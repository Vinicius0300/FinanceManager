"""Ciclo de coleta: agenda, histórico, falhas isoladas, fallback do câmbio e eventos.

Providers falsos (sem rede) e relógio fixo. Datas em Brasília (UTC−3, sem horário de
verão desde 2019): 29/10/2026 é uma quinta-feira, dia útil.
"""

from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.banco import criar_fabrica_sessoes, sessao_transacional
from app.domain.enums import OrigemPreco, TipoIndicador, TipoTransacao
from app.domain.indicadores import PontoIndicador
from app.providers.base import (
    AlvoCotacao,
    Cotacao,
    Fechamento,
    FonteIndisponivelError,
    PedidoHistorico,
    ResultadoCotacao,
    ResultadoHistorico,
    SimboloNaoEncontradoError,
)
from app.providers.registry import RegistroProviders
from app.repositories import modelos as m
from app.repositories.mercado import RepositorioEstadosColeta, RepositorioIndicadores
from app.services.coleta import (
    Coletor,
    EventoColeta,
    chave_ativo,
    chave_cambio_intradiario,
    chave_indicador,
    indicadores_necessarios,
)
from app.services.configuracoes import alterar_configuracoes
from app.services.mercado import registrar_indicador, registrar_preco
from tests.fabricas import D, acao_br, acao_us, cdb, compra, deposito, instituicao, montante

SP = ZoneInfo("America/Sao_Paulo")
HOJE = date(2026, 10, 29)


def em_sp(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=SP)


class Relogio:
    def __init__(self, inicio: datetime) -> None:
        self.agora = inicio

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, **kwargs: float) -> None:
        self.agora += timedelta(**kwargs)


class CotacaoFalsa:
    """Provider de cotação programável: preço por ativo, histórico e falhas."""

    def __init__(self, nome: str = "yfinance", persistente: bool = False) -> None:
        self.nome = nome
        self.identificador_persistente = persistente
        self.precos: dict[int, Decimal] = {}
        self.historico: dict[int, list[Fechamento]] = {}
        self.falha_cotacao: Exception | None = None
        self.chamadas_cotacao: list[list[int]] = []
        self.chamadas_historico: list[list[tuple[int, date]]] = []
        self.relogio: Callable[[], datetime] = lambda: em_sp(HOJE, 14)

    def identificar(self, alvo: AlvoCotacao) -> str:
        return alvo.simbolo_externo or f"id-{(alvo.simbolo or '').lower()}"

    def cotacoes(self, alvos: Sequence[AlvoCotacao]) -> dict[int, ResultadoCotacao]:
        self.chamadas_cotacao.append([a.ativo_id for a in alvos])
        if self.falha_cotacao is not None:
            raise self.falha_cotacao
        resultado: dict[int, ResultadoCotacao] = {}
        for alvo in alvos:
            if alvo.ativo_id in self.precos:
                instante = self.relogio().astimezone(UTC)
                resultado[alvo.ativo_id] = Cotacao(
                    instante.astimezone(SP).date(), instante, self.precos[alvo.ativo_id]
                )
            else:
                resultado[alvo.ativo_id] = SimboloNaoEncontradoError(f"{alvo.nome} não encontrado.")
        return resultado

    def historicos(
        self, pedidos: Sequence[PedidoHistorico], fim: date
    ) -> dict[int, ResultadoHistorico]:
        self.chamadas_historico.append([(p.alvo.ativo_id, p.inicio) for p in pedidos])
        return {
            p.alvo.ativo_id: [
                f for f in self.historico.get(p.alvo.ativo_id, []) if p.inicio <= f.data <= fim
            ]
            for p in pedidos
        }


class IndicadorFalso:
    def __init__(self, nome: str, suportados: set[tuple[TipoIndicador, str]]) -> None:
        self.nome = nome
        self.suportados = suportados
        self.series: dict[tuple[TipoIndicador, str], list[PontoIndicador]] = {}
        self.falha: Exception | None = None
        self.chamadas: list[tuple[TipoIndicador, str, date, date]] = []

    def suporta(self, tipo: TipoIndicador, moeda: str) -> bool:
        return (tipo, moeda) in self.suportados

    def serie(
        self, tipo: TipoIndicador, moeda: str, inicio: date, fim: date
    ) -> list[PontoIndicador]:
        self.chamadas.append((tipo, moeda, inicio, fim))
        if self.falha is not None:
            raise self.falha
        return [p for p in self.series.get((tipo, moeda), []) if inicio <= p.data <= fim]


class Cenario:
    def __init__(self, engine: Engine, inicio: datetime) -> None:
        self.fabrica: sessionmaker[Session] = criar_fabrica_sessoes(engine)
        self.relogio = Relogio(inicio)
        self.yahoo = CotacaoFalsa("yfinance")
        self.gecko = CotacaoFalsa("coingecko", persistente=True)
        self.yahoo.relogio = self.gecko.relogio = self.relogio
        self.sgs = IndicadorFalso(
            "bcb_sgs",
            {
                (TipoIndicador.CDI, "BRL"),
                (TipoIndicador.SELIC, "BRL"),
                (TipoIndicador.IPCA, "BRL"),
                (TipoIndicador.CAMBIO, "USD"),
            },
        )
        self.yahoo_cambio = IndicadorFalso("yfinance", {(TipoIndicador.CAMBIO, "USD")})
        self.providers = RegistroProviders()
        self.providers.registrar_cotacao(self.yahoo)
        self.providers.registrar_cotacao(self.gecko)
        self.providers.registrar_indicador(self.sgs)
        self.providers.registrar_indicador(self.yahoo_cambio)
        self.providers.registrar_cambio_intradiario(self.yahoo_cambio)
        self.eventos: list[EventoColeta] = []
        self.coletor = Coletor(
            self.fabrica, self.providers, relogio=self.relogio, publicar=self.eventos.append
        )

    def sessao(self) -> Iterator[Session]:
        with sessao_transacional(self.fabrica) as sessao:
            yield sessao

    def estado(self, chave: str) -> m.EstadoColeta | None:
        with sessao_transacional(self.fabrica) as sessao:
            return RepositorioEstadosColeta(sessao).obter(chave)

    def precos(self, ativo_id: int) -> list[tuple[date, Decimal, OrigemPreco, str | None]]:
        with sessao_transacional(self.fabrica) as sessao:
            registros = sessao.query(m.Preco).filter_by(ativo_id=ativo_id).order_by(m.Preco.data)
            return [(p.data, p.valor, p.origem, p.provider) for p in registros]

    def indicadores(
        self, tipo: TipoIndicador, moeda: str = "BRL"
    ) -> list[tuple[date, Decimal, str | None]]:
        with sessao_transacional(self.fabrica) as sessao:
            return [
                (i.data, i.valor, i.fonte)
                for i in RepositorioIndicadores(sessao).filtrar(tipo, moeda)
            ]

    def tipos_de_evento(self) -> list[str]:
        return [e.tipo for e in self.eventos]


@pytest.fixture
def cenario(engine: Engine) -> Cenario:
    return Cenario(engine, em_sp(HOJE, 14))  # pregão da B3 aberto


def preparar(cenario: Cenario, sessao_cb: object = None) -> dict[str, int]:
    """Instituição, PETR4 com compra em 02/03/2026 e saldo."""
    with sessao_transacional(cenario.fabrica) as sessao:
        rico = instituicao(sessao)
        deposito(sessao, rico, "10000", date(2026, 3, 1))
        petr = acao_br(sessao, "PETR4")
        compra(sessao, petr, rico, date(2026, 3, 2), "100", "30")
        return {"rico": rico.id, "petr": petr.id}


# ---------------------------------------------------------------- ativos cotados


def test_primeira_coleta_baixa_historico_desde_a_compra_e_cota_hoje(cenario: Cenario) -> None:
    ids = preparar(cenario)
    petr = ids["petr"]
    cenario.yahoo.precos[petr] = D("52.2")
    cenario.yahoo.historico[petr] = [
        Fechamento(date(2026, 3, 1), D("29")),  # antes da compra: não é pedido
        Fechamento(date(2026, 10, 27), D("51.5")),
        Fechamento(date(2026, 10, 28), D("52")),
        Fechamento(HOJE, D("52.1")),  # candle de hoje: tratado pela cotação atual
    ]
    resumo = cenario.coletor.executar()

    # 1 ano para trás seria 29/10/2025, mas a primeira compra (02/03/2026) é mais recente.
    assert cenario.yahoo.chamadas_historico == [[(petr, date(2026, 3, 2))]]
    assert cenario.precos(petr) == [
        (date(2026, 10, 27), D("51.5"), OrigemPreco.AUTOMATICO, "yfinance"),
        (date(2026, 10, 28), D("52"), OrigemPreco.AUTOMATICO, "yfinance"),
        (HOJE, D("52.2"), OrigemPreco.AUTOMATICO, "yfinance"),
    ]
    estado = cenario.estado(chave_ativo(petr))
    assert estado is not None
    assert estado.historico_desde == date(2026, 3, 2)
    assert estado.ultimo_sucesso == cenario.relogio.agora
    assert estado.ultimo_erro is None
    assert estado.provider == "yfinance"
    assert resumo.precos_atualizados == 3
    assert resumo.erros == 0
    assert cenario.tipos_de_evento() == ["preco_atualizado", "fim_ciclo"]
    assert cenario.eventos[0].dados == {
        "ativo_id": petr,
        "data": "2026-10-29",
        "data_hora": "2026-10-29T17:00:00+00:00",
        "valor": "52.2",
        "moeda": "BRL",
        "origem": "automatico",
        "provider": "yfinance",
    }


def test_intervalo_e_respeitado_e_reflete_mudanca_sem_reiniciar(cenario: Cenario) -> None:
    petr = preparar(cenario)["petr"]
    cenario.yahoo.precos[petr] = D("52.2")
    cenario.coletor.executar()
    cenario.relogio.avancar(minutes=3)
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 1  # 3 min < 5 min (padrão)
    cenario.relogio.avancar(minutes=2)
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 2  # 5 min: coleta
    assert len(cenario.yahoo.chamadas_historico) == 1  # histórico só na primeira vez
    with sessao_transacional(cenario.fabrica) as sessao:
        alterar_configuracoes(sessao, 15)
    cenario.relogio.avancar(minutes=10)
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 2  # agora o intervalo é 15 min
    cenario.relogio.avancar(minutes=5)
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 3
    # Um preço por dia: as coletas do dia atualizam o mesmo registro.
    assert len([p for p in cenario.precos(petr) if p[0] == HOJE]) == 1


def test_forcar_ignora_o_intervalo(cenario: Cenario) -> None:
    petr = preparar(cenario)["petr"]
    cenario.yahoo.precos[petr] = D("52.2")
    cenario.coletor.executar()
    cenario.relogio.avancar(seconds=10)
    cenario.yahoo.precos[petr] = D("52.4")
    resumo = cenario.coletor.executar(forcar=True)
    assert resumo.forcado is True
    assert len(cenario.yahoo.chamadas_cotacao) == 2
    assert cenario.precos(petr)[-1][1] == D("52.4")


def test_fora_do_pregao_coleta_so_ate_pegar_o_fechamento(engine: Engine) -> None:
    cenario = Cenario(engine, em_sp(HOJE, 16, 55))
    petr = preparar(cenario)["petr"]
    cenario.yahoo.precos[petr] = D("52.2")
    cenario.coletor.executar()
    cenario.relogio.agora = em_sp(HOJE, 19)  # fechou (17h + 30 min de margem)
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 2  # último sucesso antes do fechamento
    cenario.relogio.agora = em_sp(HOJE, 21)
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 2  # já tem o fechamento de quinta
    cenario.relogio.agora = em_sp(date(2026, 10, 31), 12)  # sábado
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 3  # pega o fechamento de sexta (30/10)
    cenario.relogio.agora = em_sp(date(2026, 11, 1), 12)  # domingo
    cenario.coletor.executar()
    cenario.relogio.agora = em_sp(date(2026, 11, 2), 11)  # segunda: Finados, B3 fechada
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 3
    cenario.relogio.agora = em_sp(date(2026, 11, 3), 10, 1)  # terça, pregão aberto
    cenario.coletor.executar()
    assert len(cenario.yahoo.chamadas_cotacao) == 4


def test_falha_vira_erro_do_ativo_e_e_tentada_no_ciclo_seguinte(cenario: Cenario) -> None:
    ids = preparar(cenario)
    with sessao_transacional(cenario.fabrica) as sessao:
        vale = acao_br(sessao, "VALE3")
    cenario.yahoo.precos[ids["petr"]] = D("52.2")
    # VALE3 sem preço na fonte: erro só nela; PETR4 segue.
    resumo = cenario.coletor.executar()
    assert resumo.erros == 1
    erro = cenario.estado(chave_ativo(vale.id))
    assert erro is not None
    assert erro.ultimo_sucesso is None
    assert erro.ultimo_erro == "Teste VALE3 não encontrado."
    assert erro.ultima_tentativa == cenario.relogio.agora
    assert [e.dados.get("ativo_id") for e in cenario.eventos if e.tipo == "erro_provider"] == [
        vale.id
    ]
    cenario.relogio.avancar(minutes=1)
    cenario.yahoo.precos[vale.id] = D("60")
    cenario.coletor.executar()
    assert cenario.yahoo.chamadas_cotacao[-1] == [vale.id]  # só quem falhou, antes do intervalo
    recuperado = cenario.estado(chave_ativo(vale.id))
    assert recuperado is not None
    assert recuperado.ultimo_erro is None
    assert recuperado.ultimo_sucesso == cenario.relogio.agora


def test_fonte_fora_do_ar_e_erro_inesperado_nao_derrubam_o_ciclo(cenario: Cenario) -> None:
    petr = preparar(cenario)["petr"]
    cenario.yahoo.falha_cotacao = FonteIndisponivelError("Yahoo Finance não respondeu a tempo.")
    resumo = cenario.coletor.executar()
    estado = cenario.estado(chave_ativo(petr))
    assert estado is not None
    assert estado.ultimo_erro == "Yahoo Finance não respondeu a tempo."
    assert resumo.erros == 1
    assert cenario.tipos_de_evento()[-1] == "fim_ciclo"
    cenario.yahoo.falha_cotacao = RuntimeError("bug")
    cenario.relogio.avancar(minutes=1)
    cenario.coletor.executar()
    estado = cenario.estado(chave_ativo(petr))
    assert estado is not None
    assert estado.ultimo_erro == "Erro inesperado ao consultar yfinance. Detalhes no log."


def test_preco_manual_do_dia_nao_e_sobrescrito(cenario: Cenario) -> None:
    petr = preparar(cenario)["petr"]
    with sessao_transacional(cenario.fabrica) as sessao:
        registrar_preco(sessao, petr, em_sp(HOJE, 9), D("50"), OrigemPreco.MANUAL)
    cenario.yahoo.precos[petr] = D("52.2")
    cenario.coletor.executar()
    assert cenario.precos(petr) == [(HOJE, D("50"), OrigemPreco.MANUAL, None)]
    assert "preco_atualizado" not in cenario.tipos_de_evento()
    estado = cenario.estado(chave_ativo(petr))
    assert estado is not None
    assert estado.ultimo_sucesso is not None  # a coleta funcionou; só não sobrescreveu


def test_lacuna_de_dias_e_completada_pelo_historico(cenario: Cenario) -> None:
    petr = preparar(cenario)["petr"]
    cenario.yahoo.precos[petr] = D("52.2")
    cenario.coletor.executar()
    cenario.relogio.agora = em_sp(date(2026, 11, 9), 11)  # app fechado por 11 dias
    cenario.yahoo.historico[petr] = [
        Fechamento(date(2026, 11, 3), D("53")),
        Fechamento(date(2026, 11, 6), D("54")),
    ]
    cenario.coletor.executar()
    assert cenario.yahoo.chamadas_historico[-1] == [(petr, HOJE)]  # desde o último preço
    assert [p[0] for p in cenario.precos(petr)][-3:] == [
        date(2026, 11, 3),
        date(2026, 11, 6),
        date(2026, 11, 9),
    ]


def test_ativo_sem_compra_baixa_um_ano_e_filtro_por_ativo(cenario: Cenario) -> None:
    with sessao_transacional(cenario.fabrica) as sessao:
        itub = acao_br(sessao, "ITUB4")
        bbas = acao_br(sessao, "BBAS3")
    cenario.coletor.executar(ativo_ids=[itub.id])
    assert cenario.yahoo.chamadas_historico == [[(itub.id, date(2025, 10, 29))]]
    assert cenario.yahoo.chamadas_cotacao == [[itub.id]]
    assert cenario.estado(chave_ativo(bbas.id)) is None
    assert cenario.sgs.chamadas == []  # o filtro por ativo não coleta indicadores


def test_cripto_grava_o_id_descoberto_em_simbolo_externo(cenario: Cenario) -> None:
    from app.services.cadastros import NovoAtivo, criar_ativo

    with sessao_transacional(cenario.fabrica) as sessao:
        btc = criar_ativo(sessao, NovoAtivo(tipo="cripto", nome="Bitcoin", simbolo="BTC"))
    cenario.gecko.precos[btc.id] = D("426934")
    cenario.coletor.executar()
    with sessao_transacional(cenario.fabrica) as sessao:
        ativo = sessao.get(m.Ativo, btc.id)
        assert ativo is not None
        assert ativo.simbolo_externo == "id-btc"
    assert cenario.precos(btc.id)[-1][3] == "coingecko"


def test_ativo_com_provider_nao_registrado(cenario: Cenario) -> None:
    with sessao_transacional(cenario.fabrica) as sessao:
        fundo = sessao.merge(
            m.Ativo(tipo="fundo", nome="Fundo X", moeda="BRL", provider="cvm", metadados={})
        )
    resumo = cenario.coletor.executar()
    assert resumo.erros == 1
    estado = cenario.estado(chave_ativo(fundo.id))
    assert estado is not None
    assert estado.ultimo_erro == "Fonte de cotação 'cvm' não disponível."


def test_ativo_excluido_durante_o_ciclo_e_ignorado(cenario: Cenario) -> None:
    with sessao_transacional(cenario.fabrica) as sessao:
        itub = acao_br(sessao, "ITUB4")
    cenario.yahoo.precos[itub.id] = D("30")

    def excluir_no_meio(alvos: Sequence[AlvoCotacao]) -> dict[int, ResultadoCotacao]:
        with sessao_transacional(cenario.fabrica) as sessao:
            sessao.delete(sessao.get(m.Ativo, itub.id))
        return CotacaoFalsa.cotacoes(cenario.yahoo, alvos)

    cenario.yahoo.cotacoes = excluir_no_meio  # type: ignore[method-assign]
    resumo = cenario.coletor.executar()
    assert resumo.erros == 0
    assert cenario.estado(chave_ativo(itub.id)) is None


# ---------------------------------------------------------------- indicadores


def test_indicadores_necessarios_pela_carteira(sessao: Session) -> None:
    rico, avenue = instituicao(sessao), instituicao(sessao, "Avenue")
    titulo = cdb(sessao, "cdi", aplicacao=date(2026, 1, 5))
    ipca = cdb(sessao, "ipca", "6", aplicacao=date(2026, 2, 10), nome="CDB IPCA")
    deposito(sessao, rico, "5000", date(2026, 1, 5))
    montante(sessao, titulo, rico, TipoTransacao.APORTE, date(2026, 1, 5), "1000")
    montante(sessao, ipca, rico, TipoTransacao.APORTE, date(2026, 2, 10), "1000")
    deposito(sessao, avenue, "100", date(2026, 4, 1), moeda="USD")
    acao_us(sessao)  # sem operações: só precisa do câmbio atual
    assert indicadores_necessarios(sessao, HOJE) == {
        (TipoIndicador.CDI, "BRL"): date(2025, 12, 29),  # 7 dias antes do aporte
        (TipoIndicador.IPCA, "BRL"): date(2025, 12, 1),  # 2 meses antes do mês do aporte
        (TipoIndicador.CAMBIO, "USD"): date(2026, 3, 25),  # conta em USD desde 01/04
    }


def test_carga_inicial_e_recoleta_diaria_de_indicadores(cenario: Cenario) -> None:
    with sessao_transacional(cenario.fabrica) as sessao:
        rico = instituicao(sessao)
        titulo = cdb(sessao, "cdi", aplicacao=date(2026, 1, 5))
        deposito(sessao, rico, "5000", date(2026, 1, 5))
        montante(sessao, titulo, rico, TipoTransacao.APORTE, date(2026, 1, 5), "1000")
        registrar_indicador(sessao, TipoIndicador.CDI, date(2026, 1, 2), D("15"))  # manual
    cenario.sgs.series[(TipoIndicador.CDI, "BRL")] = [
        PontoIndicador(date(2026, 1, 2), D("14.9")),
        PontoIndicador(date(2026, 1, 5), D("14.9")),
        PontoIndicador(date(2026, 10, 28), D("13.65")),
    ]
    resumo = cenario.coletor.executar()
    assert cenario.sgs.chamadas == [(TipoIndicador.CDI, "BRL", date(2025, 12, 29), HOJE)]
    assert cenario.indicadores(TipoIndicador.CDI) == [
        (date(2026, 1, 2), D("15"), "manual"),  # manual prevalece
        (date(2026, 1, 5), D("14.9"), "bcb_sgs"),
        (date(2026, 10, 28), D("13.65"), "bcb_sgs"),
    ]
    assert resumo.indicadores_gravados == 2
    estado = cenario.estado(chave_indicador(TipoIndicador.CDI, "BRL"))
    assert estado is not None
    assert estado.historico_desde == date(2025, 12, 29)
    assert estado.provider == "bcb_sgs"
    assert "indicador_atualizado" in cenario.tipos_de_evento()

    cenario.relogio.avancar(hours=3)
    cenario.coletor.executar()
    assert len(cenario.sgs.chamadas) == 1  # já coletou hoje
    cenario.relogio.avancar(days=1)
    cenario.sgs.series[(TipoIndicador.CDI, "BRL")].append(PontoIndicador(HOJE, D("13.65")))
    cenario.coletor.executar()
    # Dia seguinte: repete os últimos 10 dias (publicações atrasadas).
    assert cenario.sgs.chamadas[-1] == (
        TipoIndicador.CDI,
        "BRL",
        date(2026, 10, 18),
        date(2026, 10, 30),
    )
    assert cenario.indicadores(TipoIndicador.CDI)[-1] == (HOJE, D("13.65"), "bcb_sgs")


def test_cambio_usa_yahoo_quando_a_ptax_falha_e_a_ptax_substitui_depois(
    cenario: Cenario,
) -> None:
    with sessao_transacional(cenario.fabrica) as sessao:
        aapl = acao_us(sessao)
    cenario.yahoo.precos[aapl.id] = D("230")
    ontem = date(2026, 10, 28)
    cenario.sgs.falha = FonteIndisponivelError("Banco Central (SGS) não respondeu a tempo.")
    cenario.yahoo_cambio.series[(TipoIndicador.CAMBIO, "USD")] = [
        PontoIndicador(ontem, D("5.36")),
        PontoIndicador(HOJE, D("5.3712")),
    ]
    resumo = cenario.coletor.executar()
    assert cenario.indicadores(TipoIndicador.CAMBIO, "USD") == [
        (ontem, D("5.36"), "yfinance"),
        (HOJE, D("5.3712"), "yfinance"),
    ]
    estado = cenario.estado(chave_indicador(TipoIndicador.CAMBIO, "USD"))
    assert estado is not None
    assert estado.provider == "yfinance"  # fallback
    assert estado.ultimo_erro is None
    assert resumo.erros == 0

    cenario.sgs.falha = None
    cenario.sgs.series[(TipoIndicador.CAMBIO, "USD")] = [PontoIndicador(ontem, D("5.3655"))]
    cenario.relogio.avancar(days=1)  # 30/10
    cenario.yahoo_cambio.series[(TipoIndicador.CAMBIO, "USD")].append(
        PontoIndicador(date(2026, 10, 30), D("5.40"))
    )
    cenario.coletor.executar()
    assert cenario.indicadores(TipoIndicador.CAMBIO, "USD") == [
        (ontem, D("5.3655"), "bcb_sgs"),  # PTAX oficial substituiu o Yahoo
        (HOJE, D("5.3712"), "yfinance"),
        (date(2026, 10, 30), D("5.4"), "yfinance"),  # dólar ao longo do dia
    ]
    intradiario = cenario.estado(chave_cambio_intradiario("USD"))
    assert intradiario is not None
    assert intradiario.ultimo_sucesso == cenario.relogio.agora


def test_todas_as_fontes_do_indicador_falham(cenario: Cenario) -> None:
    with sessao_transacional(cenario.fabrica) as sessao:
        aapl = acao_us(sessao)
    cenario.yahoo.precos[aapl.id] = D("230")
    cenario.sgs.falha = FonteIndisponivelError("SGS fora.")
    cenario.yahoo_cambio.falha = FonteIndisponivelError("Yahoo fora.")
    resumo = cenario.coletor.executar()
    estado = cenario.estado(chave_indicador(TipoIndicador.CAMBIO, "USD"))
    assert estado is not None
    assert estado.ultimo_erro == "SGS fora. Yahoo fora."
    assert estado.ultimo_sucesso is None
    assert resumo.erros == 2  # diário e intradiário


def test_cambio_ao_longo_do_dia_so_grava_hoje(cenario: Cenario) -> None:
    # O Yahoo às vezes traz pontos estranhos em dias passados (ex.: 4,96 com a PTAX em 5,33):
    # o câmbio intradiário só grava o dia de hoje; os anteriores ficam com a fonte diária.
    with sessao_transacional(cenario.fabrica) as sessao:
        aapl = acao_us(sessao)
    cenario.yahoo.precos[aapl.id] = D("230")
    cenario.sgs.series[(TipoIndicador.CAMBIO, "USD")] = [
        PontoIndicador(date(2026, 10, 27), D("5.33"))
    ]
    cenario.yahoo_cambio.series[(TipoIndicador.CAMBIO, "USD")] = [
        PontoIndicador(date(2026, 10, 26), D("4.96")),
        PontoIndicador(HOJE, D("5.38")),
    ]
    cenario.coletor.executar()
    assert cenario.indicadores(TipoIndicador.CAMBIO, "USD") == [
        (date(2026, 10, 27), D("5.33"), "bcb_sgs"),
        (HOJE, D("5.38"), "yfinance"),
    ]
