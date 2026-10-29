"""Cliente HTTP comum dos providers: timeout, retry com backoff, rate limit e cache curto.

- **Timeout** por requisição (padrão 20 s; downloads grandes usam um maior).
- **Retry** em falha de rede, HTTP 5xx e 429, com espera exponencial
  (1 s, 2 s, 4 s...) limitada a ``espera_maxima``; no 429 respeita ``Retry-After``.
- **Rate limit**: intervalo mínimo entre requisições da mesma fonte.
- **Cache** em memória de respostas pequenas (``ttl`` por chamada), para que histórico
  e cotação do mesmo ciclo não repitam o download.
- Erros viram :class:`~app.providers.base.ProviderError` com mensagem em pt-BR.

``dormir`` e ``relogio`` são injetáveis: os testes não esperam nem dependem do relógio.
"""

import logging
import threading
import time
from collections.abc import Callable, Mapping
from typing import IO

import httpx2

from app.providers.base import (
    FonteIndisponivelError,
    LimiteRequisicoesError,
    ProviderError,
    RespostaInvalidaError,
)

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Financas/0.1"
TIMEOUT_PADRAO_S = 20.0
TIMEOUT_DOWNLOAD_S = 180.0
TAMANHO_BLOCO = 1024 * 256

Parametros = Mapping[str, str | int]


class ClienteHttp:
    def __init__(
        self,
        fonte: str,
        *,
        transporte: httpx2.BaseTransport | None = None,
        timeout: float = TIMEOUT_PADRAO_S,
        tentativas: int = 3,
        espera_base: float = 1.0,
        espera_maxima: float = 30.0,
        intervalo_minimo: float = 0.0,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.monotonic,
        cabecalhos: Mapping[str, str] | None = None,
    ) -> None:
        self.fonte = fonte
        self._cliente = httpx2.Client(
            transport=transporte,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, **(cabecalhos or {})},
        )
        self._tentativas = max(1, tentativas)
        self._espera_base = espera_base
        self._espera_maxima = espera_maxima
        self._intervalo_minimo = intervalo_minimo
        self._dormir = dormir
        self._relogio = relogio
        self._ultima_requisicao: float | None = None
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, object]] = {}
        self._trava = threading.Lock()

    def fechar(self) -> None:
        self._cliente.close()

    def limpar_cache(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------ API pública

    def get_json(
        self,
        url: str,
        params: Parametros | None = None,
        *,
        ttl: float = 0,
        aceitar_404: bool = False,
    ) -> object:
        """JSON da resposta; ``None`` se 404 e ``aceitar_404``."""
        return self._com_cache(url, params, ttl, lambda: self._json(url, params, aceitar_404))

    def get_texto(
        self,
        url: str,
        params: Parametros | None = None,
        *,
        ttl: float = 0,
        codificacao: str = "utf-8",
        aceitar_404: bool = False,
        timeout: float | None = None,
    ) -> str | None:
        """Corpo como texto; ``None`` se 404 e ``aceitar_404``."""

        def baixar() -> str | None:
            resposta = self._requisitar(url, params, aceitar_404, timeout)
            if resposta is None:
                return None
            return resposta.content.decode(codificacao, errors="replace")

        resultado = self._com_cache(url, params, ttl, baixar)
        return resultado if isinstance(resultado, str) else None

    def baixar_arquivo(self, url: str, destino: IO[bytes], *, aceitar_404: bool = False) -> bool:
        """Grava o corpo em ``destino`` em blocos (arquivos grandes). ``False`` se 404."""
        for tentativa in range(1, self._tentativas + 1):
            destino.seek(0)
            destino.truncate()
            self._respeitar_intervalo()
            try:
                with self._cliente.stream("GET", url, timeout=TIMEOUT_DOWNLOAD_S) as resposta:
                    if resposta.status_code == 404 and aceitar_404:
                        return False
                    if self._deve_repetir(resposta.status_code) and tentativa < self._tentativas:
                        self._esperar(tentativa, resposta)
                        continue
                    self._exigir_sucesso(resposta)
                    for bloco in resposta.iter_bytes(TAMANHO_BLOCO):
                        destino.write(bloco)
                destino.seek(0)
                return True
            except httpx2.TransportError as erro:
                if tentativa >= self._tentativas:
                    raise self._erro_de_rede(erro) from erro
                self._esperar(tentativa)
        raise FonteIndisponivelError(f"{self.fonte} indisponível no momento.")

    # ------------------------------------------------------------ internos

    def _com_cache(
        self, url: str, params: Parametros | None, ttl: float, obter: Callable[[], object]
    ) -> object:
        chave = (url, tuple(sorted((k, str(v)) for k, v in (params or {}).items())))
        if ttl > 0:
            guardado = self._cache.get(chave)
            if guardado is not None and guardado[0] > self._relogio():
                return guardado[1]
        resultado = obter()
        if ttl > 0:
            self._cache[chave] = (self._relogio() + ttl, resultado)
        return resultado

    def _json(self, url: str, params: Parametros | None, aceitar_404: bool) -> object:
        resposta = self._requisitar(url, params, aceitar_404)
        if resposta is None:
            return None
        try:
            return resposta.json()
        except ValueError as erro:
            raise RespostaInvalidaError(
                f"{self.fonte} respondeu em formato inesperado (não é JSON)."
            ) from erro

    def _requisitar(
        self,
        url: str,
        params: Parametros | None,
        aceitar_404: bool,
        timeout: float | None = None,
    ) -> httpx2.Response | None:
        for tentativa in range(1, self._tentativas + 1):
            self._respeitar_intervalo()
            try:
                resposta = self._cliente.get(
                    url,
                    params=dict(params) if params else None,
                    timeout=timeout if timeout is not None else httpx2.USE_CLIENT_DEFAULT,
                )
            except httpx2.TransportError as erro:
                logger.warning("%s: falha de rede (tentativa %d): %s", self.fonte, tentativa, erro)
                if tentativa >= self._tentativas:
                    raise self._erro_de_rede(erro) from erro
                self._esperar(tentativa)
                continue
            if resposta.status_code == 404 and aceitar_404:
                return None
            if self._deve_repetir(resposta.status_code) and tentativa < self._tentativas:
                logger.warning(
                    "%s: HTTP %d (tentativa %d)", self.fonte, resposta.status_code, tentativa
                )
                self._esperar(tentativa, resposta)
                continue
            self._exigir_sucesso(resposta)
            return resposta
        raise FonteIndisponivelError(f"{self.fonte} indisponível no momento.")  # pragma: no cover

    @staticmethod
    def _deve_repetir(status: int) -> bool:
        return status == 429 or status >= 500

    def _exigir_sucesso(self, resposta: httpx2.Response) -> None:
        status = resposta.status_code
        if status == 429:
            raise LimiteRequisicoesError(
                f"{self.fonte} limitou as consultas (muitas requisições). "
                "A atualização tenta de novo no próximo ciclo."
            )
        if status >= 500:
            raise FonteIndisponivelError(
                f"{self.fonte} está fora do ar no momento (erro {status} no servidor)."
            )
        if status >= 400:
            raise ProviderError(f"{self.fonte} recusou a consulta (erro {status}).")

    def _erro_de_rede(self, erro: httpx2.TransportError) -> FonteIndisponivelError:
        if isinstance(erro, httpx2.TimeoutException):
            return FonteIndisponivelError(f"{self.fonte} não respondeu a tempo.")
        return FonteIndisponivelError(
            f"Não foi possível conectar a {self.fonte}. Verifique a conexão com a internet."
        )

    def _respeitar_intervalo(self) -> None:
        with self._trava:
            if self._intervalo_minimo > 0 and self._ultima_requisicao is not None:
                falta = self._intervalo_minimo - (self._relogio() - self._ultima_requisicao)
                if falta > 0:
                    self._dormir(falta)
            self._ultima_requisicao = self._relogio()

    def _esperar(self, tentativa: int, resposta: httpx2.Response | None = None) -> None:
        espera = self._espera_base * 2 ** (tentativa - 1)
        if resposta is not None and resposta.status_code == 429:
            pedido = resposta.headers.get("Retry-After", "")
            if pedido.isdigit():
                espera = float(pedido)
        self._dormir(min(espera, self._espera_maxima))
