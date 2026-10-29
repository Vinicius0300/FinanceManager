"""Tesouro Direto: título público cotado (quantidade × PU de venda do Tesouro Transparente).

Diferente da ``renda_fixa`` (accrual por indexador), o valor vem do **PU de venda**
publicado pelo Tesouro, que é o valor de resgate antecipado do título naquele dia.
Somente BRL e sem taxas (a custódia da B3 não é modelada). Cupons de juros semestrais
são lançados como provento.
"""

from datetime import date
from typing import ClassVar

from app.asset_types.base import (
    CampoEspecifico,
    HandlerCotado,
    Metadados,
    Opcao,
    TipoCampo,
    ler_data,
)
from app.domain.enums import TipoTransacao
from app.domain.erros import OperacaoNaoPermitidaError
from app.domain.tempo import formatar_data

TITULOS = (
    Opcao("selic", "Tesouro Selic"),
    Opcao("prefixado", "Tesouro Prefixado"),
    Opcao("prefixado_juros", "Tesouro Prefixado com Juros Semestrais"),
    Opcao("ipca", "Tesouro IPCA+"),
    Opcao("ipca_juros", "Tesouro IPCA+ com Juros Semestrais"),
    Opcao("renda_mais", "Tesouro Renda+"),
    Opcao("educa_mais", "Tesouro Educa+"),
)
TITULOS_COM_CUPOM = frozenset({"prefixado_juros", "ipca_juros"})


class TesouroDireto(HandlerCotado):
    slug = "tesouro_direto"
    nome = "Tesouro Direto"
    descricao = "Títulos públicos do Tesouro Direto, avaliados pelo preço de resgate do dia."
    moedas_aceitas = ("BRL",)
    provider = "tesouro"
    aceita_taxas: ClassVar[bool] = False
    campos_identificacao: ClassVar[frozenset[str]] = frozenset({"titulo", "vencimento"})
    campos = (
        CampoEspecifico(nome="titulo", rotulo="Título", tipo=TipoCampo.ESCOLHA, opcoes=TITULOS),
        CampoEspecifico(
            nome="vencimento",
            rotulo="Vencimento",
            tipo=TipoCampo.DATA,
            ajuda="Data de vencimento do título (ex.: 2029-01-01).",
        ),
    )

    def validar_transacao(self, metadados: Metadados, tipo: TipoTransacao, data: date) -> None:
        super().validar_transacao(metadados, tipo, data)
        vencimento = ler_data(metadados, "vencimento")
        if tipo is TipoTransacao.COMPRA and data >= vencimento:
            raise OperacaoNaoPermitidaError(
                f"Não é possível comprar um título vencido em {formatar_data(vencimento)}."
            )
        if tipo is TipoTransacao.PROVENTO and str(metadados["titulo"]) not in TITULOS_COM_CUPOM:
            raise OperacaoNaoPermitidaError(
                "Só títulos com juros semestrais pagam cupons (proventos)."
            )
