"""ETFs negociados na B3 (BRL): de ações, de índices estrangeiros e de renda fixa.

A classificação vem do cadastro oficial da B3 (categorias ``ETF EQUITIES`` e
``ETF FOREIGN INDEX``; os de renda fixa pela categoria própria com mercado primário de ETF).
"""

from typing import ClassVar

from app.asset_types.base import HandlerCotado
from app.domain.agenda import AGENDA_B3, Agenda


class EtfBr(HandlerCotado):
    slug = "etf_br"
    nome = "ETF (Brasil)"
    descricao = "Fundos de índice negociados na B3, como BOVA11, IVVB11 e FIXA11."
    moedas_aceitas = ("BRL",)
    agenda: ClassVar[Agenda] = AGENDA_B3
    provider = "yfinance"
    lista_simbolos: ClassVar[str | None] = "B3"
    sufixo_simbolo_externo: ClassVar[str] = ".SA"
