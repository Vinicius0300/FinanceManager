"""Avaliação da carteira (Análise Geral e por Instituição), série de patrimônio e financeiro."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.carteira import GRUPO_CAIXA
from app.domain.enums import (
    OrigemPreco,
    TipoIndicador,
    TipoInstituicao,
    TipoLancamento,
    TipoTransacao,
)
from app.domain.erros import (
    ConflitoError,
    NaoEncontradoError,
    OperacaoNaoPermitidaError,
    ValidacaoError,
)
from app.domain.numeros import ZERO, arredondar_moeda, dividir, percentual
from app.repositories import modelos as m
from app.services.carteira import avaliar_carteira
from app.services.financeiro import (
    NovoLancamento,
    criar_categoria,
    excluir_categoria,
    excluir_lancamento,
    obter_resumo_mensal,
    obter_totais_por_categoria,
    registrar_lancamento,
)
from app.services.patrimonio import _custo_nominal, serie_patrimonio
from tests.fabricas import (
    D,
    acao_br,
    acao_us,
    cdb,
    compra,
    deposito,
    indicador,
    instituicao,
    montante,
    poupanca,
    preco,
    provento,
    venda,
)

DATA_REF = date(2025, 9, 1)


class Cenario:
    """Carteira sintética usada nos testes de avaliação.

    - RICO: depósito 2.000; compra 90 TST11 @ 10 (−900); provento 45 → caixa 1.145.
    - XP: depósito 120; compra 10 TST11 @ 12 → caixa 0.
    - Avenue (USD): depósito US$ 1.100; compra 10 AAPL @ US$ 100, câmbio 5 → caixa US$ 100.
    - Banco X: depósito 10.000; aporte em CDB 100% CDI (01/08/2025) → caixa 0.
    - Em 01/09/2025: TST11 = 15; AAPL = US$ 120; câmbio = 5,50; CDI = 14,90% a.a.
    """

    def __init__(self, sessao: Session, *, com_cambio: bool = True, com_cdi: bool = True) -> None:
        self.rico = instituicao(sessao, "RICO")
        self.xp = instituicao(sessao, "XP")
        self.avenue = instituicao(sessao, "Avenue")
        self.banco = instituicao(sessao, "Banco X", TipoInstituicao.BANCO)
        self.tst = acao_br(sessao)
        self.aapl = acao_us(sessao)
        self.cdb = cdb(sessao)
        julho = date(2025, 7, 1)
        deposito(sessao, self.rico, "2000", julho)
        deposito(sessao, self.xp, "120", julho)
        deposito(sessao, self.avenue, "1100", julho, moeda="USD")
        deposito(sessao, self.banco, "10000", date(2025, 8, 1))
        compra(sessao, self.tst, self.rico, date(2025, 7, 2), "90", "10", aceitar_ajuste=False)
        compra(sessao, self.tst, self.xp, date(2025, 7, 2), "10", "12", aceitar_ajuste=False)
        compra(sessao, self.aapl, self.avenue, date(2025, 7, 2), "10", "100", cambio="5")
        provento(sessao, self.tst, self.rico, date(2025, 7, 10), "45")
        montante(sessao, self.cdb, self.banco, TipoTransacao.APORTE, date(2025, 8, 1), "10000")
        preco(sessao, self.tst, DATA_REF, "15")
        preco(sessao, self.aapl, DATA_REF, "120")
        if com_cambio:
            indicador(sessao, TipoIndicador.CAMBIO, julho, "5", moeda="USD")
            indicador(sessao, TipoIndicador.CAMBIO, DATA_REF, "5.5", moeda="USD")
        if com_cdi:
            indicador(sessao, TipoIndicador.CDI, julho, "14.90")


def test_analise_geral(sessao: Session) -> None:
    cenario = Cenario(sessao)
    geral = avaliar_carteira(sessao, DATA_REF).geral()
    por_ativo = {p.ativo_id: p for p in geral.posicoes}

    # TST11 consolidado: 100 ações, custo 900 + 120 = 1.020, PM 10,20, valor 100 × 15 = 1.500.
    tst = por_ativo[cenario.tst.id]
    assert tst.instituicao_id is None
    assert tst.quantidade == D(100)
    assert tst.preco_medio == D("10.2")
    assert tst.avaliacao.valor_brl == D(1500)
    assert tst.avaliacao.origem is OrigemPreco.MANUAL
    metricas = tst.metricas_brl
    assert metricas is not None
    # Rentabilidade total = (1.500 − 1.020 + 0 + 45) / 1.020 = 525 / 1.020 ≈ 51,47%.
    assert metricas.rentabilidade_total == dividir(D(525), D(1020))
    assert percentual(metricas.rentabilidade_total or ZERO) == D("51.47")

    # AAPL: 10 × US$ 120 = US$ 1.200 × 5,50 = R$ 6.600; custo R$ 5.000 (câmbio da compra).
    aapl = por_ativo[cenario.aapl.id]
    assert aapl.avaliacao.valor == D(1200)
    assert aapl.avaliacao.valor_brl == D("6600.0")
    assert aapl.valores_brl.custo == D(5000)

    # CDB: 10.000 × 1,149^(21/252) = 10.116,42 (origem calculado, sem quantidade).
    cdb_avaliado = por_ativo[cenario.cdb.id]
    assert cdb_avaliado.quantidade is None
    assert cdb_avaliado.avaliacao.origem is OrigemPreco.CALCULADO
    assert arredondar_moeda(cdb_avaliado.avaliacao.valor_brl or ZERO) == D("10116.42")

    # Caixa: RICO 1.145 + XP 0 + Avenue US$ 100 × 5,50 = 550 + Banco X 0 = 1.695.
    assert geral.caixa_brl == D(1695)
    # Patrimônio = 1.500 + 6.600 + 10.116,42 + 1.695 = 19.911,42.
    assert arredondar_moeda(geral.investimentos_brl) == D("18216.42")
    assert arredondar_moeda(geral.patrimonio_brl) == D("19911.42")
    assert geral.completo
    assert [f.grupo for f in geral.alocacao] == ["renda_fixa", "acao_us", GRUPO_CAIXA, "acao_br"]
    assert sum(f.percentual for f in geral.alocacao) == pytest.approx(Decimal(1))


def test_analise_por_instituicao(sessao: Session) -> None:
    cenario = Cenario(sessao)
    carteira = avaliar_carteira(sessao, DATA_REF)
    assert carteira.instituicoes == sorted(
        [cenario.rico.id, cenario.xp.id, cenario.avenue.id, cenario.banco.id]
    )
    rico = carteira.por_instituicao(cenario.rico.id)
    assert [(p.ativo_id, p.quantidade) for p in rico.posicoes] == [(cenario.tst.id, D(90))]
    # RICO: 90 × 15 = 1.350 investidos + 1.145 em caixa = 2.495.
    assert rico.investimentos_brl == D(1350)
    assert rico.caixa_brl == D(1145)
    assert rico.patrimonio_brl == D(2495)
    posicao = rico.posicoes[0]
    assert posicao.valores.proventos == D(45)  # o provento é da posição da RICO...
    xp = carteira.por_instituicao(cenario.xp.id)
    assert xp.posicoes[0].valores.proventos == ZERO  # ...e não da XP
    assert xp.patrimonio_brl == D(150)


def test_falha_de_cambio_ou_indicador_nao_derruba_a_carteira(sessao: Session) -> None:
    Cenario(sessao, com_cambio=False, com_cdi=False)
    geral = avaliar_carteira(sessao, DATA_REF).geral()
    assert not geral.completo
    erros = {p.tipo_ativo: p.avaliacao.erro for p in geral.posicoes}
    assert erros["acao_br"] is None
    assert "Câmbio USD/BRL indisponível" in (erros["acao_us"] or "")
    assert "CDI" in (erros["renda_fixa"] or "")
    # Patrimônio só com o que foi possível avaliar: TST11 1.500 + caixa em BRL 1.145.
    assert geral.patrimonio_brl == D(2645)
    avenue = next(c for c in geral.caixas if c.moeda == "USD")
    assert avenue.saldo_brl is None
    assert avenue.erro is not None


def test_cambio_antigo_e_usado_mas_marca_posicao_e_caixa_como_defasados(sessao: Session) -> None:
    # Regressão (code review): câmbio de 2020 avaliado em 2025 saía com defasado=False.
    # Tolerância de 4 dias (decisão do dono, igual às ações).
    avenue, aapl = instituicao(sessao, "Avenue"), acao_us(sessao)
    indicador(sessao, TipoIndicador.CAMBIO, date(2025, 8, 28), "4", moeda="USD")
    deposito(sessao, avenue, "150", date(2025, 8, 28), moeda="USD")
    compra(sessao, aapl, avenue, date(2025, 8, 28), "1", "100")
    preco(sessao, aapl, DATA_REF, "200")

    # 28/08 → 01/09: 4 dias, ainda vigente.
    em_dia = avaliar_carteira(sessao, DATA_REF)
    assert not em_dia.posicoes[0].avaliacao.defasado
    assert not em_dia.caixas[0].defasado

    # 28/08 → 02/09: 5 dias, defasado (valor continua calculado com o último câmbio).
    carteira = avaliar_carteira(sessao, DATA_REF + timedelta(days=1))
    posicao, conta = carteira.posicoes[0], carteira.caixas[0]
    assert posicao.avaliacao.valor_brl == D(800)
    assert posicao.avaliacao.defasado
    assert posicao.avaliacao.aviso == "Câmbio USD/BRL defasado: último registro em 28/08/2025."
    assert posicao.avaliacao.erro is None
    assert (conta.saldo_brl, conta.defasado) == (D(200), True)  # US$ 50 × 4
    assert conta.aviso == posicao.avaliacao.aviso
    assert carteira.geral().completo


def test_carteira_em_data_passada_ignora_o_futuro(sessao: Session) -> None:
    Cenario(sessao)
    passado = avaliar_carteira(sessao, date(2025, 7, 1)).geral()
    assert passado.posicoes == ()
    # Só os depósitos de 01/07: 2.000 + 120 + US$ 1.100 × 5 = 7.620.
    assert passado.caixa_brl == D(7620)


def test_ativo_sem_cotacao_entra_pelo_custo(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao, "SEM3")
    compra(sessao, tst, rico, date(2025, 7, 2), "10", "10", taxas="1")
    posicao = avaliar_carteira(sessao, DATA_REF).geral().posicoes[0]
    assert posicao.avaliacao.valor_brl == D(101)
    assert posicao.avaliacao.origem is OrigemPreco.CALCULADO
    assert posicao.avaliacao.defasado
    assert posicao.avaliacao.aviso == "Sem cotação registrada: usando o preço médio de compra."


def test_poupanca_na_carteira(sessao: Session) -> None:
    banco, conta = instituicao(sessao, "Banco X", TipoInstituicao.BANCO), poupanca(sessao)
    indicador(sessao, TipoIndicador.SELIC, date(2025, 1, 1), "15")
    montante(sessao, conta, banco, TipoTransacao.APORTE, date(2025, 1, 10), "1000")
    posicao = avaliar_carteira(sessao, date(2025, 3, 10)).geral().posicoes[0]
    # 1.000 × 1,005² = 1.010,025 (dois aniversários).
    assert posicao.avaliacao.valor_brl == D("1010.025")


# ---------------------------------------------------------------- Série de patrimônio


def test_serie_patrimonio_simples(sessao: Session) -> None:
    # Depósito 1.000 em 01/07; compra 10 @ 10 em 02/07; preço 12 a partir de 03/07.
    # investimentos: 0 | 100 (sem preço → custo) | 120 | 120
    # caixa:      1.000 | 900 | 900 | 900
    rico, tst = instituicao(sessao), acao_br(sessao)
    deposito(sessao, rico, "1000", date(2025, 7, 1))
    compra(sessao, tst, rico, date(2025, 7, 2), "10", "10")
    preco(sessao, tst, date(2025, 7, 3), "12")
    serie = serie_patrimonio(sessao, date(2025, 7, 1), date(2025, 7, 4))
    assert [(p.investimentos, p.caixa, p.patrimonio) for p in serie.pontos] == [
        (ZERO, D(1000), D(1000)),
        (D(100), D(900), D(1000)),
        (D(120), D(900), D(1020)),
        (D(120), D(900), D(1020)),
    ]
    assert [p.data for p in serie.pontos] == [date(2025, 7, d) for d in range(1, 5)]
    assert serie.avisos == ()


def test_serie_bate_com_a_avaliacao_em_cada_dia(sessao: Session) -> None:
    # Consistência: o patrimônio de cada dia da série é igual ao da avaliação naquele dia.
    Cenario(sessao)
    inicio, fim = date(2025, 7, 1), DATA_REF
    serie = serie_patrimonio(sessao, inicio, fim)
    assert len(serie.pontos) == (fim - inicio).days + 1
    for ponto in serie.pontos[::7] + serie.pontos[-1:]:
        geral = avaliar_carteira(sessao, ponto.data).geral()
        assert ponto.patrimonio == geral.patrimonio_brl, ponto.data


def test_serie_com_falhas_registra_avisos(sessao: Session) -> None:
    Cenario(sessao, com_cambio=False, com_cdi=False)
    serie = serie_patrimonio(sessao, date(2025, 8, 1), date(2025, 8, 2))
    assert any("CDB Banco X" in aviso and "valor aplicado" in aviso for aviso in serie.avisos)
    assert any("Conta Avenue (USD) fora da série" in aviso for aviso in serie.avisos)
    assert any(
        "AAPL" in aviso and "não há câmbio USD/BRL" in aviso and "custo em BRL" in aviso
        for aviso in serie.avisos
    )
    # Sem câmbio, a AAPL entra pelo custo em BRL (5.000); o CDB pelo valor aplicado (10.000);
    # TST11 sem preço até 01/09 entra pelo custo (900 + 120). Caixa em BRL: 1.145 + 0 + 0.
    assert serie.pontos[0].investimentos == D(5000) + D(10000) + D(1020)
    assert serie.pontos[0].caixa == D(1145)


def test_plano_b_da_serie_em_cotas_usa_o_valor_aplicado_em_brl(sessao: Session) -> None:
    # Regressão (code review): o plano B só entendia aporte/resgate e zerava ações.
    # Compra 10 @ US$ 100 + US$ 1 (câmbio 5) = R$ 5.005; venda 4 @ US$ 120 − US$ 1
    # (câmbio 6) = R$ 2.874 → resta R$ 2.131 aplicado. Proventos não entram.
    avenue, aapl = instituicao(sessao, "Avenue"), acao_us(sessao)
    compra(sessao, aapl, avenue, date(2025, 3, 3), "10", "100", taxas="1", cambio="5")
    venda(sessao, aapl, avenue, date(2025, 3, 10), "4", "120", taxas="1", cambio="6")
    provento(sessao, aapl, avenue, date(2025, 3, 12), "5", cambio="6")
    transacoes = list(sessao.scalars(select(m.Transacao).order_by(m.Transacao.id)))
    assert _custo_nominal(transacoes) == [
        (date(2025, 3, 3), D(5005)),
        (date(2025, 3, 10), D(2131)),
        (date(2025, 3, 12), D(2131)),
    ]


def test_serie_valor_aplicado_considera_resgates(sessao: Session) -> None:
    banco, titulo = instituicao(sessao, "Banco X", TipoInstituicao.BANCO), cdb(sessao)
    indicador(sessao, TipoIndicador.CDI, date(2025, 1, 1), "14.90")
    montante(sessao, titulo, banco, TipoTransacao.APORTE, date(2025, 8, 1), "1000")
    montante(sessao, titulo, banco, TipoTransacao.RESGATE, date(2025, 8, 4), "400")
    # Apaga o CDI depois: a série cai no plano B (aplicado − resgatado = 600).
    sessao.query(m.Indicador).delete()
    serie = serie_patrimonio(sessao, date(2025, 8, 4), date(2025, 8, 4))
    assert serie.pontos[0].investimentos == D(600)


# ---------------------------------------------------------------- Receitas e despesas


def test_resumo_mensal_pelo_service(sessao: Session) -> None:
    salario = criar_categoria(sessao, "Salário", TipoLancamento.RECEITA)
    mercado = criar_categoria(sessao, " Mercado ", TipoLancamento.DESPESA)
    assert mercado.nome == "Mercado"
    marco = date(2025, 3, 5)
    registrar_lancamento(
        sessao, NovoLancamento(TipoLancamento.RECEITA, marco, "Salário", D(5000), salario.id)
    )
    registrar_lancamento(
        sessao, NovoLancamento(TipoLancamento.DESPESA, marco, "Feira", D("349.90"), mercado.id)
    )
    registrar_lancamento(
        sessao, NovoLancamento(TipoLancamento.DESPESA, marco, "Padaria", D("80.10"))
    )
    registrar_lancamento(
        sessao,
        NovoLancamento(TipoLancamento.DESPESA, date(2025, 4, 1), "Abril", D(999), mercado.id),
    )
    # Março: receitas 5.000; despesas 349,90 + 80,10 = 430; saldo 4.570.
    resumo = obter_resumo_mensal(sessao, 2025, 3)
    assert (resumo.total_receitas, resumo.total_despesas, resumo.saldo) == (
        D(5000),
        D("430.00"),
        D("4570.00"),
    )
    totais = obter_totais_por_categoria(sessao, 2025, 3)
    assert [(t.categoria_nome, t.total) for t in totais] == [
        ("Salário", D(5000)),
        ("Mercado", D("349.90")),
        ("Sem categoria", D("80.10")),
    ]


def test_validacoes_do_financeiro(sessao: Session) -> None:
    mercado = criar_categoria(sessao, "Mercado", TipoLancamento.DESPESA)
    with pytest.raises(ConflitoError):
        criar_categoria(sessao, "MERCADO", TipoLancamento.DESPESA)
    criar_categoria(sessao, "Mercado", TipoLancamento.RECEITA)  # mesmo nome, outro tipo
    with pytest.raises(ValidacaoError, match="nome da categoria"):
        criar_categoria(sessao, " ", TipoLancamento.DESPESA)
    with pytest.raises(ValidacaoError, match="no máximo 80"):
        criar_categoria(sessao, "x" * 81, TipoLancamento.DESPESA)
    dia = date(2025, 3, 1)
    with pytest.raises(ValidacaoError, match="é de despesa, não de receita"):
        registrar_lancamento(
            sessao, NovoLancamento(TipoLancamento.RECEITA, dia, "x", D(1), mercado.id)
        )
    with pytest.raises(NaoEncontradoError):
        registrar_lancamento(sessao, NovoLancamento(TipoLancamento.DESPESA, dia, "x", D(1), 999))
    with pytest.raises(ValidacaoError, match="descrição"):
        registrar_lancamento(sessao, NovoLancamento(TipoLancamento.DESPESA, dia, "  ", D(1)))
    with pytest.raises(ValidacaoError, match="no máximo 200"):
        registrar_lancamento(sessao, NovoLancamento(TipoLancamento.DESPESA, dia, "x" * 201, D(1)))
    with pytest.raises(ValidacaoError, match="maior que zero"):
        registrar_lancamento(sessao, NovoLancamento(TipoLancamento.DESPESA, dia, "x", ZERO))
    with pytest.raises(ValidacaoError, match="no máximo 2 casas decimais"):
        registrar_lancamento(sessao, NovoLancamento(TipoLancamento.DESPESA, dia, "x", D("1.005")))
    with pytest.raises(ValidacaoError, match="no máximo 500"):
        registrar_lancamento(
            sessao, NovoLancamento(TipoLancamento.DESPESA, dia, "x", D(1), observacao="x" * 501)
        )
    with pytest.raises(ValidacaoError, match="mês"):
        obter_resumo_mensal(sessao, 2025, 0)


def test_exclusoes_do_financeiro(sessao: Session) -> None:
    mercado = criar_categoria(sessao, "Mercado", TipoLancamento.DESPESA)
    lancamento = registrar_lancamento(
        sessao,
        NovoLancamento(
            TipoLancamento.DESPESA, date(2025, 3, 1), "Feira", D(10), mercado.id, " obs "
        ),
    )
    assert lancamento.observacao == "obs"
    with pytest.raises(OperacaoNaoPermitidaError, match="tem lançamentos"):
        excluir_categoria(sessao, mercado.id)
    excluir_lancamento(sessao, lancamento.id)
    excluir_categoria(sessao, mercado.id)
    with pytest.raises(NaoEncontradoError):
        excluir_categoria(sessao, mercado.id)
    with pytest.raises(NaoEncontradoError):
        excluir_lancamento(sessao, lancamento.id)


def test_ajuste_na_data_aparece_no_dia_seguinte_da_serie(sessao: Session) -> None:
    # Compra sem saldo (ajuste automático) não altera o patrimônio: −100 de caixa
    # compensado por +100 de ajuste e +100 investidos pelo custo.
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 7, 2), "10", "10")
    serie = serie_patrimonio(sessao, date(2025, 7, 1), date(2025, 7, 2) + timedelta(days=1))
    assert [p.patrimonio for p in serie.pontos] == [ZERO, D(100), D(100)]
    assert [p.caixa for p in serie.pontos] == [ZERO, ZERO, ZERO]
