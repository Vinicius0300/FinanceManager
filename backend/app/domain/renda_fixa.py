"""Accrual de renda fixa em 252 dias úteis, valor **bruto** (sem IR/IOF).

Fórmulas (``du`` = dias úteis em ``[inicio, fim)``, ver ``domain/calendario.py``):
- **Pré:** fator = (1 + taxa)^(du/252), taxa em % ao ano.
- **% CDI:** produto, em cada dia útil, de 1 + ((1 + CDI_dia)^(1/252) − 1) × percentual,
  usando o CDI (% a.a.) de cada dia da tabela ``indicadores`` (dia sem valor usa o último).
- **IPCA+:** fator = IPCA acumulado × (1 + spread)^(du/252). O IPCA de cada mês entra
  pro rata pelos dias úteis do mês dentro do período: (1 + IPCA_mês)^(du_no_período/du_do_mês).
  Mês ainda sem IPCA publicado usa o último IPCA conhecido (simplificação documentada).

O rendimento para no vencimento: depois dele, o valor fica congelado.
Não há arredondamentos intermediários da convenção ANBIMA (ex.: fator diário com
8 casas), por isso o resultado pode diferir do extrato em centavos.
"""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.domain.calendario import dias_uteis_entre, eh_dia_util
from app.domain.enums import Indexador, TipoIndicador
from app.domain.indicadores import Indicadores, SerieIndicador
from app.domain.montante import FatorAcumulado
from app.domain.numeros import CEM, UM, dec, dividir, potencia
from app.domain.tempo import primeiro_dia_do_mes, primeiro_dia_do_proximo_mes

DIAS_UTEIS_ANO = Decimal(252)


@dataclass(frozen=True)
class ParametrosRendaFixa:
    indexador: Indexador
    taxa: Decimal  # pré: % a.a.; CDI: % do CDI; IPCA: spread % a.a.
    data_aplicacao: date
    vencimento: date


def fator_taxa_anual(taxa_percentual_aa: Decimal, dias_uteis: int) -> Decimal:
    """(1 + taxa)^(du/252)."""
    if dias_uteis == 0:
        return UM
    return potencia(UM + taxa_percentual_aa / CEM, dividir(dec(dias_uteis), DIAS_UTEIS_ANO))


def fator_pre(taxa_percentual_aa: Decimal, inicio: date, fim: date) -> Decimal:
    return fator_taxa_anual(taxa_percentual_aa, dias_uteis_entre(inicio, fim))


class IndiceCdi:
    """Índice acumulado de um percentual do CDI a partir de uma data de origem.

    Guarda o produto acumulado dia a dia (calculado sob demanda e reaproveitado),
    para que ``fator(a, b) = acumulado(b) / acumulado(a)`` seja barato mesmo quando a
    série diária de patrimônio pede milhares de fatores.
    """

    def __init__(self, cdi: SerieIndicador, percentual: Decimal, origem: date) -> None:
        self._cdi = cdi
        self._percentual = percentual / CEM
        self._origem = origem
        self._cursor = origem
        self._dias: list[date] = []
        self._acumulados: list[Decimal] = []  # produto até dias[i], inclusive
        self._diario_por_taxa: dict[Decimal, Decimal] = {}

    def _fator_do_dia(self, dia: date) -> Decimal:
        taxa = self._cdi.valor_em(dia)
        diario = self._diario_por_taxa.get(taxa)
        if diario is None:
            diario = potencia(UM + taxa / CEM, dividir(UM, DIAS_UTEIS_ANO)) - UM
            self._diario_por_taxa[taxa] = diario
        return UM + diario * self._percentual

    def acumulado_ate(self, dia: date) -> Decimal:
        """Produto dos fatores diários nos dias úteis de ``[origem, dia)``."""
        if dia < self._origem:
            raise ValueError("Data anterior à origem do índice CDI.")
        while self._cursor < dia:
            if eh_dia_util(self._cursor):
                anterior = self._acumulados[-1] if self._acumulados else UM
                self._dias.append(self._cursor)
                self._acumulados.append(anterior * self._fator_do_dia(self._cursor))
            self._cursor += timedelta(days=1)
        indice = bisect_left(self._dias, dia)
        return self._acumulados[indice - 1] if indice else UM

    def fator(self, inicio: date, fim: date) -> Decimal:
        if fim <= inicio:
            return UM
        return dividir(self.acumulado_ate(fim), self.acumulado_ate(inicio))


def fator_ipca(ipca: SerieIndicador, inicio: date, fim: date) -> Decimal:
    """IPCA acumulado em ``[inicio, fim)``, pro rata por dias úteis em cada mês."""
    fator = UM
    mes = primeiro_dia_do_mes(inicio)
    while mes < fim:
        proximo = primeiro_dia_do_proximo_mes(mes)
        dias_no_periodo = dias_uteis_entre(max(inicio, mes), min(fim, proximo))
        if dias_no_periodo:
            taxa_mes = ipca.valor_em(mes)
            expoente = dividir(dec(dias_no_periodo), dec(dias_uteis_entre(mes, proximo)))
            fator *= potencia(UM + taxa_mes / CEM, expoente)
        mes = proximo
    return fator


def criar_fator_renda_fixa(
    parametros: ParametrosRendaFixa, indicadores: Indicadores
) -> FatorAcumulado:
    """Fator acumulado do título, limitado ao vencimento."""
    indice_cdi = (
        IndiceCdi(indicadores.serie(TipoIndicador.CDI), parametros.taxa, parametros.data_aplicacao)
        if parametros.indexador is Indexador.CDI
        else None
    )
    ipca = indicadores.serie(TipoIndicador.IPCA)

    def fator(inicio: date, fim: date) -> Decimal:
        fim = min(fim, parametros.vencimento)
        if fim <= inicio:
            return UM
        if indice_cdi is not None:
            return indice_cdi.fator(inicio, fim)
        if parametros.indexador is Indexador.PRE:
            return fator_pre(parametros.taxa, inicio, fim)
        return fator_ipca(ipca, inicio, fim) * fator_pre(parametros.taxa, inicio, fim)

    return fator
