"""IPCA acumulado em 12 meses: composição das variações mensais, conferida à mão."""

from datetime import date
from decimal import Decimal

from app.domain.indicadores import PontoIndicador, ipca_acumulado_12_meses

D = Decimal

# nov/2025 a out/2026 (SGS 433). Produto de (1 + v/100) = 1,04628360...; o BC publica 4,63%
# na série 13522 (acumulado em 12 meses) para out/2026.
VALORES = [
    "0.18",
    "0.33",
    "0.33",
    "0.70",
    "0.88",
    "0.67",
    "0.58",
    "0.16",
    "0.07",
    "-0.32",
    "0.82",
    "0.14",
]
MESES = [date(2025, 11, 1), date(2025, 12, 1)] + [date(2026, m, 1) for m in range(1, 11)]
PONTOS = [PontoIndicador(m, D(v)) for m, v in zip(MESES, VALORES, strict=True)]


def test_confere_com_o_numero_oficial() -> None:
    assert ipca_acumulado_12_meses(PONTOS, date(2026, 10, 1)) == D("4.63")


def test_qualquer_dia_do_mes_final_vale_o_mes() -> None:
    assert ipca_acumulado_12_meses(PONTOS, date(2026, 10, 31)) == D("4.63")


def test_composto_e_nao_soma_simples() -> None:
    # 12 meses de 1%: soma daria 12,00%; composto dá 1,01^12 − 1 = 12,6825...% → 12,68%.
    pontos = [PontoIndicador(date(2026, m, 1), D("1")) for m in range(1, 13)]
    assert ipca_acumulado_12_meses(pontos, date(2026, 12, 1)) == D("12.68")


def test_deflacao_entra_com_sinal() -> None:
    # 11 meses de 0% e um de −0,32%: acumulado −0,32%.
    pontos = [PontoIndicador(date(2026, m, 1), D("0")) for m in range(1, 13)]
    pontos[7] = PontoIndicador(date(2026, 8, 1), D("-0.32"))
    assert ipca_acumulado_12_meses(pontos, date(2026, 12, 1)) == D("-0.32")


def test_mes_faltando_devolve_none() -> None:
    sem_marco = [p for p in PONTOS if p.data != date(2026, 3, 1)]
    assert ipca_acumulado_12_meses(sem_marco, date(2026, 10, 1)) is None
    # Mês final ainda não publicado também.
    assert ipca_acumulado_12_meses(PONTOS, date(2026, 11, 1)) is None


def test_meses_fora_da_janela_sao_ignorados() -> None:
    extra = [PontoIndicador(date(2025, 10, 1), D("5")), *PONTOS]
    assert ipca_acumulado_12_meses(extra, date(2026, 10, 1)) == D("4.63")
