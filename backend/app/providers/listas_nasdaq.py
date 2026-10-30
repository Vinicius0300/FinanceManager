"""Lista oficial de tickers dos EUA: diretório de símbolos da NASDAQ (dados públicos).

``nasdaqlisted.txt`` (NASDAQ) e ``otherlisted.txt`` (NYSE, NYSE American, NYSE Arca e
outras), separados por ``|``, com a coluna ``ETF`` (Y/N) e a linha de rodapé
``File Creation Time``. A classificação fica em ``domain/listas.py``.
"""

from datetime import date

from app.domain.listas import BOLSA_EUA, FormatoListaError, classificar_nasdaq
from app.providers.base import ListaBaixada, RespostaInvalidaError
from app.providers.http import ClienteHttp

URL_NASDAQ = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
URL_OUTRAS = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
ROTULO = "NASDAQ (diretório de símbolos)"


class FonteListaNasdaq:
    bolsa = BOLSA_EUA
    rotulo = ROTULO

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def _texto(self, url: str) -> str:
        texto = self._http.get_texto(url)
        if not texto:
            arquivo = url.rsplit("/", 1)[-1]
            raise RespostaInvalidaError(f"{ROTULO}: arquivo vazio ({arquivo}).")
        return texto

    def baixar(self, hoje: date) -> ListaBaixada:
        nasdaq = self._texto(URL_NASDAQ)
        outras = self._texto(URL_OUTRAS)
        try:
            resultado = classificar_nasdaq(nasdaq, outras)
        except FormatoListaError as erro:
            raise RespostaInvalidaError(f"{ROTULO}: {erro}") from erro
        return ListaBaixada(
            bolsa=BOLSA_EUA,
            itens=resultado.itens,
            data_arquivo=hoje,
            nao_mapeados=resultado.nao_mapeados,
        )
