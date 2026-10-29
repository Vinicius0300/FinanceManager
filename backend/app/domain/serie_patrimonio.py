"""Série diária de evolução do patrimônio (pandas, valores ``Decimal`` em colunas object).

Regras de reconstrução (documentadas em ``docs/CALCULOS.md``):
- um ponto por **dia corrido**, valor ao fim do dia;
- quantidade e custo de cada posição seguem o histórico de operações (degraus);
- preço: o último preço conhecido até o dia (preenchimento para frente). Antes do
  primeiro preço do ativo, a posição vale o custo (mesma regra da avaliação atual);
- câmbio: o último conhecido até o dia; antes do primeiro, o primeiro disponível.
  Sem nenhum câmbio, a posição vale o custo em BRL;
- renda fixa e poupança: valor do accrual em cada dia;
- caixa: saldo de fim de dia de cada conta, convertido para BRL.
"""

from __future__ import annotations

import operator
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from functools import reduce
from typing import Any, TypeAlias

import pandas as pd

from app.domain.conta_corrente import LancamentoCaixa, saldos_fim_do_dia
from app.domain.montante import (
    EstadoMontante,
    FatorAcumulado,
    OperacaoMontante,
    aplicar_operacao_montante,
    chave_ordenacao,
)
from app.domain.numeros import ZERO
from app.domain.posicao import EstadoPosicao

COLUNAS = ("investimentos", "caixa", "patrimonio")

SerieDecimal: TypeAlias = "pd.Series[Any]"
"""Série diária indexada por data com valores ``Decimal`` (dtype object)."""


def indice_diario(inicio: date, fim: date) -> pd.DatetimeIndex:
    if fim < inicio:
        raise ValueError("A data final da série deve ser igual ou posterior à inicial.")
    return pd.date_range(inicio, fim, freq="D")


def serie_degraus(
    pontos: Sequence[tuple[date, Decimal]],
    inicio: date,
    fim: date,
    valor_inicial: Decimal | None = ZERO,
) -> SerieDecimal:
    """Valor vigente em cada dia: o do último ponto com data ≤ dia.

    Pontos anteriores a ``inicio`` definem o valor inicial; dias antes do primeiro ponto
    recebem ``valor_inicial``. Datas repetidas: vale o último ponto.
    """
    indice = indice_diario(inicio, fim)
    if not pontos:
        return pd.Series([valor_inicial] * len(indice), index=indice, dtype=object)
    por_data: dict[pd.Timestamp, Decimal] = {pd.Timestamp(d): v for d, v in pontos}
    bruta = pd.Series(list(por_data.values()), index=list(por_data.keys()), dtype=object)
    bruta = bruta.sort_index()
    unida = bruta.reindex(bruta.index.union(indice)).ffill()
    resultado = unida.reindex(indice).astype(object)
    resultado[resultado.isna()] = valor_inicial
    return resultado


def _cambio_diario(
    cambios: Sequence[tuple[date, Decimal]] | None, inicio: date, fim: date
) -> SerieDecimal | None:
    """Câmbio de cada dia (BRL → 1). ``None`` se a moeda não tem nenhum câmbio."""
    indice = indice_diario(inicio, fim)
    if cambios is None:
        return pd.Series([Decimal(1)] * len(indice), index=indice, dtype=object)
    if not cambios:
        return None
    primeiro = min(cambios)[1]
    return serie_degraus(cambios, inicio, fim, valor_inicial=primeiro)


def serie_valor_cotas(
    historico: Sequence[tuple[date, EstadoPosicao]],
    precos: Sequence[tuple[date, Decimal]],
    cambios: Sequence[tuple[date, Decimal]] | None,
    inicio: date,
    fim: date,
) -> SerieDecimal:
    """Valor diário em BRL de uma posição em cotas. ``cambios=None`` indica ativo em BRL."""
    quantidade = serie_degraus([(d, e.quantidade) for d, e in historico], inicio, fim)
    custo = serie_degraus([(d, e.moeda.custo) for d, e in historico], inicio, fim)
    custo_brl = serie_degraus([(d, e.brl.custo) for d, e in historico], inicio, fim)
    preco = serie_degraus(precos, inicio, fim, valor_inicial=None)
    cambio = _cambio_diario(cambios, inicio, fim)
    valores: list[Decimal] = []
    for dia in quantidade.index:
        p = preco[dia]
        valor_moeda = quantidade[dia] * p if p is not None else custo[dia]
        if cambio is None:
            valores.append(custo_brl[dia])
        else:
            valores.append(valor_moeda * cambio[dia])
    return pd.Series(valores, index=quantidade.index, dtype=object)


def serie_valor_montante(
    operacoes: Sequence[OperacaoMontante], fator: FatorAcumulado, inicio: date, fim: date
) -> SerieDecimal:
    """Valor diário (BRL) de uma posição por montante, aplicando as operações até cada dia."""
    indice = indice_diario(inicio, fim)
    pendentes = sorted(operacoes, key=chave_ordenacao)
    estado = EstadoMontante()
    posicao = 0
    valores: list[Decimal] = []
    for marca in indice:
        dia = marca.date()
        while posicao < len(pendentes) and pendentes[posicao].data <= dia:
            estado = aplicar_operacao_montante(estado, pendentes[posicao], fator)
            posicao += 1
        valores.append(estado.valor_em(dia, fator))
    return pd.Series(valores, index=indice, dtype=object)


def serie_caixa(
    lancamentos: Sequence[LancamentoCaixa],
    cambios: Sequence[tuple[date, Decimal]] | None,
    inicio: date,
    fim: date,
) -> SerieDecimal | None:
    """Saldo diário em BRL de uma conta. ``None`` se a moeda não tem câmbio algum."""
    saldo = serie_degraus(saldos_fim_do_dia(lancamentos), inicio, fim)
    cambio = _cambio_diario(cambios, inicio, fim)
    if cambio is None:
        return None
    return pd.Series(
        [s * c for s, c in zip(saldo.tolist(), cambio.tolist(), strict=True)],
        index=saldo.index,
        dtype=object,
    )


def _somar(series: Sequence[SerieDecimal], indice: pd.DatetimeIndex) -> SerieDecimal:
    if not series:
        return pd.Series([ZERO] * len(indice), index=indice, dtype=object)
    return reduce(operator.add, series)


def montar_serie_patrimonio(
    investimentos: Sequence[SerieDecimal],
    caixas: Sequence[SerieDecimal],
    inicio: date,
    fim: date,
) -> pd.DataFrame:
    """DataFrame diário com colunas ``investimentos``, ``caixa`` e ``patrimonio`` (BRL)."""
    indice = indice_diario(inicio, fim)
    total_investimentos = _somar(investimentos, indice)
    total_caixa = _somar(caixas, indice)
    return pd.DataFrame(
        {
            "investimentos": total_investimentos,
            "caixa": total_caixa,
            "patrimonio": total_investimentos + total_caixa,
        },
        index=indice,
    )
