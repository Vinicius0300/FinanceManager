"""Ações e ETFs negociados nos EUA (USD, convertidos para BRL pelo câmbio)."""

from app.asset_types.base import CampoEspecifico, HandlerCotado, Opcao, TipoCampo


class AcaoUs(HandlerCotado):
    slug = "acao_us"
    nome = "Ação (EUA)"
    descricao = "Ações e ETFs negociados em bolsas dos Estados Unidos, em dólar."
    moedas_aceitas = ("USD",)
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
