"""Números (Decimal), calendário de dias úteis e utilitários de data."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, DivisionByZero

import pytest

from app.domain.calendario import (
    dias_uteis_entre,
    eh_dia_util,
    feriados_nacionais,
    pascoa,
    proximo_dia_util,
)
from app.domain.erros import ValidacaoError
from app.domain.moedas import validar_moeda
from app.domain.numeros import (
    arredondar_moeda,
    arredondar_quantidade,
    dec,
    dividir,
    formatar_numero,
    percentual,
    potencia,
    texto_decimal,
)
from app.domain.tempo import (
    data_local,
    dias_corridos,
    formatar_data,
    primeiro_dia_do_mes,
    primeiro_dia_do_proximo_mes,
    somar_meses,
)

# ---------------------------------------------------------------- Decimal


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("10.50", Decimal("10.50")),
        (7, Decimal(7)),
        (Decimal("0.1"), Decimal("0.1")),
        (" 3 ", Decimal(3)),
    ],
)
def test_dec_aceita_str_int_e_decimal(entrada: str | int | Decimal, esperado: Decimal) -> None:
    assert dec(entrada) == esperado


@pytest.mark.parametrize("entrada", [0.1, True, None, [1]])
def test_dec_recusa_float_bool_e_outros_tipos(entrada: object) -> None:
    with pytest.raises(TypeError, match="float é proibido"):
        dec(entrada)  # type: ignore[arg-type]


@pytest.mark.parametrize("entrada", ["abc", "", "NaN", "Infinity", "-inf"])
def test_dec_recusa_textos_invalidos_e_nao_finitos(entrada: str) -> None:
    with pytest.raises(ValueError, match="Número inválido"):
        dec(entrada)


def test_dividir_usa_28_digitos_e_levanta_em_divisao_por_zero() -> None:
    # 1/3 = 0,333... com 28 dígitos significativos (contexto do projeto).
    assert dividir(Decimal(1), Decimal(3)) == Decimal("0." + "3" * 28)
    with pytest.raises(DivisionByZero):
        dividir(Decimal(1), Decimal(0))


def test_potencia_com_expoente_fracionario() -> None:
    # 1,21^(1/2) = 1,1 exatamente.
    assert potencia(Decimal("1.21"), Decimal("0.5")) == Decimal("1.1")


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        # ROUND_HALF_EVEN: o 5 exato vai para o vizinho par.
        ("2.345", "2.34"),
        ("2.355", "2.36"),
        ("1010.025", "1010.02"),
        ("-2.345", "-2.34"),
        ("2.3451", "2.35"),  # acima da metade sobe
        ("10", "10.00"),
    ],
)
def test_arredondar_moeda_bancario(valor: str, esperado: str) -> None:
    assert arredondar_moeda(Decimal(valor)) == Decimal(esperado)
    assert str(arredondar_moeda(Decimal(valor))) == esperado


def test_arredondar_quantidade_oito_casas() -> None:
    assert arredondar_quantidade(Decimal("0.123456785")) == Decimal("0.12345678")  # 8 é par
    assert arredondar_quantidade(Decimal("0.123456775")) == Decimal("0.12345678")  # 7 sobe


def test_percentual_converte_razao_com_duas_casas() -> None:
    assert percentual(Decimal("0.15")) == Decimal("15.00")
    assert percentual(dividir(Decimal(1), Decimal(3))) == Decimal("33.33")


def test_texto_decimal_sem_notacao_cientifica() -> None:
    assert texto_decimal(Decimal("1E+3")) == "1000"
    assert texto_decimal(Decimal("0.00001")) == "0.00001"
    assert texto_decimal(Decimal("10.50")) == "10.50"


def test_formatar_numero_para_mensagens() -> None:
    assert formatar_numero(Decimal("10.500")) == "10,5"
    assert formatar_numero(Decimal("100")) == "100"


def test_validar_moeda() -> None:
    assert validar_moeda(" usd ") == "USD"
    with pytest.raises(ValidacaoError, match="Moeda inválida"):
        validar_moeda("REAL")


# ---------------------------------------------------------------- Calendário


@pytest.mark.parametrize(
    ("ano", "esperado"),
    [
        (2000, date(2000, 4, 23)),
        (2019, date(2019, 4, 21)),
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
    ],
)
def test_pascoa(ano: int, esperado: date) -> None:
    assert pascoa(ano) == esperado


def test_feriados_nacionais_2026_inclui_moveis_e_consciencia_negra() -> None:
    assert feriados_nacionais(2026) == {
        date(2026, 1, 1),
        date(2026, 2, 16),  # segunda de Carnaval (Páscoa − 48)
        date(2026, 2, 17),  # terça de Carnaval
        date(2026, 4, 3),  # Sexta-feira Santa
        date(2026, 4, 21),
        date(2026, 5, 1),
        date(2026, 6, 4),  # Corpus Christi (Páscoa + 60)
        date(2026, 9, 7),
        date(2026, 10, 12),
        date(2026, 11, 2),
        date(2026, 11, 15),
        date(2026, 11, 20),
        date(2026, 12, 25),
    }


def test_consciencia_negra_so_a_partir_de_2024() -> None:
    assert date(2023, 11, 20) not in feriados_nacionais(2023)
    assert date(2024, 11, 20) in feriados_nacionais(2024)


def test_eh_dia_util() -> None:
    assert not eh_dia_util(date(2026, 4, 4))  # sábado
    assert not eh_dia_util(date(2026, 4, 3))  # Sexta-feira Santa
    assert eh_dia_util(date(2026, 4, 6))
    assert proximo_dia_util(date(2026, 4, 3)) == date(2026, 4, 6)
    assert proximo_dia_util(date(2026, 4, 6)) == date(2026, 4, 6)


def test_dias_uteis_2025_sao_252() -> None:
    # 2025 começa numa quarta: 261 dias de semana. Feriados em dias de semana: 01/01,
    # Carnaval (2), Sexta Santa, 21/04, 01/05, Corpus Christi, 20/11 e 25/12 = 9.
    # 261 − 9 = 252.
    assert dias_uteis_entre(date(2025, 1, 1), date(2026, 1, 1)) == 252


def test_dias_uteis_2026_sao_249() -> None:
    # 2026 começa numa quinta: 261 dias de semana; 12 feriados caem em dias de semana.
    assert dias_uteis_entre(date(2026, 1, 1), date(2027, 1, 1)) == 249


def test_dias_uteis_intervalo_semiaberto_e_casos_de_borda() -> None:
    assert dias_uteis_entre(date(2025, 8, 1), date(2025, 9, 1)) == 21  # agosto/2025
    assert dias_uteis_entre(date(2025, 8, 4), date(2025, 8, 5)) == 1  # conta o início
    assert dias_uteis_entre(date(2025, 8, 4), date(2025, 8, 4)) == 0
    assert dias_uteis_entre(date(2025, 8, 5), date(2025, 8, 4)) == 0
    # Virada de ano usa os feriados dos dois anos: 31/12 é útil, 01/01 não.
    assert dias_uteis_entre(date(2025, 12, 31), date(2026, 1, 2)) == 1


# ---------------------------------------------------------------- Datas


def test_data_local_usa_fuso_de_brasilia() -> None:
    # 02h UTC do dia 2 ainda é 23h do dia 1 em Brasília (UTC−3).
    assert data_local(datetime(2025, 1, 2, 2, tzinfo=UTC)) == date(2025, 1, 1)
    assert data_local(datetime(2025, 1, 2, 4, tzinfo=UTC)) == date(2025, 1, 2)
    fuso_tokyo = timezone(timedelta(hours=9))
    assert data_local(datetime(2025, 1, 2, 8, tzinfo=fuso_tokyo)) == date(2025, 1, 1)


def test_data_local_recusa_datetime_sem_fuso() -> None:
    with pytest.raises(ValueError, match="fuso"):
        data_local(datetime(2025, 1, 1))


def test_utilitarios_de_mes() -> None:
    assert formatar_data(date(2025, 3, 5)) == "05/03/2025"
    assert primeiro_dia_do_mes(date(2025, 3, 17)) == date(2025, 3, 1)
    assert primeiro_dia_do_proximo_mes(date(2025, 12, 31)) == date(2026, 1, 1)
    assert primeiro_dia_do_proximo_mes(date(2025, 1, 31)) == date(2025, 2, 1)
    assert somar_meses(date(2025, 11, 15), 3) == date(2026, 2, 15)
    assert somar_meses(date(2025, 3, 15), -3) == date(2024, 12, 15)
    with pytest.raises(ValueError, match="até 28"):
        somar_meses(date(2025, 1, 31), 1)
    assert dias_corridos(date(2025, 1, 30), date(2025, 2, 1)) == [
        date(2025, 1, 30),
        date(2025, 1, 31),
        date(2025, 2, 1),
    ]
