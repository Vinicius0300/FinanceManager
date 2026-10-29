"""Rendimento da poupança (regra simplificada, decidida com o dono).

Regra aplicada:
- o rendimento é creditado a cada **aniversário mensal** do depósito (sem pro rata entre
  aniversários: no meio do mês o valor é o do último aniversário);
- depósitos nos dias 29, 30 e 31 passam a contar do dia 1º do mês seguinte;
- taxa do mês: 0,5% se a Selic meta vigente no início do período for maior que 8,5% a.a.;
  senão, 70% da Selic mensalizada: (1 + 0,7 × Selic)^(1/12) − 1.

Simplificações (documentadas em ``docs/CALCULOS.md``): TR considerada zero; resgates
reduzem todos os depósitos proporcionalmente (a regra real retira primeiro os depósitos
com aniversário mais distante, perdendo o rendimento do período em curso).
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from app.domain.enums import TipoIndicador
from app.domain.indicadores import Indicadores, SerieIndicador
from app.domain.montante import FatorAcumulado
from app.domain.numeros import CEM, UM, dec, dividir, potencia
from app.domain.tempo import primeiro_dia_do_proximo_mes, somar_meses

LIMITE_SELIC = Decimal("8.5")
TAXA_FIXA_MENSAL = Decimal("0.005")
FRACAO_DA_SELIC = Decimal("0.7")


def taxa_mensal_poupanca(selic_percentual_aa: Decimal) -> Decimal:
    """Taxa mensal (razão) para a Selic meta informada em % a.a."""
    if selic_percentual_aa > LIMITE_SELIC:
        return TAXA_FIXA_MENSAL
    anual = FRACAO_DA_SELIC * selic_percentual_aa / CEM
    return potencia(UM + anual, dividir(UM, dec(12))) - UM


def inicio_rendimento(data_deposito: date) -> date:
    """Data-base dos aniversários (dias 29 a 31 viram dia 1º do mês seguinte)."""
    return primeiro_dia_do_proximo_mes(data_deposito) if data_deposito.day > 28 else data_deposito


def fator_poupanca(
    selic: SerieIndicador,
    inicio: date,
    fim: date,
    taxa_mensal: Callable[[Decimal], Decimal] = taxa_mensal_poupanca,
) -> Decimal:
    """Fator acumulado dos aniversários completos entre ``inicio`` e ``fim`` (inclusive)."""
    base = inicio_rendimento(inicio)
    fator = UM
    meses = 1
    while somar_meses(base, meses) <= fim:  # cada aniversário completo credita um mês
        inicio_periodo = somar_meses(base, meses - 1)
        fator *= UM + taxa_mensal(selic.valor_em(inicio_periodo))
        meses += 1
    return fator


def criar_fator_poupanca(indicadores: Indicadores) -> FatorAcumulado:
    selic = indicadores.serie(TipoIndicador.SELIC)
    taxas: dict[Decimal, Decimal] = {}

    def taxa_em_cache(selic_aa: Decimal) -> Decimal:
        if selic_aa not in taxas:
            taxas[selic_aa] = taxa_mensal_poupanca(selic_aa)
        return taxas[selic_aa]

    def fator(inicio: date, fim: date) -> Decimal:
        return fator_poupanca(selic, inicio, fim, taxa_em_cache)

    return fator
