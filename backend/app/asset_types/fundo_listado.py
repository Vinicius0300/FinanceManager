"""Fundos negociados na B3: FII, Fiagro, FI-Infra e demais cotas de fundo em bolsa (BRL).

Engloba toda a categoria ``FUNDS`` do cadastro oficial da B3, que não separa FII de
Fiagro, FI-Infra, FIP ou FIDC (o código CFI também não). É diferente do tipo ``fundo``
(fundo aberto da CVM, identificado pelo CNPJ e sem ticker). Rendimentos mensais são
lançados como provento.
"""

from typing import ClassVar

from app.asset_types.base import HandlerCotado
from app.domain.agenda import AGENDA_B3, Agenda


class FundoListado(HandlerCotado):
    slug = "fundo_listado"
    nome = "Fundo listado (FII, Fiagro, FI-Infra)"
    descricao = "Cotas de fundos negociadas na B3, como FIIs, Fiagros e FI-Infra."
    moedas_aceitas = ("BRL",)
    agenda: ClassVar[Agenda] = AGENDA_B3
    provider = "yfinance"
    lista_simbolos: ClassVar[str | None] = "B3"
    sufixo_simbolo_externo: ClassVar[str] = ".SA"
