"""Services de cadastro, mercado, caixa, transações e eventos (com banco SQLite)."""

from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.conta_corrente import MENSAGEM_SALDO_INSUFICIENTE
from app.domain.enums import (
    OrigemPreco,
    SubtipoProvento,
    TipoEvento,
    TipoIndicador,
    TipoInstituicao,
    TipoMovimento,
    TipoTransacao,
)
from app.domain.erros import (
    CambioAusenteError,
    ConflitoError,
    IndicadorAusenteError,
    NaoEncontradoError,
    OperacaoNaoPermitidaError,
    PosicaoInsuficienteError,
    SaldoInsuficienteError,
    ValidacaoError,
)
from app.domain.numeros import ZERO
from app.domain.posicao import EstadoPosicao
from app.repositories import modelos as m
from app.services import caixa
from app.services.cadastros import NovoAtivo, criar_ativo, criar_instituicao, obter_ativo
from app.services.mercado import (
    carregar_indicadores,
    carregar_precos,
    registrar_indicador,
    registrar_preco,
)
from app.services.posicoes import estado_cotas
from app.services.transacoes import (
    NovaTransacao,
    NovoEvento,
    excluir_evento,
    excluir_transacao,
    registrar_evento,
    registrar_transacao,
)
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
    provento,
    saque,
    venda,
)


def contar(sessao: Session, modelo: type[m.Base]) -> int:
    return sessao.scalar(select(func.count()).select_from(modelo)) or 0


def estado(sessao: Session, ativo: m.Ativo, inst: m.Instituicao) -> EstadoPosicao:
    transacoes = [
        t
        for t in sessao.scalars(select(m.Transacao))
        if t.instituicao_id == inst.id and t.ativo_id == ativo.id
    ]
    eventos = list(
        sessao.scalars(select(m.EventoCorporativo).where(m.EventoCorporativo.ativo_id == ativo.id))
    )
    return estado_cotas(transacoes, eventos)


# ---------------------------------------------------------------- Cadastros e mercado


def test_cadastro_de_instituicao(sessao: Session) -> None:
    rico = criar_instituicao(sessao, "  RICO ", TipoInstituicao.CORRETORA)
    assert rico.nome == "RICO"
    with pytest.raises(ConflitoError, match="Já existe uma instituição chamada 'rico'"):
        criar_instituicao(sessao, "rico", TipoInstituicao.BANCO)
    with pytest.raises(ValidacaoError, match="obrigatório"):
        criar_instituicao(sessao, "   ", TipoInstituicao.BANCO)
    with pytest.raises(ValidacaoError, match="no máximo 100"):
        criar_instituicao(sessao, "x" * 101, TipoInstituicao.BANCO)


def test_cadastro_de_ativo(sessao: Session) -> None:
    ativo = criar_ativo(
        sessao,
        NovoAtivo(
            tipo="acao_br", nome="Petrobras PN", simbolo=" petr4 ", simbolo_externo="PETR4.SA"
        ),
    )
    assert (ativo.simbolo, ativo.moeda, ativo.provider, ativo.metadados) == (
        "PETR4",
        "BRL",
        "yfinance",
        {},
    )
    assert ativo.simbolo_externo == "PETR4.SA"
    with pytest.raises(ConflitoError):
        criar_ativo(sessao, NovoAtivo(tipo="acao_br", nome="Outra", simbolo="PETR4"))
    # Mesmo símbolo em outro tipo é permitido.
    criar_ativo(sessao, NovoAtivo(tipo="cripto", nome="Fictício", simbolo="PETR4"))
    with pytest.raises(ValidacaoError, match="aceita apenas: USD"):
        criar_ativo(sessao, NovoAtivo(tipo="acao_us", nome="Apple", simbolo="AAPL", moeda="BRL"))
    with pytest.raises(ValidacaoError, match="Dados inválidos para Renda fixa"):
        criar_ativo(sessao, NovoAtivo(tipo="renda_fixa", nome="CDB", metadados={}))
    with pytest.raises(NaoEncontradoError):
        obter_ativo(sessao, 999)


def test_registro_de_precos(sessao: Session) -> None:
    ativo = acao_br(sessao)
    instante = datetime(2025, 1, 2, 15, tzinfo=UTC)
    preco = registrar_preco(sessao, ativo.id, instante, D(10), OrigemPreco.AUTOMATICO, "yfinance")
    assert preco.moeda == "BRL"
    assert preco.data == date(2025, 1, 2)
    with pytest.raises(ValidacaoError, match="provider"):
        registrar_preco(
            sessao, ativo.id, datetime(2025, 1, 3, tzinfo=UTC), D(1), OrigemPreco.AUTOMATICO
        )
    with pytest.raises(ValidacaoError, match="maior que zero"):
        registrar_preco(
            sessao, ativo.id, datetime(2025, 1, 3, tzinfo=UTC), ZERO, OrigemPreco.MANUAL
        )
    with pytest.raises(ValidacaoError, match="fuso"):
        registrar_preco(sessao, ativo.id, datetime(2025, 1, 3), D(1), OrigemPreco.MANUAL)
    serie = carregar_precos(sessao, ativo.id)
    ultimo = serie.ultimo_ate(date(2025, 1, 2))
    assert ultimo is not None
    assert ultimo.valor == D(10)


def test_registro_de_indicadores(sessao: Session) -> None:
    registrar_indicador(sessao, TipoIndicador.CDI, date(2025, 1, 2), D("14.90"))
    registrar_indicador(sessao, TipoIndicador.CAMBIO, date(2025, 1, 2), D("6.1"), "usd")
    registrar_indicador(sessao, TipoIndicador.IPCA, date(2025, 1, 1), D("-0.10"))  # deflação
    with pytest.raises(ConflitoError, match="Já existe CDI registrado para 02/01/2025"):
        registrar_indicador(sessao, TipoIndicador.CDI, date(2025, 1, 2), D(15))
    with pytest.raises(ValidacaoError, match="moeda estrangeira"):
        registrar_indicador(sessao, TipoIndicador.CAMBIO, date(2025, 1, 3), D(6))
    with pytest.raises(ValidacaoError, match="em BRL"):
        registrar_indicador(sessao, TipoIndicador.SELIC, date(2025, 1, 3), D(15), "USD")
    with pytest.raises(ValidacaoError, match="dia 1º"):
        registrar_indicador(sessao, TipoIndicador.IPCA, date(2025, 2, 15), D("0.3"))
    with pytest.raises(ValidacaoError, match="negativa"):
        registrar_indicador(sessao, TipoIndicador.CDI, date(2025, 1, 3), D(-1))
    with pytest.raises(ValidacaoError, match="câmbio deve ser maior"):
        registrar_indicador(sessao, TipoIndicador.CAMBIO, date(2025, 1, 3), ZERO, "USD")
    indicadores = carregar_indicadores(sessao)
    assert indicadores.cambio_em("USD", date(2025, 1, 5)) == D("6.1")
    assert indicadores.serie(TipoIndicador.CDI).valor_em(date(2025, 1, 2)) == D("14.90")


# ---------------------------------------------------------------- Conta corrente (prompt)


def test_exemplo_completo_da_conta_rico(sessao: Session) -> None:
    """Tabela do prompt: depósito, compra, provento, venda e compra com aviso + ajuste."""
    rico, tst = instituicao(sessao), acao_br(sessao)
    deposito(sessao, rico, "1000", date(2025, 2, 20))  # saldo 1.000
    compra(sessao, tst, rico, date(2025, 3, 1), "90", "10")  # −900 → 100
    provento(sessao, tst, rico, date(2025, 3, 10), "45")  # +45 → 145
    venda(sessao, tst, rico, date(2025, 3, 20), "40", "12")  # +480 → 625
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 20)) == D(625)

    # Compra 70 @ 11 = 770 > 625: sem aceitar o ajuste, só avisa e não grava nada.
    sem_ajuste = compra(sessao, tst, rico, date(2025, 3, 25), "70", "11", aceitar_ajuste=False)
    assert not sem_ajuste.gravada
    assert sem_ajuste.aviso is not None
    assert sem_ajuste.aviso.mensagem == MENSAGEM_SALDO_INSUFICIENTE
    assert sem_ajuste.aviso.valor_faltante == D(145)
    assert (sem_ajuste.aviso.instituicao_id, sem_ajuste.aviso.moeda) == (rico.id, "BRL")
    assert contar(sessao, m.Transacao) == 3

    # Usuário escolhe continuar: grava a compra e um ajuste de 145; o saldo fica em 0.
    com_ajuste = compra(sessao, tst, rico, date(2025, 3, 25), "70", "11", aceitar_ajuste=True)
    assert com_ajuste.gravada
    assert com_ajuste.ajuste is not None
    assert com_ajuste.ajuste.valor == D(145)
    assert com_ajuste.ajuste.tipo is TipoMovimento.AJUSTE_SALDO
    assert com_ajuste.ajuste.descricao == "Ajuste de saldo (depósito não informado)"
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 31)) == ZERO

    # Posição: 90 − 40 = 50 (custo 500) + 70 @ 11 (770) = 120 ações, custo 1.270.
    # Lucro realizado = (12 − 10) × 40 = 80; proventos 45 (fora do valor da posição).
    posicao = estado(sessao, tst, rico)
    assert posicao.quantidade == D(120)
    assert posicao.moeda.custo == D(1270)
    assert posicao.moeda.lucro_realizado == D(80)
    assert posicao.moeda.proventos == D(45)

    conta = caixa.obter_conta(sessao, rico.id, "BRL")
    assert conta is not None
    extrato = [(x.tipo, x.valor) for x in caixa.movimentos_da_conta(sessao, conta.id)]
    assert extrato == [
        (TipoMovimento.DEPOSITO, D(1000)),
        (TipoMovimento.DEBITO_COMPRA, D(900)),
        (TipoMovimento.CREDITO_PROVENTO, D(45)),
        (TipoMovimento.CREDITO_VENDA, D(480)),
        (TipoMovimento.DEBITO_COMPRA, D(770)),
        (TipoMovimento.AJUSTE_SALDO, D(145)),
    ]


def test_compra_sem_conta_cria_a_conta_e_ajusta_o_valor_todo(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    resultado = compra(sessao, tst, rico, date(2025, 3, 1), "10", "10", taxas="1")
    assert resultado.ajuste is not None
    assert resultado.ajuste.valor == D(101)  # 10 × 10 + 1 de taxa
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 1)) == ZERO


def test_compra_retroativa_que_estoura_saldo_futuro(sessao: Session) -> None:
    # Depósito 100 (01/03) e compra de 100 (10/03). Compra retroativa de 50 em 05/03:
    # o saldo de 10/03 ficaria −50 → aviso de 50.
    rico, tst = instituicao(sessao), acao_br(sessao)
    deposito(sessao, rico, "100", date(2025, 3, 1))
    compra(sessao, tst, rico, date(2025, 3, 10), "10", "10")
    resultado = compra(sessao, tst, rico, date(2025, 3, 5), "5", "10", aceitar_ajuste=False)
    assert resultado.aviso is not None
    assert resultado.aviso.valor_faltante == D(50)


# ---------------------------------------------------------------- Regras de posição


def test_venda_maior_que_a_posicao_nao_grava_nada(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "10", "10")
    with pytest.raises(PosicaoInsuficienteError):
        venda(sessao, tst, rico, date(2025, 3, 2), "11", "10")
    assert contar(sessao, m.Transacao) == 1


def test_venda_retroativa_que_invalida_venda_posterior(sessao: Session) -> None:
    # Compra 10 (01/03), vende 10 (03/03). Vender 5 em 02/03 deixaria a venda de 03/03
    # maior que a posição (5) → recusado.
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "10", "10")
    venda(sessao, tst, rico, date(2025, 3, 3), "10", "12")
    with pytest.raises(PosicaoInsuficienteError, match="03/03/2025"):
        venda(sessao, tst, rico, date(2025, 3, 2), "5", "11")


def test_posicao_e_independente_por_instituicao(sessao: Session) -> None:
    # TST11: 90 na RICO e 10 na XP. Vender 50 pela XP é recusado mesmo com 100 no total.
    rico, xp, tst = instituicao(sessao), instituicao(sessao, "XP"), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "90", "10")
    compra(sessao, tst, xp, date(2025, 3, 1), "10", "12")
    with pytest.raises(PosicaoInsuficienteError, match="disponível de 10"):
        venda(sessao, tst, xp, date(2025, 3, 2), "50", "12")
    venda(sessao, tst, rico, date(2025, 3, 2), "50", "12")
    assert estado(sessao, tst, rico).quantidade == D(40)
    assert estado(sessao, tst, xp).quantidade == D(10)


def test_provento_exige_compra_anterior_na_instituicao(sessao: Session) -> None:
    rico, xp, tst = instituicao(sessao), instituicao(sessao, "XP"), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 10), "10", "10")
    with pytest.raises(
        OperacaoNaoPermitidaError, match="Não há compra deste ativo nesta instituição"
    ):
        provento(sessao, tst, rico, date(2025, 3, 9), "5")
    with pytest.raises(OperacaoNaoPermitidaError):
        provento(sessao, tst, xp, date(2025, 3, 15), "5")
    # Provento pago depois de vender tudo (data com anterior à venda) é aceito.
    venda(sessao, tst, rico, date(2025, 3, 11), "10", "10")
    assert provento(sessao, tst, rico, date(2025, 3, 20), "5").gravada


def test_jcp_credita_o_liquido_e_guarda_o_imposto(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "100", "10")
    resultado = provento(
        sessao, tst, rico, date(2025, 3, 5), "85", imposto="15", subtipo=SubtipoProvento.JCP
    )
    transacao = resultado.transacao
    assert transacao is not None
    assert (transacao.valor, transacao.imposto_retido, transacao.subtipo_provento) == (
        D(85),
        D(15),
        SubtipoProvento.JCP,
    )
    movimentos = [(x.tipo, x.valor) for x in transacao.movimentos]
    assert movimentos == [(TipoMovimento.CREDITO_PROVENTO, D(85))]


@pytest.mark.parametrize(
    ("campos", "campo_com_erro"),
    [
        (
            {
                "tipo": TipoTransacao.COMPRA,
                "quantidade": D(1),
                "preco_unitario": D(1),
                "valor": D(1),
            },
            "valor",
        ),
        ({"tipo": TipoTransacao.COMPRA, "preco_unitario": D(1)}, "quantidade"),
        ({"tipo": TipoTransacao.COMPRA, "quantidade": D(1)}, "preco_unitario"),
        ({"tipo": TipoTransacao.PROVENTO, "valor": D(1)}, "subtipo_provento"),
        ({"tipo": TipoTransacao.PROVENTO, "quantidade": D(1), "valor": D(1)}, "quantidade"),
        ({"tipo": TipoTransacao.PROVENTO}, "valor"),
        (
            {
                "tipo": TipoTransacao.PROVENTO,
                "valor": D(1),
                "subtipo_provento": SubtipoProvento.JCP,
                "taxas": D(1),
            },
            "taxas",
        ),
        (
            {
                "tipo": TipoTransacao.COMPRA,
                "quantidade": D(1),
                "preco_unitario": D(1),
                "subtipo_provento": SubtipoProvento.JCP,
            },
            "subtipo_provento",
        ),
        (
            {
                "tipo": TipoTransacao.COMPRA,
                "quantidade": D(1),
                "preco_unitario": D(1),
                "imposto_retido": D(1),
            },
            "imposto_retido",
        ),
        (
            {
                "tipo": TipoTransacao.COMPRA,
                "quantidade": D(1),
                "preco_unitario": D(1),
                "observacao": "x" * 501,
            },
            "observacao",
        ),
        ({"tipo": TipoTransacao.COMPRA, "quantidade": D(0), "preco_unitario": D(1)}, "quantidade"),
        (
            {
                "tipo": TipoTransacao.COMPRA,
                "quantidade": D(1),
                "preco_unitario": D(1),
                "cambio": D(5),
            },
            "cambio",
        ),
    ],
)
def test_validacao_dos_campos_da_transacao(
    sessao: Session, campos: dict[str, object], campo_com_erro: str
) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "10", "10")
    dados = NovaTransacao(ativo_id=tst.id, instituicao_id=rico.id, data=date(2025, 3, 2), **campos)  # type: ignore[arg-type]
    with pytest.raises(ValidacaoError) as erro:
        registrar_transacao(sessao, dados)
    assert erro.value.detalhes[0].campo == campo_com_erro


def test_ativo_ou_instituicao_inexistente_e_tipo_nao_aceito(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    base = NovaTransacao(
        ativo_id=999,
        instituicao_id=rico.id,
        tipo=TipoTransacao.COMPRA,
        data=date(2025, 3, 1),
        quantidade=D(1),
        preco_unitario=D(1),
    )
    with pytest.raises(NaoEncontradoError, match="Ativo 999"):
        registrar_transacao(sessao, base)
    with pytest.raises(NaoEncontradoError, match="Instituição 999"):
        registrar_transacao(
            sessao,
            NovaTransacao(
                ativo_id=tst.id,
                instituicao_id=999,
                tipo=TipoTransacao.COMPRA,
                data=date(2025, 3, 1),
                quantidade=D(1),
                preco_unitario=D(1),
            ),
        )
    with pytest.raises(OperacaoNaoPermitidaError, match="não aceita transação do tipo aporte"):
        montante(sessao, tst, rico, TipoTransacao.APORTE, date(2025, 3, 1), "100")


def test_observacao_e_gravada_sem_espacos(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    resultado = registrar_transacao(
        sessao,
        NovaTransacao(
            ativo_id=tst.id,
            instituicao_id=rico.id,
            tipo=TipoTransacao.COMPRA,
            data=date(2025, 3, 1),
            quantidade=D(1),
            preco_unitario=D(1),
            observacao="  nota de corretagem 123  ",
        ),
        aceitar_ajuste=True,
    )
    assert resultado.transacao is not None
    assert resultado.transacao.observacao == "nota de corretagem 123"


# ---------------------------------------------------------------- Multimoeda


def test_compra_em_dolar_debita_conta_em_dolar_e_guarda_cambio(sessao: Session) -> None:
    avenue, aapl = instituicao(sessao, "Avenue"), acao_us(sessao)
    deposito(sessao, avenue, "1100", date(2025, 3, 1), moeda="USD")
    resultado = compra(sessao, aapl, avenue, date(2025, 3, 2), "10", "100", cambio="5.00")
    assert resultado.transacao is not None
    assert (resultado.transacao.moeda, resultado.transacao.cambio) == ("USD", D(5))
    assert caixa.saldo(sessao, avenue.id, "USD", date(2025, 3, 2)) == D(100)
    assert caixa.saldo(sessao, avenue.id, "BRL", date(2025, 3, 2)) == ZERO
    assert estado(sessao, aapl, avenue).brl.custo == D(5000)


def test_cambio_omitido_vem_dos_indicadores_com_tolerancia(sessao: Session) -> None:
    avenue, aapl = instituicao(sessao, "Avenue"), acao_us(sessao)
    indicador(sessao, TipoIndicador.CAMBIO, date(2025, 3, 1), "5.80", moeda="USD")
    resultado = compra(sessao, aapl, avenue, date(2025, 3, 5), "1", "100")
    assert resultado.transacao is not None
    assert resultado.transacao.cambio == D("5.80")
    with pytest.raises(CambioAusenteError, match="antigo demais"):
        compra(sessao, aapl, avenue, date(2025, 3, 20), "1", "100")


def test_cambio_ausente_e_invalido(sessao: Session) -> None:
    avenue, aapl = instituicao(sessao, "Avenue"), acao_us(sessao)
    with pytest.raises(CambioAusenteError, match="Câmbio USD/BRL indisponível"):
        compra(sessao, aapl, avenue, date(2025, 3, 5), "1", "100")
    with pytest.raises(ValidacaoError, match="câmbio deve ser maior"):
        compra(sessao, aapl, avenue, date(2025, 3, 5), "1", "100", cambio="-1")


# ---------------------------------------------------------------- Exclusão de transações


def test_nao_exclui_compra_que_sustenta_venda(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    primeira = compra(sessao, tst, rico, date(2025, 3, 1), "10", "10").transacao
    venda(sessao, tst, rico, date(2025, 3, 2), "10", "12")
    assert primeira is not None
    with pytest.raises(
        OperacaoNaoPermitidaError, match="Não é possível excluir esta transação: Venda de 10"
    ):
        excluir_transacao(sessao, primeira.id)


def test_nao_exclui_venda_cujo_dinheiro_foi_reinvestido(sessao: Session) -> None:
    # A venda credita 120; uma compra posterior usa esse dinheiro. Sem a venda, a conta
    # ficaria negativa → recusa.
    rico, tst, outra = instituicao(sessao), acao_br(sessao), acao_br(sessao, "OUT3")
    compra(sessao, tst, rico, date(2025, 3, 1), "10", "10")  # ajuste de 100
    vendida = venda(sessao, tst, rico, date(2025, 3, 2), "10", "12").transacao
    compra(sessao, outra, rico, date(2025, 3, 3), "12", "10", aceitar_ajuste=False)
    assert vendida is not None
    with pytest.raises(SaldoInsuficienteError, match="negativa em R\\$ 120"):
        excluir_transacao(sessao, vendida.id)


def test_excluir_compra_remove_movimentos_e_ajuste(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    deposito(sessao, rico, "50", date(2025, 3, 1))
    resultado = compra(sessao, tst, rico, date(2025, 3, 2), "10", "10")  # débito 100, ajuste 50
    assert resultado.transacao is not None
    assert contar(sessao, m.MovimentoConta) == 3
    excluir_transacao(sessao, resultado.transacao.id)
    assert contar(sessao, m.Transacao) == 0
    assert contar(sessao, m.MovimentoConta) == 1  # só o depósito
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 31)) == D(50)
    with pytest.raises(NaoEncontradoError):
        excluir_transacao(sessao, resultado.transacao.id)


# ---------------------------------------------------------------- Renda fixa pelos services


def test_aporte_e_resgate_de_cdb(sessao: Session) -> None:
    banco, titulo = instituicao(sessao, "Banco X", TipoInstituicao.BANCO), cdb(sessao)
    indicador(sessao, TipoIndicador.CDI, date(2025, 1, 1), "14.90")
    deposito(sessao, banco, "10000", date(2025, 8, 1))
    montante(sessao, titulo, banco, TipoTransacao.APORTE, date(2025, 8, 1), "10000")
    assert caixa.saldo(sessao, banco.id, "BRL", date(2025, 8, 1)) == ZERO
    # Em 01/09 o saldo estimado é 10.116,42; resgatar mais que isso é recusado.
    with pytest.raises(PosicaoInsuficienteError, match="10116,42"):
        montante(sessao, titulo, banco, TipoTransacao.RESGATE, date(2025, 9, 1), "10200")
    montante(sessao, titulo, banco, TipoTransacao.RESGATE, date(2025, 9, 1), "5000")
    assert caixa.saldo(sessao, banco.id, "BRL", date(2025, 9, 1)) == D(5000)


def test_renda_fixa_regras_de_data_taxas_e_indicador(sessao: Session) -> None:
    banco, titulo = instituicao(sessao, "Banco X", TipoInstituicao.BANCO), cdb(sessao)
    with pytest.raises(OperacaoNaoPermitidaError, match="anterior à aplicação"):
        montante(sessao, titulo, banco, TipoTransacao.APORTE, date(2025, 7, 1), "100")
    with pytest.raises(ValidacaoError, match="não aceitam taxas"):
        registrar_transacao(
            sessao,
            NovaTransacao(
                ativo_id=titulo.id,
                instituicao_id=banco.id,
                tipo=TipoTransacao.APORTE,
                data=date(2025, 8, 1),
                valor=D(100),
                taxas=D(1),
            ),
        )
    montante(sessao, titulo, banco, TipoTransacao.APORTE, date(2025, 8, 1), "100")
    with pytest.raises(IndicadorAusenteError, match="CDI"):
        montante(sessao, titulo, banco, TipoTransacao.RESGATE, date(2025, 9, 1), "50")


# ---------------------------------------------------------------- Eventos corporativos


def test_desdobramento_vale_para_todas_as_instituicoes(sessao: Session) -> None:
    rico, xp, tst = instituicao(sessao), instituicao(sessao, "XP"), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "90", "10")
    compra(sessao, tst, xp, date(2025, 3, 1), "10", "12")
    registrar_evento(sessao, NovoEvento(tst.id, TipoEvento.DESDOBRAMENTO, date(2025, 4, 1), 1, 2))
    assert estado(sessao, tst, rico).quantidade == D(180)
    assert estado(sessao, tst, xp).quantidade == D(20)
    assert estado(sessao, tst, xp).preco_medio == D(6)
    with pytest.raises(ConflitoError, match="Já existe desdobramento"):
        registrar_evento(
            sessao, NovoEvento(tst.id, TipoEvento.DESDOBRAMENTO, date(2025, 4, 1), 1, 3)
        )


def test_grupamento_que_invalida_venda_posterior_e_recusado(sessao: Session) -> None:
    # Compra 100; venda de 50 em 05/03. Grupamento 10:1 em 03/03 deixaria só 10 → recusa.
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "100", "10")
    venda(sessao, tst, rico, date(2025, 3, 5), "50", "10")
    with pytest.raises(PosicaoInsuficienteError):
        registrar_evento(sessao, NovoEvento(tst.id, TipoEvento.GRUPAMENTO, date(2025, 3, 3), 10, 1))
    assert contar(sessao, m.EventoCorporativo) == 0


def test_excluir_evento(sessao: Session) -> None:
    # Com desdobramento 1:2 a venda de 150 é válida; sem ele, não → exclusão recusada.
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "100", "10")
    evento = registrar_evento(
        sessao,
        NovoEvento(tst.id, TipoEvento.DESDOBRAMENTO, date(2025, 3, 2), 1, 2, observacao=" ex "),
    )
    assert evento.observacao == "ex"
    vendida = venda(sessao, tst, rico, date(2025, 3, 3), "150", "6").transacao
    with pytest.raises(OperacaoNaoPermitidaError, match="Não é possível excluir este evento"):
        excluir_evento(sessao, evento.id)
    assert vendida is not None
    excluir_transacao(sessao, vendida.id)
    excluir_evento(sessao, evento.id)
    assert contar(sessao, m.EventoCorporativo) == 0
    with pytest.raises(NaoEncontradoError):
        excluir_evento(sessao, evento.id)


def test_evento_invalido_em_renda_fixa_e_bonificacao_em_dolar(sessao: Session) -> None:
    titulo = cdb(sessao)
    with pytest.raises(OperacaoNaoPermitidaError, match="não tem eventos corporativos"):
        registrar_evento(
            sessao, NovoEvento(titulo.id, TipoEvento.DESDOBRAMENTO, date(2025, 9, 1), 1, 2)
        )
    tst = acao_br(sessao)
    with pytest.raises(ValidacaoError):
        registrar_evento(sessao, NovoEvento(tst.id, TipoEvento.GRUPAMENTO, date(2025, 9, 1), 1, 2))
    with pytest.raises(ValidacaoError, match="no máximo 500"):
        registrar_evento(
            sessao,
            NovoEvento(
                tst.id, TipoEvento.DESDOBRAMENTO, date(2025, 9, 1), 1, 2, observacao="x" * 501
            ),
        )

    # Bonificação com custo em ativo em dólar precisa do câmbio da data.
    avenue, aapl = instituicao(sessao, "Avenue"), acao_us(sessao)
    compra(sessao, aapl, avenue, date(2025, 3, 1), "100", "10", cambio="5")
    bonificacao = NovoEvento(
        aapl.id, TipoEvento.BONIFICACAO, date(2025, 4, 1), 10, 11, custo_unitario=D(4)
    )
    with pytest.raises(CambioAusenteError):
        registrar_evento(sessao, bonificacao)
    indicador(sessao, TipoIndicador.CAMBIO, date(2025, 4, 1), "5.5", moeda="USD")
    registrar_evento(sessao, bonificacao)
    # Custo: 100 × 10 × 5 = 5.000 + 10 novas × US$ 4 × 5,5 = 220 → R$ 5.220.
    assert estado(sessao, aapl, avenue).brl.custo == D(5220)


# ---------------------------------------------------------------- Caixa (movimentos manuais)


def test_deposito_e_saque(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "100", date(2025, 3, 1))
    saque(sessao, rico, "30", date(2025, 3, 5))
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 4)) == D(100)
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 5)) == D(70)
    assert caixa.saldo(sessao, rico.id, "USD", date(2025, 3, 5)) == ZERO  # conta inexistente
    with pytest.raises(
        SaldoInsuficienteError, match="Este saque deixaria a conta RICO \\(BRL\\) negativa"
    ):
        saque(sessao, rico, "71", date(2025, 3, 6))
    # Saque retroativo que deixaria o saldo negativo antes de um depósito futuro.
    with pytest.raises(SaldoInsuficienteError):
        saque(sessao, rico, "10", date(2025, 2, 1))


def test_movimento_manual_invalido(sessao: Session) -> None:
    rico = instituicao(sessao)
    with pytest.raises(OperacaoNaoPermitidaError, match="Só depósitos e saques"):
        caixa.registrar_movimento_manual(
            sessao,
            caixa.NovoMovimentoManual(
                rico.id, "BRL", TipoMovimento.AJUSTE_SALDO, date(2025, 3, 1), D(1)
            ),
        )
    with pytest.raises(ValidacaoError, match="maior que zero"):
        deposito(sessao, rico, "0", date(2025, 3, 1))
    with pytest.raises(ValidacaoError, match="no máximo 300"):
        caixa.registrar_movimento_manual(
            sessao,
            caixa.NovoMovimentoManual(
                rico.id, "BRL", TipoMovimento.DEPOSITO, date(2025, 3, 1), D(1), descricao="x" * 301
            ),
        )
    with pytest.raises(NaoEncontradoError):
        deposito(
            sessao,
            m.Instituicao(id=999, nome="?", tipo=TipoInstituicao.OUTRO),
            "1",
            date(2025, 3, 1),
        )
    mov = caixa.registrar_movimento_manual(
        sessao,
        caixa.NovoMovimentoManual(
            rico.id, "brl", TipoMovimento.DEPOSITO, date(2025, 3, 1), D(1), "  pix  "
        ),
    )
    assert mov.descricao == "pix"


def test_editar_e_excluir_ajuste_e_deposito(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    dep = deposito(sessao, rico, "60", date(2025, 3, 1))
    resultado = compra(sessao, tst, rico, date(2025, 3, 2), "10", "10")  # débito 100, ajuste 40
    assert resultado.ajuste is not None
    # Reduzir o ajuste deixaria a conta negativa; aumentá-lo é permitido.
    with pytest.raises(SaldoInsuficienteError, match="Este novo valor"):
        caixa.alterar_valor_movimento(sessao, resultado.ajuste.id, D(30))
    caixa.alterar_valor_movimento(sessao, resultado.ajuste.id, D(50))
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 2)) == D(10)
    # Excluir o depósito que sustenta a compra é recusado.
    with pytest.raises(SaldoInsuficienteError, match="Excluir este movimento"):
        caixa.excluir_movimento(sessao, dep.id)
    # Movimento automático não é editável diretamente.
    assert resultado.transacao is not None
    debito = next(
        x for x in resultado.transacao.movimentos if x.tipo is TipoMovimento.DEBITO_COMPRA
    )
    with pytest.raises(OperacaoNaoPermitidaError, match="gerado por uma transação"):
        caixa.excluir_movimento(sessao, debito.id)
    with pytest.raises(ValidacaoError):
        caixa.alterar_valor_movimento(sessao, dep.id, ZERO)
    with pytest.raises(NaoEncontradoError):
        caixa.excluir_movimento(sessao, 999)
    extra = deposito(sessao, rico, "5", date(2025, 3, 3))
    caixa.excluir_movimento(sessao, extra.id)
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 31)) == D(10)


# ---------------------------------------------------------------- Precisão das entradas


def test_entradas_com_casas_decimais_demais_sao_recusadas(sessao: Session) -> None:
    # Dinheiro 2 casas, quantidade e preço 8, câmbio 6 (decisão do dono, code review).
    rico, avenue = instituicao(sessao), instituicao(sessao, "Avenue")
    tst, aapl, titulo = acao_br(sessao), acao_us(sessao), cdb(sessao)
    deposito(sessao, rico, "1000", date(2025, 3, 1))
    casos: list[Callable[[], object]] = [
        lambda: deposito(sessao, rico, "100.005", date(2025, 3, 2)),
        lambda: compra(sessao, tst, rico, date(2025, 3, 2), "1.123456789", "10"),
        lambda: compra(sessao, tst, rico, date(2025, 3, 2), "1", "10.123456789"),
        lambda: compra(sessao, tst, rico, date(2025, 3, 2), "1", "10", taxas="0.001"),
        lambda: compra(sessao, aapl, avenue, date(2025, 3, 2), "1", "10", cambio="5.1234567"),
        lambda: montante(sessao, titulo, rico, TipoTransacao.APORTE, date(2025, 8, 1), "1.001"),
        lambda: provento(sessao, tst, rico, date(2025, 3, 2), "1.001"),
        lambda: registrar_preco(
            sessao,
            tst.id,
            datetime(2025, 3, 2, 15, tzinfo=UTC),
            D("1.123456789"),
            OrigemPreco.MANUAL,
        ),
        lambda: indicador(sessao, TipoIndicador.CAMBIO, date(2025, 3, 2), "5.1234567", "USD"),
        lambda: registrar_evento(
            sessao,
            NovoEvento(tst.id, TipoEvento.BONIFICACAO, date(2025, 4, 1), 10, 11, D("1.123456789")),
        ),
    ]
    for caso in casos:
        with pytest.raises(ValidacaoError, match="casas decimais"):
            caso()
    assert contar(sessao, m.Transacao) == 0
    assert contar(sessao, m.EventoCorporativo) == 0
    # Os limites exatos são aceitos (zeros à direita não contam).
    compra(sessao, tst, rico, date(2025, 3, 2), "1.12345678", "10.12345678", taxas="0.10")
    deposito(sessao, rico, "100.500", date(2025, 3, 3))


def test_compra_debita_o_caixa_em_centavos_e_o_custo_fica_cheio(sessao: Session) -> None:
    rico, fundo_tst = instituicao(sessao), acao_br(sessao)
    deposito(sessao, rico, "10", date(2025, 3, 1))
    compra(sessao, fundo_tst, rico, date(2025, 3, 2), "3", "1.234567")
    assert caixa.saldo(sessao, rico.id, "BRL", date(2025, 3, 2)) == D("6.30")  # 10 − 3,70
    assert estado(sessao, fundo_tst, rico).moeda.custo == D("3.703701")


def test_compra_a_preco_zero_nao_gera_movimento_de_caixa(sessao: Session) -> None:
    # Antes gravava um movimento de valor zero e violava o CHECK valor > 0.
    rico, tst = instituicao(sessao), acao_br(sessao)
    resultado = compra(sessao, tst, rico, date(2025, 3, 2), "10", "0")
    assert resultado.gravada
    assert contar(sessao, m.MovimentoConta) == 0
    assert estado(sessao, tst, rico).quantidade == D(10)


def test_cambio_da_bonificacao_fica_gravado_no_evento(sessao: Session) -> None:
    # Regressão (code review): cadastrar o câmbio do dia depois do evento mudava o custo
    # em BRL já registrado (5.050 → 5.060). Agora o câmbio fica no evento.
    avenue, msft = instituicao(sessao, "Avenue"), acao_us(sessao, "MSFT")
    indicador(sessao, TipoIndicador.CAMBIO, date(2025, 3, 3), "5", moeda="USD")
    compra(sessao, msft, avenue, date(2025, 3, 3), "10", "100", cambio="5")
    evento = registrar_evento(
        sessao, NovoEvento(msft.id, TipoEvento.BONIFICACAO, date(2025, 3, 5), 10, 11, D(10))
    )
    assert evento.cambio == D(5)  # buscado nos indicadores (até 7 dias)
    # 10 × 100 × 5 = 5.000 + 1 nova × US$ 10 × 5 = 50 → R$ 5.050.
    assert estado(sessao, msft, avenue).brl.custo == D(5050)
    indicador(sessao, TipoIndicador.CAMBIO, date(2025, 3, 5), "6", moeda="USD")
    assert estado(sessao, msft, avenue).brl.custo == D(5050)

    # Câmbio informado pelo usuário tem prioridade e segue o limite de 6 casas.
    informado = registrar_evento(
        sessao,
        NovoEvento(
            msft.id, TipoEvento.BONIFICACAO, date(2025, 3, 10), 10, 11, D(10), cambio=D("5.7")
        ),
    )
    assert informado.cambio == D("5.7")
    # Sem custo atribuído o câmbio não importa: não é buscado nem exigido.
    sem_cambio = acao_us(sessao, "NVDA")
    compra(sessao, sem_cambio, avenue, date(2025, 3, 3), "1", "10", cambio="5")
    desdobramento = registrar_evento(
        sessao, NovoEvento(sem_cambio.id, TipoEvento.DESDOBRAMENTO, date(2026, 1, 5), 1, 2)
    )
    assert desdobramento.cambio == D(1)
    with pytest.raises(ValidacaoError, match="BRL não usam câmbio"):
        registrar_evento(
            sessao,
            NovoEvento(
                acao_br(sessao).id, TipoEvento.DESDOBRAMENTO, date(2025, 3, 5), 1, 2, cambio=D(5)
            ),
        )
