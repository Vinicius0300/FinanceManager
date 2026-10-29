"""Atualização automática de cotações e indicadores (um ciclo de coleta).

Um ciclo tem três fases, para não segurar o banco durante a rede:
1. **plano** (transação curta): lê ativos, estados e configurações e decide o que coletar
   (regras de ``domain/agenda.py``; ``forcar`` ignora o intervalo);
2. **rede** (sem sessão aberta): chama os providers;
3. **gravação** (uma transação por alvo): grava preços/indicadores e o estado da coleta.

Falhas nunca derrubam o ciclo: erro de rede, de provider ou inesperado vira ``ultimo_erro``
daquele alvo (com log em arquivo) e os demais continuam. Cada mudança é publicada como
evento (``preco_atualizado``, ``indicador_atualizado``, ``erro_provider``) e o ciclo
termina com ``fim_ciclo``.

Histórico: ativo cotado sem histórico baixa os fechamentos de até 1 ano para trás (ou desde
a primeira compra, se mais recente); depois disso só completa lacunas (app fechado por
alguns dias). Indicadores baixam desde a data mais antiga necessária (aplicações de renda
fixa/poupança, operações e contas em moeda estrangeira).
"""

import logging
import threading
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from typing import Literal, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.asset_types.base import HandlerCotado, HandlerMontante
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.core.banco import sessao_transacional
from app.domain.agenda import AGENDA_CONTINUA, AGENDA_DIARIA, precisa_coletar
from app.domain.enums import OrigemPreco, TipoIndicador, TipoTransacao
from app.domain.erros import DominioError
from app.domain.indicadores import NOMES_INDICADORES, PontoIndicador
from app.domain.moedas import MOEDA_BASE
from app.domain.numeros import texto_decimal
from app.domain.tempo import agora_utc, data_local, primeiro_dia_do_mes
from app.providers.base import (
    AlvoCotacao,
    PedidoHistorico,
    ProviderCotacao,
    ProviderError,
    ProviderIndicador,
    ResultadoCotacao,
    ResultadoHistorico,
)
from app.providers.registry import RegistroProviders
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.repositories.contas import RepositorioContas, RepositorioMovimentos
from app.repositories.mercado import (
    RepositorioEstadosColeta,
    RepositorioIndicadores,
    RepositorioPrecos,
)
from app.repositories.transacoes import RepositorioEventos, RepositorioTransacoes
from app.services.configuracoes import obter_intervalo
from app.services.mercado import gravar_fechamentos, gravar_indicadores_automaticos, registrar_preco

logger = logging.getLogger(__name__)
T = TypeVar("T")

DIAS_HISTORICO = 365
MARGEM_INDICADOR = timedelta(days=7)
"""Folga antes da data mais antiga: câmbio e Selic buscam o último valor até 7 dias antes."""
MESES_MARGEM_IPCA = 2
RECOLETA_INDICADOR = timedelta(days=10)
"""Coletas seguintes repetem os últimos dias (valores publicados com atraso)."""
RECOLETA_IPCA = timedelta(days=100)
DIAS_CAMBIO_INTRADIARIO = 4
TAMANHO_ERRO = 500

TipoEvento = Literal["preco_atualizado", "indicador_atualizado", "erro_provider", "fim_ciclo"]


@dataclass(frozen=True)
class EventoColeta:
    tipo: TipoEvento
    dados: dict[str, object]


Publicar = Callable[[EventoColeta], None]


def _sem_publicacao(_: EventoColeta) -> None:
    return None


def chave_ativo(ativo_id: int) -> str:
    return f"ativo:{ativo_id}"


def chave_indicador(tipo: TipoIndicador, moeda: str) -> str:
    return f"indicador:{tipo.value}:{moeda}"


def chave_cambio_intradiario(moeda: str) -> str:
    return f"indicador:cambio_intradiario:{moeda}"


def _texto_erro(mensagem: str) -> str:
    return mensagem[:TAMANHO_ERRO]


# ---------------------------------------------------------------- plano


@dataclass(frozen=True)
class TarefaAtivo:
    alvo: AlvoCotacao
    provider: str
    cotar: bool
    historico_desde: date | None  # None: não baixa histórico neste ciclo
    historico_completo: bool  # True: marca historico_desde ao terminar


@dataclass(frozen=True)
class TarefaIndicador:
    tipo: TipoIndicador
    moeda: str
    inicio: date
    completo: bool  # True: primeira carga (ou início mais antigo que o já baixado)


@dataclass
class Plano:
    agora: datetime
    hoje: date
    ativos: list[TarefaAtivo] = field(default_factory=list)
    indicadores: list[TarefaIndicador] = field(default_factory=list)
    cambio_intradiario: list[str] = field(default_factory=list)
    sem_provider: list[tuple[int, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ResumoCiclo:
    inicio: datetime
    fim: datetime
    forcado: bool
    precos_atualizados: int
    indicadores_gravados: int
    erros: int


def _inicio_historico(hoje: date, primeira_compra: date | None) -> date:
    um_ano = hoje - timedelta(days=DIAS_HISTORICO)
    return max(um_ano, primeira_compra) if primeira_compra else um_ano


def _alvo(ativo: m.Ativo) -> AlvoCotacao:
    return AlvoCotacao(
        ativo_id=ativo.id,
        tipo=ativo.tipo,
        nome=ativo.nome,
        moeda=ativo.moeda,
        simbolo=ativo.simbolo,
        simbolo_externo=ativo.simbolo_externo,
        metadados=dict(ativo.metadados),
    )


def _juntar_inicio(
    necessidades: dict[tuple[TipoIndicador, str], date], chave: tuple[TipoIndicador, str], dia: date
) -> None:
    atual = necessidades.get(chave)
    necessidades[chave] = dia if atual is None else min(atual, dia)


def _inicio_do_indicador(tipo: TipoIndicador, dia: date) -> date:
    if tipo is TipoIndicador.IPCA:
        mes = primeiro_dia_do_mes(dia)
        for _ in range(MESES_MARGEM_IPCA):
            mes = primeiro_dia_do_mes(mes - timedelta(days=1))
        return mes
    return dia - MARGEM_INDICADOR


def indicadores_necessarios(
    sessao: Session, hoje: date, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> dict[tuple[TipoIndicador, str], date]:
    """Indicadores usados pela carteira e a data mais antiga necessária de cada um."""
    necessidades: dict[tuple[TipoIndicador, str], date] = {}
    primeira_operacao: dict[int, date] = {}
    for transacao in RepositorioTransacoes(sessao).listar_ate():
        primeira_operacao.setdefault(transacao.ativo_id, transacao.data)
    for evento in RepositorioEventos(sessao).listar():
        atual = primeira_operacao.get(evento.ativo_id)
        primeira_operacao[evento.ativo_id] = (
            evento.data if atual is None else min(atual, evento.data)
        )
    for ativo in RepositorioAtivos(sessao).listar():
        handler = registro.obter(ativo.tipo)
        inicio = primeira_operacao.get(ativo.id)
        if isinstance(handler, HandlerMontante) and inicio is not None:
            for tipo in handler.indicadores_necessarios(ativo.metadados):
                _juntar_inicio(necessidades, (tipo, MOEDA_BASE), _inicio_do_indicador(tipo, inicio))
        if ativo.moeda != MOEDA_BASE:
            _juntar_inicio(
                necessidades,
                (TipoIndicador.CAMBIO, ativo.moeda),
                _inicio_do_indicador(TipoIndicador.CAMBIO, inicio or hoje),
            )
    movimentos = RepositorioMovimentos(sessao)
    for conta in RepositorioContas(sessao).listar():
        if conta.moeda == MOEDA_BASE:
            continue
        datas = [mov.data for mov in movimentos.da_conta(conta.id)]
        _juntar_inicio(
            necessidades,
            (TipoIndicador.CAMBIO, conta.moeda),
            _inicio_do_indicador(TipoIndicador.CAMBIO, min(datas, default=hoje)),
        )
    return necessidades


def montar_plano(
    sessao: Session,
    providers: RegistroProviders,
    agora: datetime,
    *,
    forcar: bool = False,
    ativo_ids: Iterable[int] | None = None,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> Plano:
    """Decide o que coletar agora (função pura sobre o banco; não acessa a rede)."""
    hoje = data_local(agora)
    intervalo = timedelta(minutes=obter_intervalo(sessao))
    plano = Plano(agora=agora, hoje=hoje)
    estados = RepositorioEstadosColeta(sessao)
    filtro = set(ativo_ids) if ativo_ids is not None else None

    primeira_compra: dict[int, date] = {}
    for transacao in RepositorioTransacoes(sessao).listar_ate():
        if transacao.tipo is TipoTransacao.COMPRA:
            primeira_compra.setdefault(transacao.ativo_id, transacao.data)

    precos = RepositorioPrecos(sessao)
    estados_ativos = estados.de_ativos()
    for ativo in RepositorioAtivos(sessao).listar():
        if filtro is not None and ativo.id not in filtro:
            continue
        handler = registro.obter(ativo.tipo)
        if not isinstance(handler, HandlerCotado) or not ativo.provider:
            continue
        if providers.cotacao(ativo.provider) is None:
            plano.sem_provider.append((ativo.id, ativo.provider))
            continue
        estado = estados_ativos.get(ativo.id)
        sucesso = estado.ultimo_sucesso if estado else None
        cotar = forcar or precisa_coletar(handler.agenda, sucesso, agora, intervalo)
        inicio = _inicio_historico(hoje, primeira_compra.get(ativo.id))
        desde = estado.historico_desde if estado else None
        historico: date | None = None
        completo = False
        if desde is None or inicio < desde:
            historico, completo = inicio, True
        elif cotar:
            ultimos = precos.ultimos(ativo.id, 1)
            ultimo_dia = ultimos[0].data if ultimos else None
            if ultimo_dia is not None and ultimo_dia < hoje - timedelta(days=1):
                historico = ultimo_dia  # completa a lacuna (app fechado alguns dias)
        if cotar or historico is not None:
            plano.ativos.append(
                TarefaAtivo(_alvo(ativo), ativo.provider, cotar, historico, completo)
            )

    if filtro is not None:
        return plano

    indicadores = RepositorioIndicadores(sessao)
    for (tipo, moeda), inicio in sorted(indicadores_necessarios(sessao, hoje, registro).items()):
        estado = estados.obter(chave_indicador(tipo, moeda))
        desde = estado.historico_desde if estado else None
        completo = desde is None or inicio < desde
        sucesso = estado.ultimo_sucesso if estado else None
        if completo:
            plano.indicadores.append(TarefaIndicador(tipo, moeda, inicio, True))
        elif forcar or precisa_coletar(AGENDA_DIARIA, sucesso, agora, intervalo):
            recoleta = RECOLETA_IPCA if tipo is TipoIndicador.IPCA else RECOLETA_INDICADOR
            ultima = indicadores.ultima_data(tipo, moeda) or hoje
            plano.indicadores.append(
                TarefaIndicador(tipo, moeda, max(min(ultima, hoje) - recoleta, inicio), False)
            )
        if tipo is TipoIndicador.CAMBIO and providers.cambio_intradiario is not None:
            intradiario = estados.obter(chave_cambio_intradiario(moeda))
            ultimo = intradiario.ultimo_sucesso if intradiario else None
            if forcar or precisa_coletar(AGENDA_CONTINUA, ultimo, agora, intervalo):
                plano.cambio_intradiario.append(moeda)
    return plano


# ---------------------------------------------------------------- rede


@dataclass
class ResultadosRede:
    cotacoes: dict[int, ResultadoCotacao] = field(default_factory=dict)
    historicos: dict[int, ResultadoHistorico] = field(default_factory=dict)
    identificadores: dict[int, str] = field(default_factory=dict)
    indicadores: dict[
        tuple[TipoIndicador, str], tuple[str, list[PontoIndicador]] | ProviderError
    ] = field(default_factory=dict)
    cambio_intradiario: dict[str, tuple[str, list[PontoIndicador]] | ProviderError] = field(
        default_factory=dict
    )


def _chamar(funcao: Callable[[], T], descricao: str) -> T | ProviderError:
    """Executa ``funcao``; erro inesperado vira ``ProviderError`` (com log), nunca exceção."""
    try:
        return funcao()
    except ProviderError as erro:
        return erro
    except Exception:
        logger.exception("Erro inesperado ao consultar %s", descricao)
        return ProviderError(f"Erro inesperado ao consultar {descricao}. Detalhes no log.")


def _buscar_indicador(
    fontes: Sequence[ProviderIndicador], tipo: TipoIndicador, moeda: str, inicio: date, fim: date
) -> tuple[str, list[PontoIndicador]] | ProviderError:
    """Tenta as fontes em ordem (fallback); devolve a primeira que responder."""
    if not fontes:
        return ProviderError(f"Nenhuma fonte disponível para {NOMES_INDICADORES[tipo]} {moeda}.")
    erros: list[str] = []
    for fonte in fontes:
        resultado = _chamar(partial(fonte.serie, tipo, moeda, inicio, fim), fonte.nome)
        if not isinstance(resultado, ProviderError):
            return fonte.nome, resultado
        logger.warning("%s %s: %s falhou (%s)", tipo.value, moeda, fonte.nome, resultado.mensagem)
        erros.append(resultado.mensagem)
    return ProviderError(" ".join(erros))


def _nunca() -> bool:
    return False


def consultar_rede(
    plano: Plano, providers: RegistroProviders, cancelado: Callable[[], bool] = _nunca
) -> ResultadosRede:
    """Chama os providers (sem sessão aberta). Para no próximo alvo se ``cancelado()``."""
    resultados = ResultadosRede()
    por_provider: dict[str, list[TarefaAtivo]] = defaultdict(list)
    for tarefa in plano.ativos:
        por_provider[tarefa.provider].append(tarefa)
    for nome, tarefas in por_provider.items():
        if cancelado():
            return resultados
        provider = providers.cotacao(nome)
        if provider is None:  # pragma: no cover - o plano já filtra
            continue
        _consultar_ativos(provider, tarefas, plano.hoje, resultados)
    for pedido in plano.indicadores:
        if cancelado():
            return resultados
        resultados.indicadores[(pedido.tipo, pedido.moeda)] = _buscar_indicador(
            providers.fontes_indicador(pedido.tipo, pedido.moeda),
            pedido.tipo,
            pedido.moeda,
            pedido.inicio,
            plano.hoje,
        )
    intradiario = providers.cambio_intradiario
    if intradiario is not None:
        for moeda in plano.cambio_intradiario:
            resultado = _buscar_indicador(
                [intradiario],
                TipoIndicador.CAMBIO,
                moeda,
                plano.hoje - timedelta(days=DIAS_CAMBIO_INTRADIARIO),
                plano.hoje,
            )
            # Só o valor de hoje: dias anteriores ficam com a PTAX (ou a reserva diária).
            resultados.cambio_intradiario[moeda] = (
                resultado
                if isinstance(resultado, ProviderError)
                else (resultado[0], [p for p in resultado[1] if p.data == plano.hoje])
            )
    return resultados


def _consultar_ativos(
    provider: ProviderCotacao, tarefas: list[TarefaAtivo], hoje: date, resultados: ResultadosRede
) -> None:
    if provider.identificador_persistente:
        for tarefa in tarefas:
            if not tarefa.alvo.simbolo_externo:
                identificado = _chamar(partial(provider.identificar, tarefa.alvo), provider.nome)
                if isinstance(identificado, str):
                    resultados.identificadores[tarefa.alvo.ativo_id] = identificado
    historicos = [
        PedidoHistorico(t.alvo, t.historico_desde) for t in tarefas if t.historico_desde is not None
    ]
    if historicos:
        lote = _chamar(partial(provider.historicos, historicos, hoje), provider.nome)
        resultados.historicos.update(
            {p.alvo.ativo_id: lote for p in historicos} if isinstance(lote, ProviderError) else lote
        )
    cotar = [t.alvo for t in tarefas if t.cotar]
    if cotar:
        cotacoes = _chamar(partial(provider.cotacoes, cotar), provider.nome)
        resultados.cotacoes.update(
            {a.ativo_id: cotacoes for a in cotar}
            if isinstance(cotacoes, ProviderError)
            else cotacoes
        )


# ---------------------------------------------------------------- gravação


class Coletor:
    """Executa ciclos de coleta. Thread-safe por fora: quem chama garante um ciclo por vez."""

    def __init__(
        self,
        fabrica_sessoes: sessionmaker[Session],
        providers: RegistroProviders,
        *,
        relogio: Callable[[], datetime] = agora_utc,
        publicar: Publicar = _sem_publicacao,
        registro: RegistroTiposAtivo = REGISTRO_PADRAO,
    ) -> None:
        self._fabrica = fabrica_sessoes
        self._providers = providers
        self._relogio = relogio
        self._publicar = publicar
        self._registro = registro
        self._cancelado = threading.Event()

    def cancelar(self) -> None:
        """Pede o fim antecipado (encerramento do app): o ciclo para no próximo alvo."""
        self._cancelado.set()

    def executar(
        self, *, forcar: bool = False, ativo_ids: Iterable[int] | None = None
    ) -> ResumoCiclo:
        inicio = self._relogio()
        with sessao_transacional(self._fabrica) as sessao:
            plano = montar_plano(
                sessao,
                self._providers,
                inicio,
                forcar=forcar,
                ativo_ids=ativo_ids,
                registro=self._registro,
            )
        rede = consultar_rede(plano, self._providers, self._cancelado.is_set)
        contagem = {"precos": 0, "indicadores": 0, "erros": 0}
        for ativo_id, provider in plano.sem_provider:
            self._erro_ativo(
                plano,
                ativo_id,
                provider,
                f"Fonte de cotação {provider!r} não disponível.",
                contagem,
            )
        for tarefa in plano.ativos:
            if self._cancelado.is_set():
                break
            self._gravar_ativo(plano, tarefa, rede, contagem)
        for pedido in plano.indicadores:
            if self._cancelado.is_set():
                break
            self._gravar_indicador(
                plano,
                chave_indicador(pedido.tipo, pedido.moeda),
                pedido.tipo,
                pedido.moeda,
                rede.indicadores.get(
                    (pedido.tipo, pedido.moeda), ProviderError("Coleta interrompida.")
                ),
                pedido.inicio if pedido.completo else None,
                contagem,
            )
        for moeda, resultado in rede.cambio_intradiario.items():
            if self._cancelado.is_set():
                break
            self._gravar_indicador(
                plano,
                chave_cambio_intradiario(moeda),
                TipoIndicador.CAMBIO,
                moeda,
                resultado,
                None,
                contagem,
            )
        resumo = ResumoCiclo(
            inicio=inicio,
            fim=self._relogio(),
            forcado=forcar,
            precos_atualizados=contagem["precos"],
            indicadores_gravados=contagem["indicadores"],
            erros=contagem["erros"],
        )
        self._publicar(
            EventoColeta(
                "fim_ciclo",
                {
                    "inicio": resumo.inicio.isoformat(),
                    "fim": resumo.fim.isoformat(),
                    "forcado": forcar,
                    "precos_atualizados": resumo.precos_atualizados,
                    "indicadores_gravados": resumo.indicadores_gravados,
                    "erros": resumo.erros,
                },
            )
        )
        return resumo

    # ------------------------------------------------------------ ativos

    def _erro_ativo(
        self, plano: Plano, ativo_id: int, provider: str, mensagem: str, contagem: dict[str, int]
    ) -> None:
        contagem["erros"] += 1
        try:
            with sessao_transacional(self._fabrica) as sessao:
                if RepositorioAtivos(sessao).obter(ativo_id) is None:
                    return
                estado = RepositorioEstadosColeta(sessao).obter_ou_criar(
                    chave_ativo(ativo_id), ativo_id
                )
                estado.ultima_tentativa = plano.agora
                estado.ultimo_erro = _texto_erro(mensagem)
                estado.provider = provider
        except Exception:
            logger.exception("Falha ao registrar o erro de coleta do ativo %s", ativo_id)
        logger.warning("Coleta do ativo %s (%s): %s", ativo_id, provider, mensagem)
        self._publicar(
            EventoColeta(
                "erro_provider",
                {
                    "alvo": chave_ativo(ativo_id),
                    "ativo_id": ativo_id,
                    "provider": provider,
                    "mensagem": mensagem,
                },
            )
        )

    def _gravar_ativo(
        self, plano: Plano, tarefa: TarefaAtivo, rede: ResultadosRede, contagem: dict[str, int]
    ) -> None:
        ativo_id = tarefa.alvo.ativo_id
        erros: list[str] = []
        publicar: list[EventoColeta] = []
        try:
            with sessao_transacional(self._fabrica) as sessao:
                ativo = RepositorioAtivos(sessao).obter(ativo_id)
                if ativo is None:  # excluído durante o ciclo
                    return
                estado = RepositorioEstadosColeta(sessao).obter_ou_criar(
                    chave_ativo(ativo_id), ativo_id
                )
                estado.ultima_tentativa = plano.agora
                estado.provider = tarefa.provider
                identificador = rede.identificadores.get(ativo_id)
                if identificador and not ativo.simbolo_externo:
                    ativo.simbolo_externo = identificador
                historico = rede.historicos.get(ativo_id)
                if isinstance(historico, ProviderError):
                    erros.append(f"Histórico: {historico.mensagem}")
                elif historico is not None:
                    fechamentos = [(f.data, f.valor) for f in historico]
                    contagem["precos"] += gravar_fechamentos(
                        sessao, ativo, fechamentos, tarefa.provider, plano.hoje
                    )
                    if tarefa.historico_completo and tarefa.historico_desde is not None:
                        atual = estado.historico_desde
                        estado.historico_desde = (
                            tarefa.historico_desde
                            if atual is None
                            else min(atual, tarefa.historico_desde)
                        )
                cotacao = rede.cotacoes.get(ativo_id)
                if isinstance(cotacao, ProviderError):
                    erros.insert(0, cotacao.mensagem)
                elif cotacao is not None:
                    preco = registrar_preco(
                        sessao,
                        ativo.id,
                        cotacao.data_hora,
                        cotacao.valor,
                        OrigemPreco.AUTOMATICO,
                        tarefa.provider,
                        registro=self._registro,
                    )
                    estado.ultimo_sucesso = plano.agora
                    if preco.origem is OrigemPreco.AUTOMATICO:
                        contagem["precos"] += 1
                        publicar.append(
                            EventoColeta(
                                "preco_atualizado",
                                {
                                    "ativo_id": ativo.id,
                                    "data": preco.data.isoformat(),
                                    "data_hora": preco.data_hora.isoformat(),
                                    "valor": texto_decimal(preco.valor),
                                    "moeda": preco.moeda,
                                    "origem": preco.origem.value,
                                    "provider": preco.provider,
                                },
                            )
                        )
                estado.ultimo_erro = _texto_erro(" ".join(erros)) if erros else None
        except (DominioError, ProviderError) as falha:
            erros = [falha.mensagem]
        except Exception:
            logger.exception("Erro inesperado ao gravar a cotação do ativo %s", ativo_id)
            erros = ["Erro inesperado ao gravar a cotação. Detalhes no log."]
            self._registrar_falha_de_gravacao(plano, ativo_id, tarefa.provider, erros[0])
        for evento in publicar:
            self._publicar(evento)
        if erros:
            contagem["erros"] += 1
            mensagem = " ".join(erros)
            logger.warning("Coleta do ativo %s (%s): %s", ativo_id, tarefa.provider, mensagem)
            self._publicar(
                EventoColeta(
                    "erro_provider",
                    {
                        "alvo": chave_ativo(ativo_id),
                        "ativo_id": ativo_id,
                        "provider": tarefa.provider,
                        "mensagem": mensagem,
                    },
                )
            )

    def _registrar_falha_de_gravacao(
        self, plano: Plano, ativo_id: int, provider: str, mensagem: str
    ) -> None:
        try:
            with sessao_transacional(self._fabrica) as sessao:
                if RepositorioAtivos(sessao).obter(ativo_id) is None:
                    return
                estado = RepositorioEstadosColeta(sessao).obter_ou_criar(
                    chave_ativo(ativo_id), ativo_id
                )
                estado.ultima_tentativa = plano.agora
                estado.ultimo_erro = mensagem
                estado.provider = provider
        except Exception:
            logger.exception("Falha ao registrar o erro de coleta do ativo %s", ativo_id)

    # ------------------------------------------------------------ indicadores

    def _gravar_indicador(
        self,
        plano: Plano,
        chave: str,
        tipo: TipoIndicador,
        moeda: str,
        resultado: tuple[str, list[PontoIndicador]] | ProviderError,
        historico_desde: date | None,
        contagem: dict[str, int],
    ) -> None:
        mensagem: str | None = resultado.mensagem if isinstance(resultado, ProviderError) else None
        gravados = 0
        fonte: str | None = None
        try:
            with sessao_transacional(self._fabrica) as sessao:
                estado = RepositorioEstadosColeta(sessao).obter_ou_criar(chave)
                estado.ultima_tentativa = plano.agora
                if not isinstance(resultado, ProviderError):
                    fonte, pontos = resultado
                    gravados = gravar_indicadores_automaticos(sessao, tipo, moeda, pontos, fonte)
                    estado.ultimo_sucesso = plano.agora
                    estado.provider = fonte
                    if historico_desde is not None:
                        atual = estado.historico_desde
                        estado.historico_desde = (
                            historico_desde if atual is None else min(atual, historico_desde)
                        )
                estado.ultimo_erro = _texto_erro(mensagem) if mensagem else None
        except (DominioError, ProviderError) as falha:
            mensagem, gravados = falha.mensagem, 0
        except Exception:
            logger.exception("Erro inesperado ao gravar %s", chave)
            mensagem, gravados = "Erro inesperado ao gravar o indicador. Detalhes no log.", 0
        contagem["indicadores"] += gravados
        if gravados:
            self._publicar(
                EventoColeta(
                    "indicador_atualizado",
                    {"tipo": tipo.value, "moeda": moeda, "fonte": fonte, "gravados": gravados},
                )
            )
        if mensagem:
            contagem["erros"] += 1
            logger.warning("Coleta de %s: %s", chave, mensagem)
            self._publicar(
                EventoColeta(
                    "erro_provider", {"alvo": chave, "provider": fonte, "mensagem": mensagem}
                )
            )
