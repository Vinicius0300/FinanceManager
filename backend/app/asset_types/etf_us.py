"""ETFs negociados nos EUA (USD, convertidos para BRL pelo câmbio).

A classificação vem da coluna ETF do diretório de símbolos da NASDAQ.
"""

from typing import ClassVar

from app.asset_types.acao_us import OPCOES_BOLSA_EUA
from app.asset_types.base import CampoEspecifico, HandlerCotado, TipoCampo
from app.domain.agenda import AGENDA_EUA, Agenda


class EtfUs(HandlerCotado):
    slug = "etf_us"
    nome = "ETF (EUA)"
    descricao = "Fundos de índice negociados nos Estados Unidos, em dólar (ex.: SPY, VOO)."
    moedas_aceitas = ("USD",)
    agenda: ClassVar[Agenda] = AGENDA_EUA
    provider = "yfinance"
    lista_simbolos: ClassVar[str | None] = "EUA"
    separador_classe: ClassVar[str | None] = "-"
    campos = (
        CampoEspecifico(
            nome="bolsa",
            rotulo="Bolsa",
            tipo=TipoCampo.ESCOLHA,
            obrigatorio=False,
            opcoes=OPCOES_BOLSA_EUA,
        ),
    )
