"""Ações, units, ETFs e BDRs negociados na B3 (BRL)."""

from app.asset_types.base import CampoEspecifico, HandlerCotado, Opcao, TipoCampo


class AcaoBr(HandlerCotado):
    slug = "acao_br"
    nome = "Ação (Brasil)"
    descricao = "Ações, units, ETFs e BDRs negociados na B3."
    moedas_aceitas = ("BRL",)
    provider = "yfinance"
    campos = (
        CampoEspecifico(
            nome="tipo_papel",
            rotulo="Tipo de papel",
            tipo=TipoCampo.ESCOLHA,
            obrigatorio=False,
            opcoes=(
                Opcao("ON", "Ordinária (ON)"),
                Opcao("PN", "Preferencial (PN)"),
                Opcao("UNIT", "Unit"),
                Opcao("ETF", "ETF"),
                Opcao("BDR", "BDR"),
            ),
        ),
        CampoEspecifico(
            nome="setor",
            rotulo="Setor",
            tipo=TipoCampo.TEXTO,
            obrigatorio=False,
            tamanho_maximo=60,
        ),
    )
