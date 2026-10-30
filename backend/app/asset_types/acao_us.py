"""Ações negociadas nos EUA (USD, convertidas para BRL pelo câmbio).

ETFs americanos têm tipo próprio (``etf_us``), identificados pela coluna ETF do
diretório de símbolos da NASDAQ.
"""

from typing import ClassVar

from app.asset_types.base import CampoEspecifico, HandlerCotado, Opcao, TipoCampo
from app.domain.agenda import AGENDA_EUA, Agenda

OPCOES_BOLSA_EUA = (
    Opcao("NYSE", "NYSE"),
    Opcao("NASDAQ", "NASDAQ"),
    Opcao("AMEX", "NYSE American (AMEX)"),
    Opcao("OUTRA", "Outra"),
)


class AcaoUs(HandlerCotado):
    slug = "acao_us"
    nome = "Ação (EUA)"
    descricao = "Ações negociadas em bolsas dos Estados Unidos, em dólar."
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
