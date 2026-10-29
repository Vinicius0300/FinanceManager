"""Indicadores, preços, posição por montante, accrual de renda fixa e poupança."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.enums import Indexador, OrigemPreco, TipoIndicador
from app.domain.erros import (
    CambioAusenteError,
    IndicadorAusenteError,
    PosicaoInsuficienteError,
    ValidacaoError,
)
from app.domain.indicadores import Indicadores, PontoIndicador, SerieIndicador
from app.domain.montante import (
    Aporte,
    Resgate,
    aplicar_operacoes_montante,
)
from app.domain.numeros import UM, ZERO, arredondar, arredondar_moeda
from app.domain.poupanca import (
    criar_fator_poupanca,
    fator_poupanca,
    inicio_rendimento,
    taxa_mensal_poupanca,
)
from app.domain.precos import PontoPreco, SeriePrecos
from app.domain.renda_fixa import (
    IndiceCdi,
    ParametrosRendaFixa,
    criar_fator_renda_fixa,
    fator_ipca,
    fator_pre,
    fator_taxa_anual,
)

D = Decimal


def serie(tipo: TipoIndicador, *pontos: tuple[date, str], moeda: str = "BRL") -> SerieIndicador:
    return SerieIndicador(tipo, [PontoIndicador(d, D(v)) for d, v in pontos], moeda)


def cdi_constante(taxa: str = "14.90") -> Indicadores:
    return Indicadores([serie(TipoIndicador.CDI, (date(2025, 1, 1), taxa))])


# ---------------------------------------------------------------- Indicadores e preços


def test_serie_indicador_preenche_para_frente() -> None:
    selic = serie(TipoIndicador.SELIC, (date(2025, 1, 10), "13.25"), (date(2025, 2, 5), "14.25"))
    assert selic.valor_em(date(2025, 1, 10)) == D("13.25")
    assert selic.valor_em(date(2025, 2, 4)) == D("13.25")
    assert selic.valor_em(date(2025, 3, 1)) == D("14.25")
    assert selic.ponto_em(date(2025, 1, 9)) is None
    assert not selic.vazia
    assert len(selic.pontos) == 2


def test_serie_indicador_sem_valor_ou_antigo_demais() -> None:
    cdi = serie(TipoIndicador.CDI, (date(2025, 1, 10), "13"))
    with pytest.raises(IndicadorAusenteError, match="Não há CDI registrado até 09/01/2025"):
        cdi.valor_em(date(2025, 1, 9))
    with pytest.raises(IndicadorAusenteError, match="antigo demais"):
        cdi.valor_em(date(2025, 1, 20), tolerancia_dias=7)
    assert cdi.valor_em(date(2025, 1, 17), tolerancia_dias=7) == D(13)


def test_serie_indicador_recusa_data_repetida() -> None:
    with pytest.raises(ValueError, match="Data repetida"):
        serie(TipoIndicador.CDI, (date(2025, 1, 1), "1"), (date(2025, 1, 1), "2"))


def test_indicadores_cambio() -> None:
    indicadores = Indicadores(
        [serie(TipoIndicador.CAMBIO, (date(2025, 1, 2), "6.10"), moeda="USD")]
    )
    assert indicadores.cambio_em("BRL", date(2020, 1, 1)) == UM
    assert indicadores.cambio_em("USD", date(2025, 1, 3)) == D("6.10")
    assert indicadores.serie(TipoIndicador.CAMBIO, "USD").nome == "câmbio USD"
    with pytest.raises(CambioAusenteError, match="Câmbio EUR/BRL indisponível"):
        indicadores.cambio_em("EUR", date(2025, 1, 3))
    with pytest.raises(CambioAusenteError):
        indicadores.cambio_em("USD", date(2025, 1, 1))
    assert indicadores.serie(TipoIndicador.IPCA).vazia


def test_serie_precos_usa_a_data_local() -> None:
    serie_precos = SeriePrecos(
        [
            # 02h UTC do dia 2 = 23h do dia 1 em Brasília.
            PontoPreco(datetime(2025, 1, 2, 2, tzinfo=UTC), D(10), OrigemPreco.AUTOMATICO),
            PontoPreco(datetime(2025, 1, 2, 15, tzinfo=UTC), D(11), OrigemPreco.AUTOMATICO),
            PontoPreco(datetime(2025, 1, 2, 18, tzinfo=UTC), D(12), OrigemPreco.MANUAL),
        ]
    )
    ultimo_dia_1 = serie_precos.ultimo_ate(date(2025, 1, 1))
    assert ultimo_dia_1 is not None
    assert ultimo_dia_1.valor == D(10)
    ultimo_dia_2 = serie_precos.ultimo_ate(date(2025, 1, 2))
    assert ultimo_dia_2 is not None
    assert ultimo_dia_2.valor == D(12)
    assert ultimo_dia_2.origem is OrigemPreco.MANUAL
    assert serie_precos.ultimo_ate(date(2024, 12, 31)) is None
    assert serie_precos.ultimo_por_dia() == [(date(2025, 1, 1), D(10)), (date(2025, 1, 2), D(12))]
    assert SeriePrecos().vazia


# ---------------------------------------------------------------- Montante (resgate proporcional)


def dez_por_cento(inicio: date, fim: date) -> Decimal:
    """Fator de teste: rende 10% assim que passa um dia."""
    return D("1.1") if fim > inicio else UM


A, B, C = date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)


def test_resgate_parcial_reduz_principal_proporcionalmente() -> None:
    # Aporte 1.000 → saldo 1.100. Resgate 550 = metade (f = 0,5):
    # principal 500, custo 500, lucro realizado = 550 − 500 = 50. Depois vale 500 × 1,1 = 550.
    estado = aplicar_operacoes_montante([Aporte(A, D(1000)), Resgate(B, D(550))], dez_por_cento)
    assert estado.valores.custo == D(500)
    assert estado.valores.lucro_realizado == D(50)
    assert estado.valores.total_investido == D(1000)
    assert estado.valor_em(C, dez_por_cento) == D(550)


def test_resgate_total_zera_a_posicao() -> None:
    estado = aplicar_operacoes_montante([Aporte(A, D(1000)), Resgate(B, D(1100))], dez_por_cento)
    assert estado.zerada
    assert estado.valores.custo == ZERO
    assert estado.valores.lucro_realizado == D(100)


def test_resgate_do_saldo_exibido_zera_mesmo_com_fracao_de_centavo() -> None:
    # Saldo real 1.000,0001 aparece como 1.000,00; resgatar 1.000,00 zera a posição.
    def quase_um(inicio: date, fim: date) -> Decimal:
        return D("1.0000001") if fim > inicio else UM

    estado = aplicar_operacoes_montante([Aporte(A, D(1000)), Resgate(B, D("1000.00"))], quase_um)
    assert estado.zerada
    assert estado.valores.lucro_realizado == ZERO


def test_resgate_maior_que_o_saldo() -> None:
    with pytest.raises(PosicaoInsuficienteError) as erro:
        aplicar_operacoes_montante([Aporte(A, D(1000)), Resgate(B, D(1200))], dez_por_cento)
    assert erro.value.mensagem == (
        "Resgate de R$ 1200 maior que o saldo estimado de R$ 1100 em 01/02/2025."
    )
    with pytest.raises(PosicaoInsuficienteError):
        aplicar_operacoes_montante([Resgate(B, D(1))], dez_por_cento)


def test_aporte_e_resgate_validam_valor() -> None:
    with pytest.raises(ValidacaoError):
        Aporte(A, ZERO)
    with pytest.raises(ValidacaoError):
        Resgate(A, D(-1))


# ---------------------------------------------------------------- Renda fixa


def test_fator_pre_em_um_ano_de_252_dias_uteis() -> None:
    # 2025 tem 252 dias úteis → (1,12)^(252/252) = 1,12 exatamente: R$ 10.000 → R$ 11.200.
    fator = fator_pre(D(12), date(2025, 1, 1), date(2026, 1, 1))
    assert fator == D("1.12")
    assert fator_taxa_anual(D(12), 0) == UM


def test_cdi_100_porcento_exemplo_do_prompt() -> None:
    # R$ 10.000 a 100% do CDI (14,90% a.a.) em agosto/2025 (21 dias úteis):
    # 10.000 × 1,149^(21/252) = 10.000 × 1,0116416 = 10.116,42.
    parametros = ParametrosRendaFixa(Indexador.CDI, D(100), date(2025, 8, 1), date(2030, 1, 2))
    fator = criar_fator_renda_fixa(parametros, cdi_constante())
    assert arredondar_moeda(D(10000) * fator(date(2025, 8, 1), date(2025, 9, 1))) == D("10116.42")


def test_cdi_110_porcento() -> None:
    # Fator diário = 1 + (1,149^(1/252) − 1) × 1,10 ≈ 1,000606442.
    # (1,000606442)^21 ≈ 1,0128128 → R$ 10.128,13.
    parametros = ParametrosRendaFixa(Indexador.CDI, D(110), date(2025, 8, 1), date(2030, 1, 2))
    fator = criar_fator_renda_fixa(parametros, cdi_constante())
    assert arredondar_moeda(D(10000) * fator(date(2025, 8, 1), date(2025, 9, 1))) == D("10128.13")


def test_cdi_variavel_usa_a_taxa_de_cada_dia() -> None:
    # 01 a 14/08/2025: 10 dias úteis a 14,90%; 15 a 29/08: 11 dias úteis a 15,15%.
    # 10.000 × 1,149^(10/252) × 1,1515^(11/252) ≈ 10.000 × 1,0117376 = 10.117,38.
    indicadores = Indicadores(
        [
            serie(
                TipoIndicador.CDI,
                (date(2025, 1, 1), "14.90"),
                (date(2025, 8, 15), "15.15"),
            )
        ]
    )
    parametros = ParametrosRendaFixa(Indexador.CDI, D(100), date(2025, 8, 1), date(2030, 1, 2))
    fator = criar_fator_renda_fixa(parametros, indicadores)
    assert arredondar_moeda(D(10000) * fator(date(2025, 8, 1), date(2025, 9, 1))) == D("10117.38")


def test_indice_cdi_reaproveita_acumulado_e_compoe_fatores() -> None:
    indice = IndiceCdi(cdi_constante().serie(TipoIndicador.CDI), D(100), date(2025, 8, 1))
    meio = date(2025, 8, 15)
    fim = date(2025, 9, 1)
    composto = indice.fator(date(2025, 8, 1), meio) * indice.fator(meio, fim)
    assert arredondar(composto, 20) == arredondar(indice.fator(date(2025, 8, 1), fim), 20)
    assert indice.fator(fim, meio) == UM
    with pytest.raises(ValueError, match="anterior à origem"):
        indice.acumulado_ate(date(2025, 7, 1))


def test_cdi_sem_indicador_registrado() -> None:
    parametros = ParametrosRendaFixa(Indexador.CDI, D(100), date(2025, 8, 1), date(2030, 1, 2))
    fator = criar_fator_renda_fixa(parametros, Indicadores())
    with pytest.raises(IndicadorAusenteError, match="CDI"):
        fator(date(2025, 8, 1), date(2025, 9, 1))


def test_ipca_mais_exemplo_do_prompt() -> None:
    # IPCA + 6% com IPCA de 0,40% em agosto/2025 (21 d.u.):
    # 10.000 × 1,004 × 1,06^(21/252) = 10.000 × 1,004 × 1,0048675 = 10.088,87.
    indicadores = Indicadores([serie(TipoIndicador.IPCA, (date(2025, 8, 1), "0.40"))])
    parametros = ParametrosRendaFixa(Indexador.IPCA, D(6), date(2025, 8, 1), date(2030, 1, 2))
    fator = criar_fator_renda_fixa(parametros, indicadores)
    assert arredondar_moeda(D(10000) * fator(date(2025, 8, 1), date(2025, 9, 1))) == D("10088.87")


def test_ipca_pro_rata_no_mes_parcial() -> None:
    # 01 a 14/08/2025 = 10 dos 21 dias úteis do mês:
    # 10.000 × 1,004^(10/21) × 1,06^(10/252) = 10.042,22.
    indicadores = Indicadores([serie(TipoIndicador.IPCA, (date(2025, 8, 1), "0.40"))])
    parametros = ParametrosRendaFixa(Indexador.IPCA, D(6), date(2025, 8, 1), date(2030, 1, 2))
    fator = criar_fator_renda_fixa(parametros, indicadores)
    assert arredondar_moeda(D(10000) * fator(date(2025, 8, 1), date(2025, 8, 15))) == D("10042.22")


def test_ipca_de_mes_nao_publicado_usa_o_ultimo_conhecido() -> None:
    # Setembro sem IPCA: usa o de agosto (0,40%). Dois meses completos = 1,004².
    ipca = serie(TipoIndicador.IPCA, (date(2025, 8, 1), "0.40"))
    assert fator_ipca(ipca, date(2025, 8, 1), date(2025, 10, 1)) == D("1.004") ** 2
    with pytest.raises(IndicadorAusenteError):
        fator_ipca(ipca, date(2025, 7, 1), date(2025, 8, 1))


def test_rendimento_para_no_vencimento() -> None:
    parametros = ParametrosRendaFixa(Indexador.PRE, D(12), date(2025, 1, 1), date(2025, 7, 1))
    fator = criar_fator_renda_fixa(parametros, Indicadores())
    no_vencimento = fator(date(2025, 1, 1), date(2025, 7, 1))
    assert fator(date(2025, 1, 1), date(2026, 1, 1)) == no_vencimento
    assert fator(date(2025, 8, 1), date(2026, 1, 1)) == UM  # aporte após o vencimento
    assert no_vencimento > UM


def test_renda_fixa_com_dois_aportes_e_resgate_proporcional() -> None:
    # Pré 12%: 1.000 em 01/01/2025 vale 1.120 em 01/01/2026 (252 d.u.).
    # Novo aporte de 1.000 em 01/01/2026 → saldo 2.120. Resgate de 1.060 = metade:
    # custo 2.000 → 1.000; lucro realizado = 1.060 − 1.000 = 60; saldo restante 1.060.
    parametros = ParametrosRendaFixa(Indexador.PRE, D(12), date(2025, 1, 1), date(2030, 1, 2))
    fator = criar_fator_renda_fixa(parametros, Indicadores())
    estado = aplicar_operacoes_montante(
        [
            Aporte(date(2025, 1, 1), D(1000), ordem=1),
            Aporte(date(2026, 1, 1), D(1000), ordem=2),
            Resgate(date(2026, 1, 1), D(1060), ordem=3),
        ],
        fator,
    )
    assert estado.valores.custo == D(1000)
    assert estado.valores.lucro_realizado == D(60)
    assert estado.valor_em(date(2026, 1, 1), fator) == D(1060)
    assert estado.valores.total_investido == D(2000)


# ---------------------------------------------------------------- Poupança


def test_taxa_mensal_da_poupanca() -> None:
    assert taxa_mensal_poupanca(D(15)) == D("0.005")  # Selic > 8,5%: 0,5% a.m.
    # Selic 8,5% (não é maior que 8,5): 70% → (1 + 0,0595)^(1/12) − 1 ≈ 0,4828% a.m.
    assert arredondar(taxa_mensal_poupanca(D("8.5")), 6) == D("0.004828")


def test_inicio_do_rendimento() -> None:
    assert inicio_rendimento(date(2025, 1, 28)) == date(2025, 1, 28)
    assert inicio_rendimento(date(2025, 1, 29)) == date(2025, 2, 1)
    assert inicio_rendimento(date(2025, 12, 31)) == date(2026, 1, 1)


def test_poupanca_rende_no_aniversario() -> None:
    # 1.000 em 10/01 com Selic 15%: 10/02 → 1.005,00; 10/03 → 1.005 × 1,005 = 1.010,025,
    # exibido como 1.010,02 (arredondamento bancário: o 5 exato vai para o par).
    selic = serie(TipoIndicador.SELIC, (date(2025, 1, 1), "15"))
    inicio = date(2025, 1, 10)
    assert fator_poupanca(selic, inicio, date(2025, 2, 9)) == UM
    assert fator_poupanca(selic, inicio, date(2025, 2, 10)) == D("1.005")
    valor = D(1000) * fator_poupanca(selic, inicio, date(2025, 3, 10))
    assert valor == D("1010.025")
    assert arredondar_moeda(valor) == D("1010.02")


def test_poupanca_deposito_no_dia_30_comeca_no_dia_primeiro() -> None:
    selic = serie(TipoIndicador.SELIC, (date(2025, 1, 1), "15"))
    assert fator_poupanca(selic, date(2025, 1, 30), date(2025, 2, 28)) == UM
    assert fator_poupanca(selic, date(2025, 1, 30), date(2025, 3, 1)) == D("1.005")


def test_poupanca_usa_selic_do_inicio_de_cada_periodo() -> None:
    # 1º mês com Selic 15% (0,5%); 2º mês começa com Selic 8% → 70%: taxa ≈ 0,4551%.
    selic = serie(TipoIndicador.SELIC, (date(2025, 1, 1), "15"), (date(2025, 2, 10), "8"))
    esperado = D("1.005") * (UM + taxa_mensal_poupanca(D(8)))
    assert fator_poupanca(selic, date(2025, 1, 10), date(2025, 3, 10)) == esperado
    assert arredondar(taxa_mensal_poupanca(D(8)), 6) == D("0.004551")


def test_poupanca_sem_selic_e_fator_com_cache() -> None:
    with pytest.raises(IndicadorAusenteError, match="Selic"):
        criar_fator_poupanca(Indicadores())(date(2025, 1, 10), date(2025, 2, 10))
    fator = criar_fator_poupanca(
        Indicadores([serie(TipoIndicador.SELIC, (date(2025, 1, 1), "15"))])
    )
    assert fator(date(2025, 1, 10), date(2025, 3, 10)) == D("1.010025")
    assert fator(date(2025, 1, 10), date(2025, 3, 10)) == D("1.010025")
