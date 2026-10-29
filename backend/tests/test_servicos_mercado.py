"""Preço diário, precedência de fontes de indicadores, configurações, agenda e defasagem."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.domain.agenda import (
    AGENDA_B3,
    AGENDA_CONTINUA,
    AGENDA_DIARIA,
    AGENDA_EUA,
    PREGAO_B3,
    precisa_coletar,
)
from app.domain.enums import OrigemPreco, TipoIndicador, TipoTransacao
from app.domain.erros import (
    ConflitoError,
    NaoEncontradoError,
    OperacaoNaoPermitidaError,
    ValidacaoError,
)
from app.domain.indicadores import PontoIndicador, SerieIndicador, aviso_indicador_defasado
from app.domain.precos import PontoPreco, SeriePrecos, instante_fechamento, variacao
from app.repositories.configuracoes import RepositorioConfiguracoes
from app.services.carteira import avaliar_carteira
from app.services.configuracoes import (
    alterar_configuracoes,
    obter_configuracoes,
    obter_intervalo,
)
from app.services.mercado import (
    editar_indicador,
    excluir_indicador,
    excluir_preco_manual,
    gravar_fechamentos,
    gravar_indicadores_automaticos,
    listar_indicadores,
    listar_precos,
    registrar_indicador,
    registrar_preco,
)
from tests.fabricas import D, acao_br, cdb, deposito, indicador, instituicao, montante, poupanca

SP = ZoneInfo("America/Sao_Paulo")
NY = ZoneInfo("America/New_York")
CINCO_MIN = timedelta(minutes=5)


def sp(ano: int, mes: int, dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(ano, mes, dia, hora, minuto, tzinfo=SP)


# ---------------------------------------------------------------- agenda


def test_agenda_intradiaria_respeita_o_intervalo() -> None:
    agora = sp(2026, 10, 29, 14)
    assert precisa_coletar(AGENDA_CONTINUA, None, agora, CINCO_MIN)
    assert not precisa_coletar(AGENDA_CONTINUA, agora - timedelta(minutes=4), agora, CINCO_MIN)
    # Folga de 30 s: o ciclo que acorda um pouco antes não pula a coleta.
    assert precisa_coletar(
        AGENDA_CONTINUA, agora - timedelta(minutes=4, seconds=31), agora, CINCO_MIN
    )
    assert precisa_coletar(AGENDA_CONTINUA, agora - CINCO_MIN, agora, CINCO_MIN)
    # Cripto roda 24 h (domingo de madrugada também).
    domingo = sp(2026, 11, 1, 3)
    assert precisa_coletar(AGENDA_CONTINUA, domingo - CINCO_MIN, domingo, CINCO_MIN)


def test_pregao_b3_e_ultimo_fechamento() -> None:
    assert PREGAO_B3.aberto(sp(2026, 10, 29, 10))
    assert PREGAO_B3.aberto(sp(2026, 10, 29, 17, 29))  # margem de 30 min
    assert not PREGAO_B3.aberto(sp(2026, 10, 29, 17, 30))
    assert not PREGAO_B3.aberto(sp(2026, 10, 29, 9, 59))
    assert not PREGAO_B3.aberto(sp(2026, 10, 31, 12))  # sábado
    assert not PREGAO_B3.aberto(sp(2026, 11, 2, 12))  # Finados
    assert PREGAO_B3.ultimo_fechamento(sp(2026, 10, 29, 9)) == sp(2026, 10, 28, 17, 30)
    assert PREGAO_B3.ultimo_fechamento(sp(2026, 10, 29, 18)) == sp(2026, 10, 29, 17, 30)
    # Segunda de Finados: o último fechamento é o de sexta.
    assert PREGAO_B3.ultimo_fechamento(sp(2026, 11, 2, 12)) == sp(2026, 10, 30, 17, 30)


def test_acoes_fora_do_pregao_so_coletam_para_pegar_o_fechamento() -> None:
    noite = sp(2026, 10, 29, 20)
    assert precisa_coletar(AGENDA_B3, sp(2026, 10, 29, 16, 50), noite, CINCO_MIN)
    assert not precisa_coletar(AGENDA_B3, sp(2026, 10, 29, 17, 31), noite, CINCO_MIN)
    madrugada = sp(2026, 10, 30, 2)
    assert not precisa_coletar(AGENDA_B3, sp(2026, 10, 29, 18), madrugada, CINCO_MIN)
    # Bolsa dos EUA: 9h30–16h de Nova York (17h30 de Brasília no horário de inverno de lá).
    ny_aberta = datetime(2026, 10, 29, 15, 59, tzinfo=NY)
    assert precisa_coletar(AGENDA_EUA, ny_aberta - CINCO_MIN, ny_aberta, CINCO_MIN)
    ny_fechada = datetime(2026, 10, 29, 18, tzinfo=NY)
    assert precisa_coletar(
        AGENDA_EUA, datetime(2026, 10, 29, 16, 10, tzinfo=NY), ny_fechada, CINCO_MIN
    )
    assert not precisa_coletar(
        AGENDA_EUA, datetime(2026, 10, 29, 16, 31, tzinfo=NY), ny_fechada, CINCO_MIN
    )


def test_agenda_diaria_usa_a_data_de_brasilia() -> None:
    # 23h de Brasília = 2h UTC do dia seguinte: ainda é o mesmo dia local.
    sucesso = sp(2026, 10, 29, 8)
    assert not precisa_coletar(AGENDA_DIARIA, sucesso, sp(2026, 10, 29, 23), CINCO_MIN)
    assert precisa_coletar(AGENDA_DIARIA, sucesso, sp(2026, 10, 30, 0, 1), CINCO_MIN)
    assert precisa_coletar(AGENDA_DIARIA, None, sucesso, CINCO_MIN)


# ---------------------------------------------------------------- domínio de preços


def test_variacao_e_preco_anterior() -> None:
    assert variacao(D("11"), D("10")) == D("0.1")
    assert variacao(D("9"), D("10")) == D("-0.1")
    assert variacao(D("9"), D("0")) is None
    serie = SeriePrecos(
        PontoPreco(instante_fechamento(dia), D(valor), OrigemPreco.AUTOMATICO)
        for dia, valor in [(date(2026, 10, 27), "10"), (date(2026, 10, 29), "11")]
    )
    anterior = serie.anterior_a(date(2026, 10, 29))
    assert anterior is not None
    assert anterior.valor == D("10")
    assert serie.anterior_a(date(2026, 10, 27)) is None
    assert instante_fechamento(date(2026, 10, 29)) == datetime(2026, 10, 29, 21, tzinfo=UTC)


# ---------------------------------------------------------------- preços


def test_um_preco_por_dia_atualizado_a_cada_coleta(sessao: Session) -> None:
    ativo = acao_br(sessao)
    primeiro = registrar_preco(
        sessao, ativo.id, sp(2026, 10, 29, 10), D("10"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    segundo = registrar_preco(
        sessao, ativo.id, sp(2026, 10, 29, 16), D("10.5"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    assert segundo is primeiro  # mesmo registro do dia
    assert (segundo.data, segundo.valor, segundo.data_hora) == (
        date(2026, 10, 29),
        D("10.5"),
        datetime(2026, 10, 29, 19, tzinfo=UTC),
    )
    # 23h30 de Brasília já é 30/10 em UTC, mas a data do preço é a local (29/10).
    noite = registrar_preco(
        sessao, ativo.id, sp(2026, 10, 29, 23, 30), D("10.6"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    assert noite is primeiro
    # Manual substitui o automático do dia e não volta a ser sobrescrito no mesmo dia.
    manual = registrar_preco(
        sessao, ativo.id, sp(2026, 10, 29, 23, 40), D("11"), OrigemPreco.MANUAL
    )
    assert (manual.origem, manual.provider, manual.valor) == (OrigemPreco.MANUAL, None, D("11"))
    mantido = registrar_preco(
        sessao, ativo.id, sp(2026, 10, 29, 23, 50), D("12"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    assert (mantido.origem, mantido.valor) == (OrigemPreco.MANUAL, D("11"))
    # No dia seguinte a coleta automática volta a valer.
    amanha = registrar_preco(
        sessao, ativo.id, sp(2026, 10, 30, 11), D("12"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    assert amanha.origem is OrigemPreco.AUTOMATICO
    pagina = listar_precos(sessao, ativo.id, None, None, limite=10, deslocamento=0)
    assert pagina.total == 2
    assert [p.data for p in pagina.itens] == [date(2026, 10, 30), date(2026, 10, 29)]


def test_preco_so_para_ativos_cotados_e_origem_valida(sessao: Session) -> None:
    titulo = cdb(sessao)
    with pytest.raises(OperacaoNaoPermitidaError, match="calculado pelo rendimento"):
        registrar_preco(sessao, titulo.id, sp(2026, 10, 29, 12), D("10"), OrigemPreco.MANUAL)
    ativo = acao_br(sessao)
    with pytest.raises(ValidacaoError, match="Preço calculado não é gravado"):
        registrar_preco(sessao, ativo.id, sp(2026, 10, 29, 12), D("10"), OrigemPreco.CALCULADO)
    with pytest.raises(NaoEncontradoError):
        listar_precos(sessao, 999, None, None, 10, 0)


def test_fechamentos_preenchem_e_corrigem_mas_nao_tocam_manual_nem_hoje(sessao: Session) -> None:
    ativo = acao_br(sessao)
    hoje = date(2026, 10, 29)
    registrar_preco(
        sessao, ativo.id, sp(2026, 10, 27, 11), D("9.9"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    registrar_preco(sessao, ativo.id, sp(2026, 10, 28, 12), D("8"), OrigemPreco.MANUAL)
    registrar_preco(
        sessao, ativo.id, sp(2026, 10, 29, 11), D("10.4"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    alterados = gravar_fechamentos(
        sessao,
        ativo,
        [
            (date(2026, 10, 26), D("9.5")),  # dia sem preço: insere às 18h
            (date(2026, 10, 27), D("10")),  # automático intradiário: corrige com o fechamento
            (date(2026, 10, 28), D("10.2")),  # manual: fica
            (hoje, D("10.3")),  # hoje: tratado pela cotação atual
        ],
        "yfinance",
        hoje,
    )
    assert alterados == 2
    valores = {
        p.data: (p.valor, p.origem, p.data_hora)
        for p in listar_precos(sessao, ativo.id, None, None, 10, 0).itens
    }
    assert valores[date(2026, 10, 26)] == (D("9.5"), OrigemPreco.AUTOMATICO, sp(2026, 10, 26, 18))
    assert valores[date(2026, 10, 27)][0] == D("10")
    assert valores[date(2026, 10, 28)][:2] == (D("8"), OrigemPreco.MANUAL)
    assert valores[hoje][0] == D("10.4")
    filtrada = listar_precos(sessao, ativo.id, date(2026, 10, 27), date(2026, 10, 28), 1, 1)
    assert filtrada.total == 2
    assert [p.data for p in filtrada.itens] == [date(2026, 10, 27)]


def test_excluir_somente_preco_manual(sessao: Session) -> None:
    ativo = acao_br(sessao)
    automatico = registrar_preco(
        sessao, ativo.id, sp(2026, 10, 28, 12), D("8"), OrigemPreco.AUTOMATICO, "yfinance"
    )
    manual = registrar_preco(sessao, ativo.id, sp(2026, 10, 29, 12), D("9"), OrigemPreco.MANUAL)
    with pytest.raises(OperacaoNaoPermitidaError, match="manualmente"):
        excluir_preco_manual(sessao, automatico.id)
    excluir_preco_manual(sessao, manual.id)
    assert listar_precos(sessao, ativo.id, None, None, 10, 0).total == 1
    with pytest.raises(NaoEncontradoError):
        excluir_preco_manual(sessao, manual.id)


# ---------------------------------------------------------------- indicadores


def test_precedencia_das_fontes_de_indicadores(sessao: Session) -> None:
    dia, outro = date(2026, 10, 28), date(2026, 10, 29)
    registrar_indicador(sessao, TipoIndicador.CAMBIO, date(2026, 10, 27), D("5.3"), "USD")
    pontos = [
        PontoIndicador(date(2026, 10, 27), D("5.31")),
        PontoIndicador(dia, D("5.36")),
        PontoIndicador(outro, D("5.37")),
    ]
    assert (
        gravar_indicadores_automaticos(sessao, TipoIndicador.CAMBIO, "USD", pontos, "yfinance") == 2
    )
    # Yahoo atualiza o próprio valor ao longo do dia.
    assert (
        gravar_indicadores_automaticos(
            sessao, TipoIndicador.CAMBIO, "USD", [PontoIndicador(outro, D("5.38"))], "yfinance"
        )
        == 1
    )
    # PTAX (prioridade maior) substitui o Yahoo; manual nunca é tocado.
    ptax = [PontoIndicador(date(2026, 10, 27), D("5.2")), PontoIndicador(dia, D("5.3655"))]
    assert gravar_indicadores_automaticos(sessao, TipoIndicador.CAMBIO, "USD", ptax, "bcb_sgs") == 1
    # Yahoo não volta a sobrescrever a PTAX.
    assert (
        gravar_indicadores_automaticos(
            sessao, TipoIndicador.CAMBIO, "USD", [PontoIndicador(dia, D("5.4"))], "yfinance"
        )
        == 0
    )
    assert [
        (i.data, i.valor, i.fonte) for i in listar_indicadores(sessao, TipoIndicador.CAMBIO, "usd")
    ] == [
        (date(2026, 10, 27), D("5.3"), "manual"),
        (dia, D("5.3655"), "bcb_sgs"),
        (outro, D("5.38"), "yfinance"),
    ]
    with pytest.raises(ValueError, match="desconhecida"):
        gravar_indicadores_automaticos(sessao, TipoIndicador.CDI, "BRL", [], "outra")
    with pytest.raises(ValidacaoError, match="dia 1º"):
        gravar_indicadores_automaticos(
            sessao, TipoIndicador.IPCA, "BRL", [PontoIndicador(dia, D("0.4"))], "bcb_sgs"
        )


def test_lancamento_edicao_exclusao_e_filtros_de_indicadores(sessao: Session) -> None:
    cdi = registrar_indicador(sessao, TipoIndicador.CDI, date(2026, 10, 28), D("13.65"))
    assert cdi.fonte == "manual"
    with pytest.raises(ConflitoError, match="Já existe CDI registrado para 28/10/2026"):
        registrar_indicador(sessao, TipoIndicador.CDI, date(2026, 10, 28), D("13.7"))
    automatico = indicador(sessao, TipoIndicador.CDI, date(2026, 10, 29), "13.65")
    automatico.fonte = "bcb_sgs"
    editado = editar_indicador(sessao, automatico.id, D("13.66"))
    assert (editado.valor, editado.fonte) == (D("13.66"), "manual")  # edição vira manual
    with pytest.raises(ValidacaoError, match="negativa"):
        editar_indicador(sessao, cdi.id, D("-1"))
    with pytest.raises(ValidacaoError, match="8 casas"):
        registrar_indicador(sessao, TipoIndicador.IPCA, date(2026, 9, 1), D("0.123456789"))
    ipca = registrar_indicador(sessao, TipoIndicador.IPCA, date(2026, 9, 1), D("-0.11"))
    filtrados = listar_indicadores(sessao, inicio=date(2026, 10, 1), fim=date(2026, 10, 28))
    assert [i.id for i in filtrados] == [cdi.id]
    assert [i.id for i in listar_indicadores(sessao, TipoIndicador.IPCA)] == [ipca.id]
    excluir_indicador(sessao, ipca.id)
    with pytest.raises(NaoEncontradoError):
        excluir_indicador(sessao, ipca.id)
    with pytest.raises(NaoEncontradoError):
        editar_indicador(sessao, ipca.id, D("1"))
    with pytest.raises(ValidacaoError, match="caracteres"):
        registrar_indicador(sessao, TipoIndicador.CDI, date(2026, 1, 2), D("1"), fonte="x" * 41)


# ---------------------------------------------------------------- configurações


def test_intervalo_de_atualizacao(sessao: Session) -> None:
    assert obter_configuracoes(sessao).intervalo_atualizacao_min == 5  # padrão
    assert alterar_configuracoes(sessao, 1).intervalo_atualizacao_min == 1
    assert alterar_configuracoes(sessao, 15).intervalo_atualizacao_min == 15
    for invalido in (0, 16, True):
        with pytest.raises(ValidacaoError, match="de 1 a 15 minutos"):
            alterar_configuracoes(sessao, invalido)
    RepositorioConfiguracoes(sessao).gravar("intervalo_atualizacao_min", 99)  # editado à mão
    assert obter_intervalo(sessao) == 5


# ---------------------------------------------------------------- defasagem por indicador


def test_aviso_de_indicador_defasado() -> None:
    cdi = SerieIndicador(TipoIndicador.CDI, [PontoIndicador(date(2026, 10, 23), D("13.65"))])
    assert aviso_indicador_defasado(cdi, date(2026, 10, 27)) is None  # 4 dias: ok
    aviso = aviso_indicador_defasado(cdi, date(2026, 10, 28))
    assert aviso == (
        "CDI defasado: último registro em 23/10/2026; o valor usa o último indicador conhecido."
    )
    ipca = SerieIndicador(TipoIndicador.IPCA, [PontoIndicador(date(2026, 8, 1), D("0.3"))])
    assert aviso_indicador_defasado(ipca, date(2026, 10, 29)) is None  # agosto em outubro: ok
    assert aviso_indicador_defasado(ipca, date(2026, 11, 1)) is not None  # 3 meses
    vazio = SerieIndicador(TipoIndicador.SELIC, [])
    assert (
        aviso_indicador_defasado(vazio, date(2026, 1, 1))
        == "Não há Selic registrado até 01/01/2026."
    )


def test_renda_fixa_e_poupanca_ficam_defasadas_sem_indicador_recente(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "5000", date(2026, 1, 2))
    titulo = cdb(sessao, "cdi", "100", aplicacao=date(2026, 1, 5), vencimento=date(2026, 6, 1))
    pre = cdb(sessao, "pre", "12", aplicacao=date(2026, 1, 5), nome="CDB pré")
    conta = poupanca(sessao)
    montante(sessao, titulo, rico, TipoTransacao.APORTE, date(2026, 1, 5), "1000")
    montante(sessao, pre, rico, TipoTransacao.APORTE, date(2026, 1, 5), "1000")
    montante(sessao, conta, rico, TipoTransacao.APORTE, date(2026, 1, 5), "1000")
    indicador(sessao, TipoIndicador.CDI, date(2026, 1, 2), "14.9")
    indicador(sessao, TipoIndicador.SELIC, date(2026, 1, 2), "15")
    indicador(sessao, TipoIndicador.SELIC, date(2026, 10, 27), "13.75")

    def avaliacao(ativo_id: int, dia: date) -> tuple[bool, str | None]:
        carteira = avaliar_carteira(sessao, dia)
        posicao = next(p for p in carteira.posicoes if p.ativo_id == ativo_id)
        return posicao.avaliacao.defasado, posicao.avaliacao.aviso

    # CDI parado em 02/01: o CDB continua calculado, mas defasado, com aviso.
    defasado, aviso = avaliacao(titulo.id, date(2026, 3, 2))
    assert defasado is True
    assert aviso is not None
    assert "CDI defasado: último registro em 02/01/2026" in aviso
    # Depois do vencimento (01/06) o valor congela: o indicador só precisava ir até lá.
    indicador(sessao, TipoIndicador.CDI, date(2026, 5, 29), "14.9")
    assert avaliacao(titulo.id, date(2026, 10, 29)) == (False, None)
    assert avaliacao(pre.id, date(2026, 10, 29)) == (False, None)  # pré não usa indicador
    assert avaliacao(conta.id, date(2026, 10, 29)) == (False, None)  # Selic de 27/10
    defasada, aviso_poupanca = avaliacao(conta.id, date(2026, 11, 5))
    assert defasada is True
    assert aviso_poupanca is not None
    assert "Selic defasado" in aviso_poupanca
