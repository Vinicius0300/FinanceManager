"""Lista oficial de tickers da B3: cadastro de instrumentos listados (``InstrumentsConsolidated``).

Download em dois passos (dados públicos da B3, sem chave):
1. ``requestname?fileName=InstrumentsConsolidated&date=AAAA-MM-DD`` devolve um ``token``;
2. ``download/?token=<token>`` devolve o CSV (``;``, latin-1, ~20 MB, ~89 mil linhas).

A primeira linha é ``Status do Arquivo: ...`` (ex.: "Parcial" na versão da manhã, que já
traz o mercado à vista completo); o cabeçalho vem na segunda. O arquivo vai para um
temporário e é lido em streaming; só as linhas classificadas ficam na memória. Sem arquivo
na data (fim de semana, feriado, ainda não publicado), tenta os dias anteriores.
"""

import csv
import io
import logging
import tempfile
from datetime import date, timedelta
from typing import IO

from app.domain.listas import BOLSA_B3, FormatoListaError, classificar_b3
from app.providers.base import (
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
DIAS_PARA_TRAS = 7
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


class FonteListaB3:
    bolsa = BOLSA_B3
    rotulo = ROTULO

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def _token(self, dia: date) -> str | None:
        dados = self._http.get_json(
            URL_TOKEN, {"fileName": NOME_ARQUIVO, "date": dia.isoformat()}, aceitar_404=True
        )
        token = dados.get("token") if isinstance(dados, dict) else None
        return token if isinstance(token, str) and token else None

    def _do_dia(self, dia: date) -> ListaBaixada:
        token = self._token(dia)
        if token is None:
            raise SimboloNaoEncontradoError(f"{ROTULO}: sem arquivo em {dia:%d/%m/%Y}.")
        with tempfile.TemporaryFile() as temporario:
            if not self._http.baixar_arquivo(
                f"{URL_DOWNLOAD}?token={token}", temporario, aceitar_404=True
            ):
                raise SimboloNaoEncontradoError(f"{ROTULO}: sem arquivo em {dia:%d/%m/%Y}.")
            return ler_arquivo_b3(temporario, dia)

    def baixar(self, hoje: date) -> ListaBaixada:
        ultimo: ProviderError | None = None
        for atras in range(DIAS_PARA_TRAS):
            dia = hoje - timedelta(days=atras)
            try:
                return self._do_dia(dia)
            except (SimboloNaoEncontradoError, RespostaInvalidaError) as erro:
                # Dia sem arquivo (ou arquivo vazio/estranho): tenta o anterior. Falha de
                # rede (FonteIndisponivelError) sobe na hora: os outros dias também falhariam.
                logger.info("%s", erro.mensagem)
                ultimo = erro
        raise ultimo or SimboloNaoEncontradoError(f"{ROTULO}: nenhum arquivo recente.")
