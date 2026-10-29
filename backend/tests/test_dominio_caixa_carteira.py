"""Conta corrente (caixa), métricas, consolidação, alocação, série e resumo mensal."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.carteira import (
    GRUPO_CAIXA,
    Avaliacao,
    PosicaoAvaliada,
    SaldoCaixa,
    calcular_alocacao,
    consolidar_por_ativo,
    resumir_carteira,
)
from app.domain.conta_corrente import (
    LancamentoCaixa,
    deficit,
    menor_saldo_a_partir,
    movimento_da_transacao,
    saldo_em,
    saldos_fim_do_dia,
    valor_com_sinal,
)
from app.domain.enums import OrigemPreco, TipoLancamento, TipoMovimento, TipoTransacao
from app.domain.erros import ValidacaoError
from app.domain.lancamentos import (
    NOME_SEM_CATEGORIA,
    Lancamento,
    resumo_mensal,
    totais_por_categoria,
)
from app.domain.metricas import calcular_metricas
from app.domain.montante import Aporte
from app.domain.numeros import UM, ZERO, dividir, percentual
from app.domain.posicao import Compra, ValoresPosicao, historico_posicao
from app.domain.serie_patrimonio import (
    montar_serie_patrimonio,
    serie_caixa,
    serie_degraus,
    serie_valor_cotas,
    serie_valor_montante,
)

D = Decimal


def dia(n: int, mes: int = 3) -> date:
    return date(2025, mes, n)


# ---------------------------------------------------------------- Conta corrente


def test_sinal_dos_movimentos() -> None:
    assert valor_com_sinal(TipoMovimento.DEPOSITO, D(10)) == D(10)
    assert valor_com_sinal(TipoMovimento.SAQUE, D(10)) == D(-10)
    assert valor_com_sinal(TipoMovimento.DEBITO_COMPRA, D(10)) == D(-10)
    assert valor_com_sinal(TipoMovimento.CREDITO_VENDA, D(10)) == D(10)
    assert valor_com_sinal(TipoMovimento.CREDITO_PROVENTO, D(10)) == D(10)
    assert valor_com_sinal(TipoMovimento.AJUSTE_SALDO, D(10)) == D(10)


def test_movimento_gerado_por_cada_tipo_de_transacao() -> None:
    # Compra debita q × p + taxas; venda credita q × p − taxas.
    compra = movimento_da_transacao(
        TipoTransacao.COMPRA, quantidade=D(10), preco_unitario=D(5), taxas=D(1)
    )
    assert compra == (TipoMovimento.DEBITO_COMPRA, D(51))
    venda = movimento_da_transacao(
        TipoTransacao.VENDA, quantidade=D(10), preco_unitario=D(5), taxas=D(1)
    )
    assert venda == (TipoMovimento.CREDITO_VENDA, D(49))
    assert movimento_da_transacao(TipoTransacao.APORTE, valor=D(7)) == (
        TipoMovimento.DEBITO_COMPRA,
        D(7),
    )
    assert movimento_da_transacao(TipoTransacao.RESGATE, valor=D(7)) == (
        TipoMovimento.CREDITO_VENDA,
        D(7),
    )
    assert movimento_da_transacao(TipoTransacao.PROVENTO, valor=D(7)) == (
        TipoMovimento.CREDITO_PROVENTO,
        D(7),
    )
    with pytest.raises(ValueError, match="quantidade"):
        movimento_da_transacao(TipoTransacao.COMPRA, valor=D(1))
    with pytest.raises(ValueError, match="valor"):
        movimento_da_transacao(TipoTransacao.APORTE)


def test_compra_e_venda_movimentam_o_caixa_em_centavos() -> None:
    # 3 cotas a R$ 1,234567 = 3,703701 → débito de R$ 3,70 (como no extrato).
    compra = movimento_da_transacao(
        TipoTransacao.COMPRA, quantidade=D(3), preco_unitario=D("1.234567")
    )
    assert compra == (TipoMovimento.DEBITO_COMPRA, D("3.70"))
    # 0,5 × 10,125 − 0,01 = 5,0525 → crédito de R$ 5,05 (arredondamento bancário).
    venda = movimento_da_transacao(
        TipoTransacao.VENDA, quantidade=D("0.5"), preco_unitario=D("10.125"), taxas=D("0.01")
    )
    assert venda == (TipoMovimento.CREDITO_VENDA, D("5.05"))
    # Compra a preço zero sem taxas: movimento de valor zero (o service não o grava).
    gratis = movimento_da_transacao(TipoTransacao.COMPRA, quantidade=D(1), preco_unitario=ZERO)
    assert gratis == (TipoMovimento.DEBITO_COMPRA, ZERO)


def test_exemplo_da_conta_rico_do_prompt() -> None:
    # 20/02 depósito +1.000 → 1.000; 01/03 compra 90 @ 10 −900 → 100;
    # 10/03 provento +45 → 145; 20/03 venda 40 @ 12 +480 → 625.
    # 25/03 compra 70 @ 11 = 770 > 625 → déficit de 145 (o ajuste que zera o saldo).
    lancamentos = [
        LancamentoCaixa(date(2025, 2, 20), D(1000)),
        LancamentoCaixa(dia(1), D(-900)),
        LancamentoCaixa(dia(10), D(45)),
        LancamentoCaixa(dia(20), D(480)),
    ]
    assert saldos_fim_do_dia(lancamentos) == [
        (date(2025, 2, 20), D(1000)),
        (dia(1), D(100)),
        (dia(10), D(145)),
        (dia(20), D(625)),
    ]
    nova_compra = LancamentoCaixa(dia(25), D(-770))
    assert deficit([*lancamentos, nova_compra], dia(25)) == D(145)
    ajuste = LancamentoCaixa(dia(25), D(145))
    assert saldo_em([*lancamentos, nova_compra, ajuste], dia(31)) == ZERO


def test_debito_retroativo_considera_os_saldos_futuros() -> None:
    # Depósito 100 em 01/03 e compra de 100 em 10/03 (saldo final 0).
    # Uma compra de 50 em 05/03 cabe no saldo daquele dia (100), mas deixa
    # o dia 10/03 em −50: o déficit é 50.
    lancamentos = [LancamentoCaixa(dia(1), D(100)), LancamentoCaixa(dia(10), D(-100))]
    assert deficit([*lancamentos, LancamentoCaixa(dia(5), D(-50))], dia(5)) == D(50)


def test_movimentos_do_mesmo_dia_se_compensam() -> None:
    lancamentos = [LancamentoCaixa(dia(1), D(-100)), LancamentoCaixa(dia(1), D(100))]
    assert deficit(lancamentos, dia(1)) == ZERO


def test_credito_nunca_gera_deficit_e_menor_saldo_sem_movimentos() -> None:
    assert deficit([LancamentoCaixa(dia(1), D(10))], dia(1)) == ZERO
    assert menor_saldo_a_partir([], dia(1)) == ZERO
    assert menor_saldo_a_partir([LancamentoCaixa(dia(1), D(10))], dia(5)) == D(10)


# ---------------------------------------------------------------- Métricas


def test_rentabilidade_total_exemplo_do_prompt() -> None:
    # Compra 100 @ 10 (1.000); provento 50; cotação 11 (valor 1.100):
    # valorização = 100 / 1.000 = 10%; rentabilidade total = (100 + 0 + 50) / 1.000 = 15%.
    valores = ValoresPosicao(custo=D(1000), total_investido=D(1000), proventos=D(50))
    metricas = calcular_metricas(D(1100), valores)
    assert metricas.lucro_nao_realizado == D(100)
    assert metricas.valorizacao == D("0.1")
    assert metricas.resultado_total == D(150)
    assert metricas.rentabilidade_total == D("0.15")


def test_rentabilidade_total_apos_venda_parcial() -> None:
    # Vende 50 @ 12 (lucro 100); restam 50 com custo 500, cotação 11 (valor 550):
    # (550 − 500 + 100 + 50) / 1.000 = 20%. O denominador é o total investido.
    valores = ValoresPosicao(
        custo=D(500), total_investido=D(1000), lucro_realizado=D(100), proventos=D(50)
    )
    metricas = calcular_metricas(D(550), valores)
    assert metricas.rentabilidade_total == D("0.2")
    assert metricas.valorizacao == D("0.1")


def test_rentabilidade_total_reconhece_bonificacao() -> None:
    # 100 @ 10 + bonificação com custo atribuído 40 (custo 1.040); cotação 12 (110 × 12 = 1.320):
    # resultado = (1.320 − 1.040) + 40 = 320 → 32% sobre os 1.000 investidos.
    valores = ValoresPosicao(custo=D(1040), total_investido=D(1000), rendimentos_bonificacao=D(40))
    assert calcular_metricas(D(1320), valores).rentabilidade_total == D("0.32")


def test_metricas_sem_custo_ou_sem_investimento() -> None:
    metricas = calcular_metricas(ZERO, ValoresPosicao())
    assert metricas.valorizacao is None
    assert metricas.rentabilidade_total is None
    vendida = calcular_metricas(ZERO, ValoresPosicao(total_investido=D(100), lucro_realizado=D(20)))
    assert vendida.valorizacao is None
    assert vendida.rentabilidade_total == D("0.2")


# ---------------------------------------------------------------- Consolidação e alocação


def posicao(
    instituicao_id: int,
    quantidade: str,
    custo: str,
    valor: str | None,
    *,
    ativo_id: int = 1,
    tipo: str = "acao_br",
    erro: str | None = None,
) -> PosicaoAvaliada:
    valores = ValoresPosicao(custo=D(custo), total_investido=D(custo))
    return PosicaoAvaliada(
        ativo_id=ativo_id,
        tipo_ativo=tipo,
        moeda="BRL",
        instituicao_id=instituicao_id,
        quantidade=D(quantidade),
        valores=valores,
        valores_brl=valores,
        avaliacao=Avaliacao(
            valor=D(valor) if valor else None,
            valor_brl=D(valor) if valor else None,
            preco_unitario=D(15),
            origem=OrigemPreco.MANUAL,
            erro=erro,
        ),
    )


def test_consolidar_mesmo_ativo_em_duas_instituicoes() -> None:
    # RICO: 90 ações, custo 900, valor 1.350; XP: 10 ações, custo 120, valor 150.
    # Geral: 100 ações, custo 1.020, PM 10,20, valor 1.500.
    geral = consolidar_por_ativo([posicao(1, "90", "900", "1350"), posicao(2, "10", "120", "150")])
    assert len(geral) == 1
    tst = geral[0]
    assert tst.instituicao_id is None
    assert tst.quantidade == D(100)
    assert tst.valores.custo == D(1020)
    assert tst.preco_medio == D("10.2")
    assert tst.avaliacao.valor_brl == D(1500)
    metricas = tst.metricas_brl
    assert metricas is not None
    assert metricas.rentabilidade_total == dividir(D(480), D(1020))


def test_consolidacao_propaga_erro_de_uma_instituicao() -> None:
    geral = consolidar_por_ativo(
        [posicao(1, "90", "900", "1350"), posicao(2, "10", "120", None, erro="Sem câmbio.")]
    )
    assert geral[0].avaliacao.valor_brl is None
    assert geral[0].avaliacao.erro == "Sem câmbio."
    assert geral[0].metricas is None


def test_alocacao_por_grupo() -> None:
    fatias = calcular_alocacao({"acao_br": D(600), GRUPO_CAIXA: D(400), "cripto": ZERO})
    assert [(f.grupo, f.valor, f.percentual) for f in fatias] == [
        ("acao_br", D(600), D("0.6")),
        (GRUPO_CAIXA, D(400), D("0.4")),
    ]
    assert calcular_alocacao({"acao_br": ZERO}) == ()


def test_resumo_da_carteira_com_caixa_e_falha() -> None:
    posicoes = [
        posicao(1, "90", "900", "1350"),
        posicao(2, "1", "100", None, ativo_id=2, tipo="acao_us", erro="Sem câmbio."),
    ]
    caixas = [SaldoCaixa(1, "BRL", D(150), D(150)), SaldoCaixa(3, "USD", D(10), None, "x")]
    resumo = resumir_carteira(posicoes, caixas)
    # Patrimônio = 1.350 (investimentos avaliados) + 150 (caixa em BRL) = 1.500.
    assert resumo.investimentos_brl == D(1350)
    assert resumo.caixa_brl == D(150)
    assert resumo.patrimonio_brl == D(1500)
    assert not resumo.completo
    assert [(f.grupo, percentual(f.percentual)) for f in resumo.alocacao] == [
        ("acao_br", D("90.00")),
        (GRUPO_CAIXA, D("10.00")),
    ]


def test_posicao_por_montante_sem_quantidade() -> None:
    valores = ValoresPosicao(custo=D(100), total_investido=D(100))
    montante = PosicaoAvaliada(
        1, "renda_fixa", "BRL", 1, None, valores, valores, Avaliacao(D(101), D(101))
    )
    assert montante.aberta
    assert montante.preco_medio is None
    assert not posicao(1, "0", "0", "0").aberta


# ---------------------------------------------------------------- Série de patrimônio (pandas)


def test_serie_degraus() -> None:
    pontos = [(dia(3), D(5)), (date(2025, 2, 1), D(1)), (dia(3), D(7))]
    serie = serie_degraus(pontos, dia(1), dia(5))
    # Ponto anterior ao início define o valor inicial; data repetida: vale o último.
    assert serie.tolist() == [D(1), D(1), D(7), D(7), D(7)]
    assert all(isinstance(v, Decimal) for v in serie)
    assert serie_degraus([], dia(1), dia(2), valor_inicial=None).tolist() == [None, None]
    with pytest.raises(ValueError, match="data final"):
        serie_degraus([], dia(2), dia(1))


def test_serie_de_posicao_em_cotas_em_brl() -> None:
    # Compra 10 @ 10 no dia 2; preços: 12 no dia 3 e 13 no dia 5.
    # Dia 1: sem posição (0); dia 2: sem preço → custo (100); dia 3: 120; dia 4: 120; dia 5: 130.
    historico = historico_posicao([Compra(dia(2), D(10), D(10))])
    serie = serie_valor_cotas(historico, [(dia(3), D(12)), (dia(5), D(13))], None, dia(1), dia(5))
    assert serie.tolist() == [ZERO, D(100), D(120), D(120), D(130)]


def test_serie_de_posicao_em_dolar_converte_pelo_cambio_do_dia() -> None:
    # 10 @ US$ 10 (câmbio da compra 5). Preço US$ 12 no dia 1. Câmbio: 5 (dia 1), 5,5 (dia 3).
    historico = historico_posicao([Compra(dia(1), D(10), D(10), cambio=D(5))])
    cambios = [(dia(1), D(5)), (dia(3), D("5.5"))]
    serie = serie_valor_cotas(historico, [(dia(1), D(12))], cambios, dia(1), dia(3))
    assert serie.tolist() == [D(600), D(600), D(660)]
    # Antes do primeiro câmbio usa o primeiro disponível.
    tardio = serie_valor_cotas(historico, [(dia(1), D(12))], [(dia(3), D(6))], dia(1), dia(3))
    assert tardio.tolist() == [D(720), D(720), D(720)]
    # Sem câmbio algum: custo em BRL (10 × 10 × 5 = 500).
    sem_cambio = serie_valor_cotas(historico, [(dia(1), D(12))], [], dia(1), dia(2))
    assert sem_cambio.tolist() == [D(500), D(500)]


def test_serie_de_montante_e_de_caixa() -> None:
    def dez_por_cento(inicio: date, fim: date) -> Decimal:
        return D("1.1") if fim > inicio else UM

    montante = serie_valor_montante([Aporte(dia(2), D(1000))], dez_por_cento, dia(1), dia(3))
    assert montante.tolist() == [ZERO, D(1000), D(1100)]

    lancamentos = [LancamentoCaixa(dia(2), D(100)), LancamentoCaixa(dia(4), D(-40))]
    caixa = serie_caixa(lancamentos, None, dia(1), dia(5))
    assert caixa is not None
    assert caixa.tolist() == [ZERO, D(100), D(100), D(60), D(60)]
    em_dolar = serie_caixa(lancamentos, [(dia(1), D(5))], dia(1), dia(2))
    assert em_dolar is not None
    assert em_dolar.tolist() == [ZERO, D(500)]
    assert serie_caixa(lancamentos, [], dia(1), dia(2)) is None


def test_montar_serie_patrimonio() -> None:
    invest = serie_degraus([(dia(1), D(100))], dia(1), dia(2))
    caixa = serie_degraus([(dia(2), D(50))], dia(1), dia(2))
    quadro = montar_serie_patrimonio([invest, invest], [caixa], dia(1), dia(2))
    assert quadro["investimentos"].tolist() == [D(200), D(200)]
    assert quadro["caixa"].tolist() == [ZERO, D(50)]
    assert quadro["patrimonio"].tolist() == [D(200), D(250)]
    vazio = montar_serie_patrimonio([], [], dia(1), dia(1))
    assert vazio["patrimonio"].tolist() == [ZERO]


# ---------------------------------------------------------------- Receitas e despesas


def lancamentos_marco() -> list[Lancamento]:
    return [
        Lancamento(dia(5), TipoLancamento.RECEITA, D(5000), 1, "Salário"),
        Lancamento(dia(20), TipoLancamento.RECEITA, D("250.50")),
        Lancamento(dia(10), TipoLancamento.DESPESA, D(1200), 2, "Moradia"),
        Lancamento(dia(12), TipoLancamento.DESPESA, D("349.90"), 3, "Mercado"),
        Lancamento(dia(28), TipoLancamento.DESPESA, D("80.10"), 3, "Mercado"),
        Lancamento(date(2025, 4, 1), TipoLancamento.DESPESA, D(999), 2, "Moradia"),
    ]


def test_resumo_mensal() -> None:
    # Receitas: 5.000 + 250,50 = 5.250,50. Despesas: 1.200 + 349,90 + 80,10 = 1.630,00.
    # Saldo: 5.250,50 − 1.630,00 = 3.620,50. O lançamento de abril fica de fora.
    resumo = resumo_mensal(lancamentos_marco(), 2025, 3)
    assert resumo.total_receitas == D("5250.50")
    assert resumo.total_despesas == D("1630.00")
    assert resumo.saldo == D("3620.50")


def test_totais_por_categoria() -> None:
    totais = totais_por_categoria(lancamentos_marco(), 2025, 3)
    assert [(t.tipo, t.categoria_nome, t.total) for t in totais] == [
        (TipoLancamento.RECEITA, "Salário", D(5000)),
        (TipoLancamento.RECEITA, NOME_SEM_CATEGORIA, D("250.50")),
        (TipoLancamento.DESPESA, "Moradia", D(1200)),
        (TipoLancamento.DESPESA, "Mercado", D("430.00")),
    ]
    # Moradia = 1.200 / 1.630 ≈ 73,62% das despesas.
    assert percentual(totais[2].percentual) == D("73.62")


def test_mes_vazio_e_mes_invalido() -> None:
    resumo = resumo_mensal([], 2025, 2)
    assert (resumo.total_receitas, resumo.total_despesas, resumo.saldo) == (ZERO, ZERO, ZERO)
    assert totais_por_categoria([], 2025, 2) == []
    with pytest.raises(ValidacaoError, match="mês"):
        resumo_mensal([], 2025, 13)
    with pytest.raises(ValidacaoError, match="Ano"):
        resumo_mensal([], 1800, 1)
    with pytest.raises(ValidacaoError):
        Lancamento(dia(1), TipoLancamento.DESPESA, ZERO)
