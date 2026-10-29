"""Calendário de dias úteis (feriados nacionais), base do accrual em 252 dias úteis.

Feriados considerados (os mesmos que o mercado financeiro usa para contar dias úteis):
- fixos: 01/01, 21/04, 01/05, 07/09, 12/10, 02/11, 15/11 e 25/12;
- 20/11 (Consciência Negra), feriado nacional a partir de 2024 (Lei 14.759/2023);
- móveis, calculados pela Páscoa: Carnaval (segunda e terça, Páscoa − 48 e − 47),
  Sexta-feira Santa (Páscoa − 2) e Corpus Christi (Páscoa + 60).

Sábados e domingos não são dias úteis. Contagens usam o intervalo semiaberto
``[inicio, fim)``: o dia da aplicação rende, o dia do cálculo ainda não.
"""

from datetime import date, timedelta
from functools import lru_cache

import numpy as np

ANO_CONSCIENCIA_NEGRA = 2024


@lru_cache(maxsize=512)
def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    mes, dia = divmod(h + el - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


@lru_cache(maxsize=512)
def feriados_nacionais(ano: int) -> frozenset[date]:
    """Feriados nacionais do ano (inclui os móveis)."""
    domingo_pascoa = pascoa(ano)
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
    if ano >= ANO_CONSCIENCIA_NEGRA:
        fixos.append((11, 20))
    moveis = [
        domingo_pascoa - timedelta(days=48),  # segunda de Carnaval
        domingo_pascoa - timedelta(days=47),  # terça de Carnaval
        domingo_pascoa - timedelta(days=2),  # Sexta-feira Santa
        domingo_pascoa + timedelta(days=60),  # Corpus Christi
    ]
    return frozenset([date(ano, mes, dia) for mes, dia in fixos] + moveis)


def eh_dia_util(dia: date) -> bool:
    return dia.weekday() < 5 and dia not in feriados_nacionais(dia.year)


@lru_cache(maxsize=64)
def _feriados_entre_anos(ano_inicial: int, ano_final: int) -> np.ndarray:
    datas = sorted(f for ano in range(ano_inicial, ano_final + 1) for f in feriados_nacionais(ano))
    return np.array(datas, dtype="datetime64[D]")


def dias_uteis_entre(inicio: date, fim: date) -> int:
    """Quantidade de dias úteis em ``[inicio, fim)``. Zero se ``fim <= inicio``."""
    if fim <= inicio:
        return 0
    feriados = _feriados_entre_anos(inicio.year, fim.year)
    return int(
        np.busday_count(np.datetime64(inicio, "D"), np.datetime64(fim, "D"), holidays=feriados)
    )


def proximo_dia_util(dia: date) -> date:
    """O próprio dia, se útil; senão o próximo dia útil."""
    while not eh_dia_util(dia):
        dia += timedelta(days=1)
    return dia
