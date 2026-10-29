"""Repositórios: só acesso ao banco (filtros, ordenação e persistência)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.enums import (
    OrigemPreco,
    TipoEvento,
    TipoIndicador,
    TipoInstituicao,
    TipoLancamento,
    TipoMovimento,
    TipoTransacao,
)
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.repositories.configuracoes import RepositorioConfiguracoes
from app.repositories.contas import RepositorioContas, RepositorioMovimentos
from app.repositories.instituicoes import RepositorioInstituicoes
from app.repositories.lancamentos import RepositorioCategorias, RepositorioLancamentos
from app.repositories.mercado import RepositorioIndicadores, RepositorioPrecos
from app.repositories.transacoes import RepositorioEventos, RepositorioTransacoes

D = Decimal


def base(sessao: Session) -> tuple[m.Instituicao, m.Instituicao, m.Ativo]:
    repositorio = RepositorioInstituicoes(sessao)
    xp = repositorio.adicionar(m.Instituicao(nome="XP", tipo=TipoInstituicao.CORRETORA))
    rico = repositorio.adicionar(m.Instituicao(nome="RICO", tipo=TipoInstituicao.CORRETORA))
    ativo = RepositorioAtivos(sessao).adicionar(
        m.Ativo(tipo="acao_br", nome="Teste", simbolo="TST11", moeda="BRL")
    )
    return rico, xp, ativo


def transacao(ativo: m.Ativo, inst: m.Instituicao, dia: date) -> m.Transacao:
    return m.Transacao(
        ativo_id=ativo.id,
        instituicao_id=inst.id,
        tipo=TipoTransacao.COMPRA,
        data=dia,
        quantidade=D(1),
        preco_unitario=D(1),
        moeda="BRL",
        cambio=D(1),
    )


def test_instituicoes_e_ativos(sessao: Session) -> None:
    rico, xp, ativo = base(sessao)
    repositorio = RepositorioInstituicoes(sessao)
    assert repositorio.por_nome("rico") is rico
    assert repositorio.por_nome("Nubank") is None
    agora = repositorio.adicionar(m.Instituicao(nome="Ágora", tipo=TipoInstituicao.CORRETORA))
    assert repositorio.por_nome("ágora") is agora
    assert [i.nome for i in repositorio.listar()] == ["RICO", "XP", "Ágora"]
    assert repositorio.obter(xp.id) is xp
    ativos = RepositorioAtivos(sessao)
    assert ativos.por_tipo_e_simbolo("acao_br", "TST11") is ativo
    assert ativos.por_tipo_e_simbolo("acao_us", "TST11") is None
    assert ativos.listar() == [ativo]
    assert ativo.metadados == {}
    ativos.remover(ativo)
    assert ativos.listar() == []


def test_contas_e_movimentos(sessao: Session) -> None:
    rico, _, _ = base(sessao)
    contas = RepositorioContas(sessao)
    usd = contas.adicionar(m.ContaCorrente(instituicao_id=rico.id, moeda="USD"))
    brl = contas.adicionar(m.ContaCorrente(instituicao_id=rico.id, moeda="BRL"))
    assert contas.da_instituicao(rico.id, "USD") is usd
    assert contas.da_instituicao(rico.id, "EUR") is None
    assert contas.listar() == [brl, usd]
    movimentos = RepositorioMovimentos(sessao)
    for dia in (date(2025, 1, 5), date(2025, 1, 1), date(2025, 1, 9)):
        movimentos.adicionar(
            m.MovimentoConta(conta_id=brl.id, tipo=TipoMovimento.DEPOSITO, data=dia, valor=D(1))
        )
    assert [x.data.day for x in movimentos.da_conta(brl.id)] == [1, 5, 9]
    assert [x.data.day for x in movimentos.da_conta(brl.id, ate=date(2025, 1, 5))] == [1, 5]
    assert movimentos.da_transacao(123) == []


def test_transacoes_e_eventos(sessao: Session) -> None:
    rico, xp, ativo = base(sessao)
    repositorio = RepositorioTransacoes(sessao)
    t2 = repositorio.adicionar(transacao(ativo, rico, date(2025, 1, 2)))
    t1 = repositorio.adicionar(transacao(ativo, rico, date(2025, 1, 1)))
    t3 = repositorio.adicionar(transacao(ativo, xp, date(2025, 1, 3)))
    assert repositorio.da_posicao(ativo.id, rico.id) == [t1, t2]
    assert repositorio.da_posicao(ativo.id, rico.id, ate=date(2025, 1, 1)) == [t1]
    assert repositorio.listar_ate(date(2025, 1, 2)) == [t1, t2]
    assert repositorio.listar_ate() == [t1, t2, t3]
    assert repositorio.do_ativo(ativo.id) == [t1, t2, t3]

    eventos = RepositorioEventos(sessao)
    evento = eventos.adicionar(
        m.EventoCorporativo(
            ativo_id=ativo.id,
            tipo=TipoEvento.DESDOBRAMENTO,
            data=date(2025, 2, 1),
            proporcao_de=1,
            proporcao_para=2,
        )
    )
    assert eventos.do_ativo(ativo.id) == [evento]
    assert eventos.do_ativo(ativo.id, ate=date(2025, 1, 31)) == []


def test_precos_e_indicadores(sessao: Session) -> None:
    _, _, ativo = base(sessao)
    precos = RepositorioPrecos(sessao)
    instante = datetime(2025, 1, 2, 15, tzinfo=UTC)
    preco = precos.adicionar(
        m.Preco(
            ativo_id=ativo.id,
            data=date(2025, 1, 2),
            data_hora=instante,
            valor=D(10),
            moeda="BRL",
            origem=OrigemPreco.MANUAL,
        )
    )
    assert precos.na_data(ativo.id, date(2025, 1, 2)) is preco
    assert precos.na_data(ativo.id, date(2025, 1, 3)) is None
    assert precos.ultimos(ativo.id, 5) == [preco]
    assert precos.do_ativo(ativo.id) == [preco]
    indicadores = RepositorioIndicadores(sessao)
    cdi = indicadores.adicionar(
        m.Indicador(tipo=TipoIndicador.CDI, data=date(2025, 1, 2), valor=D(14))
    )
    cambio = indicadores.adicionar(
        m.Indicador(tipo=TipoIndicador.CAMBIO, moeda="USD", data=date(2025, 1, 1), valor=D(6))
    )
    assert cdi.moeda == "BRL"  # padrão
    assert indicadores.na_data(TipoIndicador.CDI, "BRL", date(2025, 1, 2)) is cdi
    assert indicadores.na_data(TipoIndicador.CDI, "BRL", date(2025, 1, 3)) is None
    assert indicadores.listar() == [cambio, cdi]  # ordem: tipo, moeda, data


def test_categorias_e_lancamentos(sessao: Session) -> None:
    categorias = RepositorioCategorias(sessao)
    mercado = categorias.adicionar(m.Categoria(nome="Mercado", tipo=TipoLancamento.DESPESA))
    salario = categorias.adicionar(m.Categoria(nome="Salário", tipo=TipoLancamento.RECEITA))
    assert categorias.por_nome("mercado", TipoLancamento.DESPESA) is mercado
    assert categorias.por_nome("mercado", TipoLancamento.RECEITA) is None
    assert categorias.por_nome("SALÁRIO", TipoLancamento.RECEITA) is salario  # com acento
    assert categorias.listar() == [mercado, salario]  # ordem do tipo: despesa, receita

    lancamentos = RepositorioLancamentos(sessao)
    for dia in (date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 28), date(2025, 3, 1)):
        lancamentos.adicionar(
            m.Lancamento(
                tipo=TipoLancamento.DESPESA,
                data=dia,
                descricao="x",
                valor=D(1),
                categoria_id=mercado.id,
            )
        )
    assert [x.data for x in lancamentos.do_mes(2025, 2)] == [date(2025, 2, 1), date(2025, 2, 28)]
    assert lancamentos.existe_na_categoria(mercado.id)
    assert not lancamentos.existe_na_categoria(salario.id)


def test_configuracoes(sessao: Session) -> None:
    repositorio = RepositorioConfiguracoes(sessao)
    assert repositorio.valor("tema", "escuro") == "escuro"
    repositorio.gravar("intervalo", {"segundos": 60})
    assert repositorio.valor("intervalo") == {"segundos": 60}
    repositorio.gravar("intervalo", {"segundos": 30})
    sessao.commit()
    sessao.expire_all()
    assert repositorio.valor("intervalo") == {"segundos": 30}
    assert len(repositorio.listar()) == 1
