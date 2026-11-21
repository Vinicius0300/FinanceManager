"""Lista oficial de tickers da B3: cadastro de instrumentos listados (``InstrumentsConsolidated``).

Download em dois passos (dados públicos da B3, sem chave):
1. ``requestname?fileName=InstrumentsConsolidated&date=AAAA-MM-DD`` devolve um ``token``;
2. ``download/?token=<token>`` devolve o CSV (``;``, latin-1, ~20 MB, ~89 mil linhas).

A primeira linha é ``Status do Arquivo: ...`` (ex.: "Parcial" na versão da manhã, que já
traz o mercado à vista completo); o cabeçalho vem na segunda. O arquivo vai para um
temporário e é lido em streaming; só as linhas classificadas ficam na memória. Sem arquivo
na data (fim de semana, feriado, ainda não publicado), tenta os dias anteriores. A B3
responde 404 **ou 400** ("Bad Request") para data sem arquivo, no pedido do token ou no
download; os dois contam como "sem arquivo". Se **todos** os dias da janela vierem com 400,
o erro é outro (provável mudança na API) e a mensagem diz isso; se só parte vier com 400, a
mensagem final diz quantos foram recusados. A publicação às vezes atrasa mais de uma semana
(nov/2026: 8 dias sem arquivo), por isso a janela de busca é de ``DIAS_PARA_TRAS`` dias
corridos.
"""

import csv
import io
import logging
import tempfile
from datetime import date, timedelta
from typing import IO

from app.domain.listas import BOLSA_B3, FormatoListaError, classificar_b3
from app.providers.base import (
    ConsultaRecusadaError,
    ListaBaixada,
    ProviderError,
    RespostaInvalidaError,
    SimboloNaoEncontradoError,
)
from app.providers.http import ClienteHttp

logger = logging.getLogger(__name__)

URL_TOKEN = "https://arquivos.b3.com.br/api/download/requestname"  # noqa: S105 - URL pública
URL_DOWNLOAD = "https://arquivos.b3.com.br/api/download/"
NOME_ARQUIVO = "InstrumentsConsolidated"
ROTULO = "B3 (cadastro de instrumentos)"
DIAS_PARA_TRAS = 21
PREFIXO_STATUS = "Status do Arquivo:"


def ler_arquivo_b3(arquivo: IO[bytes], dia: date) -> ListaBaixada:
    """Lê o CSV já baixado (com ou sem a linha de status) e classifica os papéis."""
    texto = io.TextIOWrapper(arquivo, encoding="latin-1", newline="")
    try:
        primeira = texto.readline()
        status: str | None = None
        if primeira.startswith(PREFIXO_STATUS):
            status = primeira[len(PREFIXO_STATUS) :].strip() or None
        else:  # sem a linha de status: a primeira já é o cabeçalho
            texto.seek(0)
        try:
            resultado = classificar_b3(csv.DictReader(texto, delimiter=";"))
        except FormatoListaError as erro:
            raise RespostaInvalidaError(f"{ROTULO}: {erro}") from erro
    finally:
        texto.detach()  # quem abriu o arquivo é quem fecha
    if not resultado.itens:
        raise RespostaInvalidaError(f"{ROTULO}: arquivo de {dia:%d/%m/%Y} sem papéis à vista.")
    return ListaBaixada(
        bolsa=BOLSA_B3,
        itens=resultado.itens,
        data_arquivo=dia,
        status_arquivo=status,
        nao_mapeados=resultado.nao_mapeados,
    )


class _DiaRecusadoError(SimboloNaoEncontradoError):
    """B3 respondeu 400 (token ou download): tratado como dia sem arquivo."""


def _recusado(erro: ConsultaRecusadaError, dia: date) -> _DiaRecusadoError:
    """400 vira "dia sem arquivo"; outro 4xx sobe como está (problema de verdade)."""
    if erro.status != 400:
        raise erro
    return _DiaRecusadoError(f"{ROTULO}: sem arquivo em {dia:%d/%m/%Y} (erro 400).")


class FonteListaB3:
    bolsa = BOLSA_B3
    rotulo = ROTULO

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def _token(self, dia: date) -> str | None:
        try:
            dados = self._http.get_json(
                URL_TOKEN, {"fileName": NOME_ARQUIVO, "date": dia.isoformat()}, aceitar_404=True
            )
        except ConsultaRecusadaError as erro:
            raise _recusado(erro, dia) from erro
        token = dados.get("token") if isinstance(dados, dict) else None
        return token if isinstance(token, str) and token else None

    def _do_dia(self, dia: date) -> ListaBaixada:
        token = self._token(dia)
        if token is None:
            raise SimboloNaoEncontradoError(f"{ROTULO}: sem arquivo em {dia:%d/%m/%Y}.")
        with tempfile.TemporaryFile() as temporario:
            try:
                baixado = self._http.baixar_arquivo(
                    f"{URL_DOWNLOAD}?token={token}", temporario, aceitar_404=True
                )
            except ConsultaRecusadaError as erro:
                raise _recusado(erro, dia) from erro
            if not baixado:
                raise SimboloNaoEncontradoError(f"{ROTULO}: sem arquivo em {dia:%d/%m/%Y}.")
            return ler_arquivo_b3(temporario, dia)

    def baixar(self, hoje: date) -> ListaBaixada:
        ultimo: ProviderError | None = None
        recusados = 0
        for atras in range(DIAS_PARA_TRAS):
            dia = hoje - timedelta(days=atras)
            try:
                return self._do_dia(dia)
            except (SimboloNaoEncontradoError, RespostaInvalidaError) as erro:
                # Dia sem arquivo (ou arquivo vazio/estranho): tenta o anterior. Falha de
                # rede (FonteIndisponivelError) sobe na hora: os outros dias também falhariam.
                logger.info("%s", erro.mensagem)
                ultimo = erro
                recusados += isinstance(erro, _DiaRecusadoError)
        if recusados == DIAS_PARA_TRAS:
            logger.warning("%s: erro 400 em todos os %d dias consultados", ROTULO, recusados)
            raise RespostaInvalidaError(
                f"{ROTULO}: a B3 recusou a consulta (erro 400) em todos os últimos "
                f"{DIAS_PARA_TRAS} dias. A API pode ter mudado; tente de novo mais tarde."
            )
        if recusados:
            # Parte da janela com 400: a mensagem diz quantos, para não esconder uma API
            # que começou a recusar pedidos (o erro privado não sai daqui).
            raise SimboloNaoEncontradoError(
                f"{ROTULO}: sem arquivo nos últimos {DIAS_PARA_TRAS} dias "
                f"({recusados} recusados com erro 400)."
            )
        raise ultimo or SimboloNaoEncontradoError(f"{ROTULO}: nenhum arquivo recente.")
