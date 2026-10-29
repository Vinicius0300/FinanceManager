"""Renda fixa (CDB, LCI, LCA, debêntures...): valor estimado por accrual em 252 dias úteis.

Tesouro Direto tem tipo próprio (``tesouro_direto``), cotado pelo PU do Tesouro.
"""

from datetime import date
from decimal import Decimal

from app.asset_types.base import (
    CampoEspecifico,
    HandlerMontante,
    Metadados,
    Opcao,
    TipoCampo,
    ler_data,
    ler_decimal,
)
from app.domain.enums import Indexador, TipoIndicador, TipoTransacao
from app.domain.erros import DetalheCampo, OperacaoNaoPermitidaError
from app.domain.indicadores import Indicadores
from app.domain.montante import FatorAcumulado
from app.domain.numeros import ZERO
from app.domain.renda_fixa import ParametrosRendaFixa, criar_fator_renda_fixa
from app.domain.tempo import formatar_data

_INDICADOR_DO_INDEXADOR = {
    Indexador.PRE: frozenset[TipoIndicador](),
    Indexador.CDI: frozenset({TipoIndicador.CDI}),
    Indexador.IPCA: frozenset({TipoIndicador.IPCA}),
}


def parametros(metadados: Metadados) -> ParametrosRendaFixa:
    return ParametrosRendaFixa(
        indexador=Indexador(str(metadados["indexador"])),
        taxa=ler_decimal(metadados, "taxa"),
        data_aplicacao=ler_data(metadados, "data_aplicacao"),
        vencimento=ler_data(metadados, "vencimento"),
    )


class RendaFixa(HandlerMontante):
    slug = "renda_fixa"
    nome = "Renda fixa"
    descricao = (
        "CDB, LCI, LCA e outros títulos prefixados, pós-fixados em % do CDI ou atrelados "
        "ao IPCA, com valor estimado por accrual (Tesouro Direto tem tipo próprio)."
    )
    campos = (
        CampoEspecifico(
            nome="indexador",
            rotulo="Indexador",
            tipo=TipoCampo.ESCOLHA,
            opcoes=(
                Opcao(Indexador.PRE.value, "Prefixado"),
                Opcao(Indexador.CDI.value, "% do CDI"),
                Opcao(Indexador.IPCA.value, "IPCA +"),
            ),
        ),
        CampoEspecifico(
            nome="taxa",
            rotulo="Taxa",
            tipo=TipoCampo.DECIMAL,
            minimo=ZERO,
            maximo=Decimal(1000),
            ajuda="Prefixado: % ao ano. % do CDI: percentual (ex.: 110). IPCA +: % ao ano.",
        ),
        CampoEspecifico(nome="data_aplicacao", rotulo="Data de aplicação", tipo=TipoCampo.DATA),
        CampoEspecifico(nome="vencimento", rotulo="Vencimento", tipo=TipoCampo.DATA),
        CampoEspecifico(nome="emissor", rotulo="Emissor", tipo=TipoCampo.TEXTO, tamanho_maximo=100),
        CampoEspecifico(
            nome="liquidez",
            rotulo="Liquidez",
            tipo=TipoCampo.ESCOLHA,
            opcoes=(
                Opcao("diaria", "Diária"),
                Opcao("no_vencimento", "No vencimento"),
            ),
        ),
    )

    def regras_adicionais(self, metadados: Metadados) -> list[DetalheCampo]:
        erros: list[DetalheCampo] = []
        if ler_decimal(metadados, "taxa") <= ZERO:
            erros.append(DetalheCampo("taxa", "A taxa deve ser maior que zero."))
        if ler_data(metadados, "vencimento") <= ler_data(metadados, "data_aplicacao"):
            erros.append(
                DetalheCampo("vencimento", "O vencimento deve ser posterior à data de aplicação.")
            )
        return erros

    def validar_transacao(self, metadados: Metadados, tipo: TipoTransacao, data: date) -> None:
        super().validar_transacao(metadados, tipo, data)
        aplicacao = ler_data(metadados, "data_aplicacao")
        vencimento = ler_data(metadados, "vencimento")
        if data < aplicacao:
            raise OperacaoNaoPermitidaError(
                f"A data ({formatar_data(data)}) é anterior à aplicação do título "
                f"({formatar_data(aplicacao)})."
            )
        if tipo is TipoTransacao.APORTE and data >= vencimento:
            raise OperacaoNaoPermitidaError(
                f"Não é possível aportar em um título vencido em {formatar_data(vencimento)}."
            )

    def indicadores_necessarios(self, metadados: Metadados) -> frozenset[TipoIndicador]:
        return _INDICADOR_DO_INDEXADOR[Indexador(str(metadados["indexador"]))]

    def referencia_indicadores(self, metadados: Metadados, data_ref: date) -> date:
        # Depois do vencimento o valor fica congelado: indicadores novos não importam.
        return min(data_ref, ler_data(metadados, "vencimento"))

    def criar_fator(self, metadados: Metadados, indicadores: Indicadores) -> FatorAcumulado:
        return criar_fator_renda_fixa(parametros(metadados), indicadores)
