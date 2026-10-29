"""Ações e ETFs negociados nos EUA (USD, convertidos para BRL pelo câmbio)."""

from typing import ClassVar

from app.asset_types.base import CampoEspecifico, HandlerCotado, Opcao, TipoCampo
from app.domain.agenda import AGENDA_EUA, Agenda


class AcaoUs(HandlerCotado):
    slug = "acao_us"
    nome = "Ação (EUA)"
    descricao = "Ações e ETFs negociados em bolsas dos Estados Unidos, em dólar."
    moedas_aceitas = ("USD",)
    agenda: ClassVar[Agenda] = AGENDA_EUA
    provider = "yfinance"
    campos = (
        CampoEspecifico(
            nome="bolsa",
            rotulo="Bolsa",
            tipo=TipoCampo.ESCOLHA,
            obrigatorio=False,
            opcoes=(
                Opcao("NYSE", "NYSE"),
                Opcao("NASDAQ", "NASDAQ"),
                Opcao("AMEX", "NYSE American (AMEX)"),
                Opcao("OUTRA", "Outra"),
            ),
        ),
    )
