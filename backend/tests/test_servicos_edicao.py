"""Edição e exclusão nos services (Parte 3): ativo, transação, evento, instituição e caixa."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.backup import criar_backup
from app.domain.enums import OrigemPreco, TipoEvento, TipoInstituicao, TipoTransacao
from app.domain.erros import (
    ConflitoError,
    NaoEncontradoError,
    OperacaoNaoPermitidaError,
    SaldoInsuficienteError,
    ValidacaoError,
)
from app.repositories import modelos as m
from app.repositories.mercado import RepositorioEstadosColeta
from app.services import backup as servico_backup
from app.services.ativos import EdicaoAtivo, editar_ativo, excluir_ativo
from app.services.cadastros import (
    NovoAtivo,
    criar_ativo,
    editar_instituicao,
    excluir_instituicao,
)
from app.services.caixa import extrato, listar_contas, saldo
from app.services.coleta import chave_ativo
from app.services.mercado import listar_precos, registrar_preco
from app.services.transacoes import (
    NovaTransacao,
    NovoEvento,
    editar_evento,
    editar_transacao,
    listar_eventos,
    listar_transacoes,
    registrar_evento,
    registrar_transacao,
)
from tests.fabricas import D, acao_br, cdb, compra, deposito, instituicao, montante, venda


def dados_compra(ativo: m.Ativo, inst: m.Instituicao, quantidade: str, dia: date) -> NovaTransacao:
    return NovaTransacao(
        ativo_id=ativo.id,
        instituicao_id=inst.id,
        tipo=TipoTransacao.COMPRA,
        data=dia,
        quantidade=D(quantidade),
        preco_unitario=D(10),
    )


# ---------------------------------------------------------------- ativos


def test_editar_ativo_campos_permitidos_e_reprocessamento(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "5000", date(2026, 1, 2))
    titulo = cdb(sessao, "pre", "12", aplicacao=date(2026, 1, 5))
    montante(sessao, titulo, rico, TipoTransacao.APORTE, date(2026, 1, 10), "1000")
    metadados = dict(titulo.metadados)
    editado = editar_ativo(
        sessao,
        titulo.id,
        EdicaoAtivo(nome=" CDB Novo ", metadados={**metadados, "taxa": "13"}),
    )
    assert (editado.nome, editado.metadados["taxa"]) == ("CDB Novo", "13")
    # Aplicação depois do aporte deixaria o aporte inválido: recusa e nada muda.
    with pytest.raises(OperacaoNaoPermitidaError, match="anterior à aplicação"):
        editar_ativo(
            sessao,
            titulo.id,
            EdicaoAtivo(nome="CDB", metadados={**metadados, "data_aplicacao": "2026-01-20"}),
        )
    assert titulo.metadados["data_aplicacao"] == "2026-01-05"
    with pytest.raises(ValidacaoError):
        editar_ativo(sessao, titulo.id, EdicaoAtivo(nome="", metadados=metadados))


def test_mudar_identificacao_na_fonte_reinicia_a_coleta(sessao: Session) -> None:
    fundo = criar_ativo(
        sessao,
        NovoAtivo(tipo="fundo", nome="Fundo X", metadados={"cnpj": "11.222.333/0001-81"}),
    )
    instante = datetime(2026, 10, 28, 21, tzinfo=UTC)
    registrar_preco(sessao, fundo.id, instante, D("2.5"), OrigemPreco.AUTOMATICO, "cvm")
    registrar_preco(
        sessao, fundo.id, datetime(2026, 10, 27, 21, tzinfo=UTC), D("2.4"), OrigemPreco.MANUAL
    )
    RepositorioEstadosColeta(sessao).obter_ou_criar(chave_ativo(fundo.id), fundo.id)
    # Só a classe (não identifica na fonte): nada é apagado.
    editar_ativo(
        sessao,
        fundo.id,
        EdicaoAtivo(nome="Fundo X", metadados={"cnpj": "11222333000181", "classe": "acoes"}),
    )
    assert listar_precos(sessao, fundo.id, None, None, 10, 0).total == 2
    # CNPJ novo: preços automáticos e estado da coleta saem; o manual fica.
    editar_ativo(
        sessao, fundo.id, EdicaoAtivo(nome="Fundo X", metadados={"cnpj": "00017024000153"})
    )
    restantes = listar_precos(sessao, fundo.id, None, None, 10, 0).itens
    assert [(p.origem, p.valor) for p in restantes] == [(OrigemPreco.MANUAL, D("2.4"))]
    assert RepositorioEstadosColeta(sessao).obter(chave_ativo(fundo.id)) is None


def test_excluir_ativo_so_sem_transacoes_nem_eventos(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "1000", date(2026, 1, 2))
    com_compra, com_evento, livre = (
        acao_br(sessao, "AAA3"),
        acao_br(sessao, "BBB3"),
        acao_br(sessao, "CCC3"),
    )
    compra(sessao, com_compra, rico, date(2026, 1, 5), "1", "10")
    registrar_evento(
        sessao, NovoEvento(com_evento.id, TipoEvento.DESDOBRAMENTO, date(2026, 1, 5), 1, 2)
    )
    with pytest.raises(OperacaoNaoPermitidaError, match="transações"):
        excluir_ativo(sessao, com_compra.id)
    with pytest.raises(OperacaoNaoPermitidaError, match="eventos corporativos"):
        excluir_ativo(sessao, com_evento.id)
    registrar_preco(
        sessao, livre.id, datetime(2026, 1, 5, 15, tzinfo=UTC), D(1), OrigemPreco.MANUAL
    )
    excluir_ativo(sessao, livre.id)
    sessao.expire_all()
    assert sessao.query(m.Preco).filter_by(ativo_id=livre.id).count() == 0  # cascata
    with pytest.raises(NaoEncontradoError):
        excluir_ativo(sessao, livre.id)


# ---------------------------------------------------------------- transações


def test_editar_transacao_mantem_id_refaz_movimentos_e_passa_pelo_aviso(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "1000", date(2026, 1, 2))
    ativo = acao_br(sessao)
    original = registrar_transacao(sessao, dados_compra(ativo, rico, "50", date(2026, 1, 5)))
    assert original.transacao is not None
    transacao_id = original.transacao.id
    # 50 → 120 cotas: 1.200 > saldo 1.000 → aviso, sem alterar nada.
    aviso = editar_transacao(
        sessao, transacao_id, dados_compra(ativo, rico, "120", date(2026, 1, 5))
    )
    assert aviso.transacao is None
    assert aviso.aviso is not None
    assert aviso.aviso.valor_faltante == D("200.00")
    assert saldo(sessao, rico.id, "BRL", date(2026, 1, 5)) == D("500.00")
    aceito = editar_transacao(
        sessao,
        transacao_id,
        dados_compra(ativo, rico, "120", date(2026, 1, 5)),
        aceitar_ajuste=True,
    )
    assert aceito.transacao is not None
    assert aceito.transacao.id == transacao_id
    assert aceito.ajuste is not None
    assert aceito.ajuste.valor == D("200.00")
    assert saldo(sessao, rico.id, "BRL", date(2026, 1, 5)) == D("0.00")
    # Voltar para 50 remove o ajuste antigo (movimentos refeitos do zero): 1.000 − 500.
    editar_transacao(sessao, transacao_id, dados_compra(ativo, rico, "50", date(2026, 1, 5)))
    assert saldo(sessao, rico.id, "BRL", date(2026, 1, 5)) == D("500.00")


def test_editar_transacao_recusa_posicao_invalida_e_conta_antiga_negativa(sessao: Session) -> None:
    rico, xp = instituicao(sessao), instituicao(sessao, "XP")
    deposito(sessao, rico, "1000", date(2026, 1, 2))
    deposito(sessao, xp, "1000", date(2026, 1, 2))
    ativo = acao_br(sessao)
    base = registrar_transacao(sessao, dados_compra(ativo, rico, "50", date(2026, 1, 5)))
    assert base.transacao is not None
    venda(sessao, ativo, rico, date(2026, 1, 10), "40", "10")
    with pytest.raises(OperacaoNaoPermitidaError, match="Não é possível alterar esta transação"):
        editar_transacao(
            sessao, base.transacao.id, dados_compra(ativo, rico, "30", date(2026, 1, 5))
        )
    # Uma venda que credita a RICO e sustenta um saque: mudar a venda para a XP deixaria a
    # RICO negativa.
    credito = venda(sessao, ativo, rico, date(2026, 1, 11), "10", "100")
    assert credito.transacao is not None
    from app.domain.enums import TipoMovimento
    from app.services.caixa import NovoMovimentoManual, registrar_movimento_manual

    registrar_movimento_manual(
        sessao,
        NovoMovimentoManual(rico.id, "BRL", TipoMovimento.SAQUE, date(2026, 1, 12), D("1500")),
    )
    mover = NovaTransacao(
        ativo_id=ativo.id,
        instituicao_id=xp.id,
        tipo=TipoTransacao.VENDA,
        data=date(2026, 1, 11),
        quantidade=D(10),
        preco_unitario=D(100),
    )
    with pytest.raises(OperacaoNaoPermitidaError):  # XP não tem a posição para vender
        editar_transacao(sessao, credito.transacao.id, mover)
    compra(sessao, ativo, xp, date(2026, 1, 3), "10", "10")
    with pytest.raises(SaldoInsuficienteError, match="conta corrente anterior"):
        editar_transacao(sessao, credito.transacao.id, mover)
    with pytest.raises(ValidacaoError, match="ativo de uma transação"):
        editar_transacao(
            sessao,
            credito.transacao.id,
            dados_compra(acao_br(sessao, "OUT3"), rico, "1", date(2026, 1, 5)),
        )


def test_listar_transacoes_paginado(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "10000", date(2026, 1, 2))
    ativo = acao_br(sessao)
    for dia in (5, 6, 7):
        compra(sessao, ativo, rico, date(2026, 1, dia), "1", "10")
    pagina = listar_transacoes(sessao, limite=2, deslocamento=0)
    assert pagina.total == 3
    assert [t.data.day for t in pagina.itens] == [7, 6]
    filtrada = listar_transacoes(sessao, inicio=date(2026, 1, 6), fim=date(2026, 1, 6))
    assert [t.data.day for t in filtrada.itens] == [6]


# ---------------------------------------------------------------- eventos


def test_editar_evento(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "1000", date(2026, 1, 2))
    ativo = acao_br(sessao)
    compra(sessao, ativo, rico, date(2026, 1, 5), "10", "10")
    evento = registrar_evento(
        sessao, NovoEvento(ativo.id, TipoEvento.DESDOBRAMENTO, date(2026, 1, 10), 1, 2)
    )
    outro = registrar_evento(
        sessao, NovoEvento(ativo.id, TipoEvento.BONIFICACAO, date(2026, 1, 20), 10, 11)
    )
    venda(sessao, ativo, rico, date(2026, 2, 5), "15", "10")  # só possível com o desdobro
    with pytest.raises(OperacaoNaoPermitidaError, match="Não é possível alterar este evento"):
        editar_evento(
            sessao,
            evento.id,
            NovoEvento(ativo.id, TipoEvento.DESDOBRAMENTO, date(2026, 3, 1), 1, 2),
        )
    with pytest.raises(ConflitoError):
        editar_evento(
            sessao,
            outro.id,
            NovoEvento(ativo.id, TipoEvento.DESDOBRAMENTO, date(2026, 1, 10), 1, 3),
        )
    alterado = editar_evento(
        sessao, evento.id, NovoEvento(ativo.id, TipoEvento.DESDOBRAMENTO, date(2026, 1, 10), 1, 3)
    )
    assert (alterado.id, alterado.proporcao_para) == (evento.id, 3)
    assert [e.id for e in listar_eventos(sessao, ativo.id)] == [outro.id, evento.id]
    with pytest.raises(NaoEncontradoError):
        editar_evento(
            sessao, 999, NovoEvento(ativo.id, TipoEvento.DESDOBRAMENTO, date(2026, 1, 10), 1, 2)
        )


# ---------------------------------------------------------------- instituições e caixa


def test_editar_e_excluir_instituicao(sessao: Session) -> None:
    rico, xp = instituicao(sessao), instituicao(sessao, "XP")
    with pytest.raises(ConflitoError):
        editar_instituicao(sessao, xp.id, "rico", TipoInstituicao.BANCO)
    assert (
        editar_instituicao(sessao, xp.id, "XP Inc", TipoInstituicao.BANCO).tipo
        is TipoInstituicao.BANCO
    )
    deposito(sessao, rico, "100", date(2026, 1, 2))
    with pytest.raises(OperacaoNaoPermitidaError, match="depósitos ou saques"):
        excluir_instituicao(sessao, rico.id)
    ativo = acao_br(sessao)
    compra(sessao, ativo, xp, date(2026, 1, 5), "1", "10")  # com ajuste de saldo
    with pytest.raises(OperacaoNaoPermitidaError, match="transações"):
        excluir_instituicao(sessao, xp.id)
    vazia = instituicao(sessao, "Vazia")
    from app.services.caixa import obter_ou_criar_conta

    obter_ou_criar_conta(sessao, vazia.id, "USD")  # conta sem movimentos sai junto
    excluir_instituicao(sessao, vazia.id)
    assert [c.conta.instituicao_id for c in listar_contas(sessao, date(2026, 1, 5))] == [
        rico.id,
        xp.id,
    ]


def test_extrato_paginado(sessao: Session) -> None:
    rico = instituicao(sessao)
    for dia in (2, 3, 4):
        deposito(sessao, rico, "10", date(2026, 1, dia))
    resultado = extrato(
        sessao,
        rico.id,
        "brl",
        inicio=date(2026, 1, 3),
        fim=None,
        hoje=date(2026, 1, 10),
        limite=1,
        deslocamento=0,
    )
    assert (resultado.total, resultado.saldo_final) == (2, D(30))
    assert [x.data.day for x in resultado.itens] == [4]
    with pytest.raises(NaoEncontradoError, match="USD"):
        extrato(
            sessao,
            rico.id,
            "USD",
            inicio=None,
            fim=None,
            hoje=date(2026, 1, 10),
            limite=1,
            deslocamento=0,
        )


# ---------------------------------------------------------------- backup


def test_restauracao_que_falha_volta_o_banco_anterior(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "teste.db"
    pasta = tmp_path / "backups"
    with Session(engine) as sessao:
        instituicao(sessao, "Antes")
        sessao.commit()
    from alembic import command

    from app.core import migracoes

    command.stamp(migracoes.configuracao_alembic(banco), "head")
    bom = criar_backup(banco, pasta, "manual")
    with Session(engine) as sessao:
        instituicao(sessao, "Depois")
        sessao.commit()

    def falhar(*_: object) -> None:
        raise migracoes.MigracaoError("falhou")

    monkeypatch.setattr(servico_backup, "migrar_banco", falhar)
    with pytest.raises(OperacaoNaoPermitidaError, match="dados anteriores foram mantidos"):
        servico_backup.restaurar(bom, banco, pasta, engine)
    with Session(engine) as sessao:
        assert {i.nome for i in sessao.query(m.Instituicao)} == {"Antes", "Depois"}
    nomes = [b.nome for b in servico_backup.listar_backups(pasta)]
    assert any(n.endswith("pre-restauracao.db") for n in nomes)
    assert servico_backup.listar_backups(tmp_path / "nao-existe") == []
