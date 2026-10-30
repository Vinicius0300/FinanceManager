"""Histórico de operações (tela Movimentações): filtros, resultado, resumo e visão por ativo.

Fluxo de uma consulta:
1. o repositório aplica os filtros simples em SQL (ativo, instituição, operações, período,
   tipo de ativo, moeda, busca por símbolo/nome);
2. os ativos envolvidos são reprocessados **com todas as transações** (não só as filtradas),
   para que o resultado de cada venda/resgate e a situação usem a posição inteira;
3. os filtros que dependem desse cálculo (situação, só prejuízo, só com custos) e a
   ordenação são aplicados aqui; a API pagina o resultado.

Situação (decisão do dono): com filtro de instituição, vale a situação da **posição**
(ativo + instituição); sem ele, a do **ativo** somando todas as instituições.
"""

import logging
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.asset_types.base import HandlerMontante
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import TipoTransacao
from app.domain.erros import DominioError
from app.domain.historico import (
    AnalisePosicao,
    GrupoAtivo,
    OperacaoHistorico,
    PontoMensal,
    ResultadoOperacao,
    SituacaoPosicao,
    TotaisHistorico,
    agrupar_por_ativo,
    analisar_cotas,
    analisar_montante,
    serie_mensal,
    situacao_do_ativo,
    totalizar,
    valor_total,
)
from app.domain.indicadores import Indicadores
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.repositories.instituicoes import RepositorioInstituicoes
from app.repositories.transacoes import RepositorioEventos, RepositorioTransacoes
from app.services.cadastros import handler_do_ativo
from app.services.mercado import carregar_indicadores
from app.services.posicoes import (
    ChavePosicao,
    agrupar_por_posicao,
    operacao_montante,
    operacoes_cotas,
)

logger = logging.getLogger(__name__)


class CampoOrdem(StrEnum):
    DATA = "data"
    OPERACAO = "operacao"
    ATIVO = "ativo"
    INSTITUICAO = "instituicao"
    QUANTIDADE = "quantidade"
    PRECO_UNITARIO = "preco_unitario"
    TAXAS = "taxas"
    VALOR_TOTAL = "valor_total"
    RESULTADO = "resultado"


class Direcao(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class FiltroHistorico:
    ativo_id: int | None = None
    instituicao_id: int | None = None
    tipo_ativo: str | None = None
    moeda: str | None = None
    busca: str | None = None
    tipos: frozenset[TipoTransacao] | None = None  # None = todas as operações
    inicio: date | None = None
    fim: date | None = None
    situacao: SituacaoPosicao | None = None
    apenas_prejuizo: bool = False
    apenas_com_custos: bool = False


@dataclass(frozen=True)
class ItemHistorico:
    transacao: m.Transacao
    ativo: m.Ativo
    instituicao: m.Instituicao
    operacao: OperacaoHistorico
    situacao: SituacaoPosicao


@dataclass(frozen=True)
class ConsultaHistorico:
    """Itens filtrados e ordenados (sem paginar) e as situações calculadas."""

    itens: list[ItemHistorico]
    situacao_posicao: Callable[[int, int], SituacaoPosicao]
    situacao_ativo: Callable[[int], SituacaoPosicao]


@dataclass(frozen=True)
class ResumoHistorico:
    totais: TotaisHistorico
    total_sem_filtros: int
    inicio: date | None
    fim: date | None
    serie: list[PontoMensal]
    por_ativo: list[GrupoAtivo]


# --------------------------------------------------------------------- análise dos ativos


@dataclass(frozen=True)
class _Analise:
    resultados: dict[int, ResultadoOperacao]
    posicoes: dict[ChavePosicao, SituacaoPosicao]

    def da_posicao(self, ativo_id: int, instituicao_id: int) -> SituacaoPosicao:
        return self.posicoes.get(ChavePosicao(ativo_id, instituicao_id), SituacaoPosicao.ABERTA)

    def do_ativo(self, ativo_id: int) -> SituacaoPosicao:
        return situacao_do_ativo(
            s for chave, s in self.posicoes.items() if chave.ativo_id == ativo_id
        )


def _analisar(
    sessao: Session, ativos: dict[int, m.Ativo], registro: RegistroTiposAtivo
) -> _Analise:
    """Reprocessa cada posição dos ativos com todas as transações e eventos.

    Uma posição que não fecha mais (ex.: indicador editado depois de um resgate de renda
    fixa) não derruba a consulta: fica sem resultado, como aberta, e vai para o log.
    """
    if not ativos:
        return _Analise({}, {})
    transacoes = RepositorioTransacoes(sessao).dos_ativos(list(ativos))
    eventos = RepositorioEventos(sessao).dos_ativos(list(ativos))
    indicadores: Indicadores | None = None
    resultados: dict[int, ResultadoOperacao] = {}
    posicoes: dict[ChavePosicao, SituacaoPosicao] = {}
    for chave, grupo in agrupar_por_posicao(transacoes).items():
        ativo = ativos[chave.ativo_id]
        handler = handler_do_ativo(ativo, registro)
        try:
            analise: AnalisePosicao
            if isinstance(handler, HandlerMontante):
                if indicadores is None:
                    indicadores = carregar_indicadores(sessao)
                fator = handler.criar_fator(ativo.metadados, indicadores)
                analise = analisar_montante([operacao_montante(t) for t in grupo], fator)
            else:
                do_ativo = [e for e in eventos if e.ativo_id == ativo.id]
                analise = analisar_cotas(operacoes_cotas(grupo, do_ativo))
        except DominioError as falha:
            logger.warning(
                "Histórico: posição %s/%s não pôde ser recalculada: %s",
                chave.ativo_id,
                chave.instituicao_id,
                falha.mensagem,
            )
            posicoes[chave] = SituacaoPosicao.ABERTA
            continue
        resultados.update(analise.resultados)
        posicoes[chave] = analise.situacao
    return _Analise(resultados, posicoes)


def _operacao(transacao: m.Transacao, resultado: ResultadoOperacao | None) -> OperacaoHistorico:
    return OperacaoHistorico(
        id=transacao.id,
        data=transacao.data,
        tipo=transacao.tipo,
        ativo_id=transacao.ativo_id,
        instituicao_id=transacao.instituicao_id,
        cambio=transacao.cambio,
        valor_total=valor_total(
            transacao.tipo,
            quantidade=transacao.quantidade,
            preco_unitario=transacao.preco_unitario,
            taxas=transacao.taxas,
            valor=transacao.valor,
        ),
        taxas=transacao.taxas,
        imposto_retido=transacao.imposto_retido,
        resultado=resultado,
    )


def operacao_da_transacao(
    sessao: Session, transacao: m.Transacao, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> tuple[OperacaoHistorico, SituacaoPosicao]:
    """Valores do histórico de uma transação (usado nas respostas de cadastro/edição)."""
    ativo = RepositorioAtivos(sessao).obter(transacao.ativo_id)
    if ativo is None:  # pragma: no cover - chave estrangeira garante o ativo
        raise ValueError("Transação sem ativo.")
    analise = _analisar(sessao, {ativo.id: ativo}, registro)
    situacao = analise.da_posicao(transacao.ativo_id, transacao.instituicao_id)
    return _operacao(transacao, analise.resultados.get(transacao.id)), situacao


# ------------------------------------------------------------------------------ consulta


def _passa(item: ItemHistorico, filtro: FiltroHistorico) -> bool:
    if filtro.situacao is not None and item.situacao is not filtro.situacao:
        return False
    if filtro.apenas_prejuizo and not item.operacao.prejuizo:
        return False
    return not (filtro.apenas_com_custos and not item.operacao.tem_custos)


def _rotulo_ativo(ativo: m.Ativo) -> str:
    return (ativo.simbolo or ativo.nome).casefold()


CHAVES_ORDEM: dict[CampoOrdem, Callable[[ItemHistorico], object]] = {
    CampoOrdem.OPERACAO: lambda i: i.transacao.tipo.value,
    CampoOrdem.ATIVO: lambda i: _rotulo_ativo(i.ativo),
    CampoOrdem.INSTITUICAO: lambda i: i.instituicao.nome.casefold(),
    CampoOrdem.QUANTIDADE: lambda i: i.transacao.quantidade,
    CampoOrdem.PRECO_UNITARIO: lambda i: i.transacao.preco_unitario,
    CampoOrdem.TAXAS: lambda i: i.operacao.taxas_brl,
    CampoOrdem.VALOR_TOTAL: lambda i: i.operacao.valor_total_brl,
    CampoOrdem.RESULTADO: lambda i: (
        None if i.operacao.resultado is None else i.operacao.resultado.resultado_brl
    ),
}


def ordenar(
    itens: Sequence[ItemHistorico], campo: CampoOrdem, direcao: Direcao
) -> list[ItemHistorico]:
    """Ordena pelo campo; empates (e sempre o desempate) pela data/registro mais recente.

    Itens sem valor no campo (ex.: quantidade de um aporte, resultado de uma compra) vão
    para o fim nas duas direções.
    """
    base = sorted(itens, key=lambda i: (i.transacao.data, i.transacao.id), reverse=True)
    if campo is CampoOrdem.DATA:
        return base if direcao is Direcao.DESC else base[::-1]
    chave = CHAVES_ORDEM[campo]
    com_valor = [i for i in base if chave(i) is not None]
    sem_valor = [i for i in base if chave(i) is None]
    # sorted é estável: o desempate pela data mais recente se mantém nos dois sentidos.
    ordenados = sorted(com_valor, key=chave, reverse=direcao is Direcao.DESC)  # type: ignore[arg-type]
    return ordenados + sem_valor


def consultar(
    sessao: Session,
    filtro: FiltroHistorico,
    campo: CampoOrdem = CampoOrdem.DATA,
    direcao: Direcao = Direcao.DESC,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> ConsultaHistorico:
    transacoes = RepositorioTransacoes(sessao).filtradas(
        ativo_id=filtro.ativo_id,
        instituicao_id=filtro.instituicao_id,
        tipos=filtro.tipos,
        inicio=filtro.inicio,
        fim=filtro.fim,
        tipo_ativo=filtro.tipo_ativo,
        moeda=filtro.moeda,
        busca=filtro.busca,
    )
    repositorio_ativos = RepositorioAtivos(sessao)
    ativos: dict[int, m.Ativo] = {}
    for ativo_id in {t.ativo_id for t in transacoes}:
        ativo = repositorio_ativos.obter(ativo_id)
        if ativo is not None:
            ativos[ativo_id] = ativo
    instituicoes = {i.id: i for i in RepositorioInstituicoes(sessao).listar()}
    analise = _analisar(sessao, ativos, registro)

    por_posicao = filtro.instituicao_id is not None

    def situacao(transacao: m.Transacao) -> SituacaoPosicao:
        if por_posicao:
            return analise.da_posicao(transacao.ativo_id, transacao.instituicao_id)
        return analise.do_ativo(transacao.ativo_id)

    itens = [
        ItemHistorico(
            transacao=t,
            ativo=ativos[t.ativo_id],
            instituicao=instituicoes[t.instituicao_id],
            operacao=_operacao(t, analise.resultados.get(t.id)),
            situacao=situacao(t),
        )
        for t in transacoes
    ]
    filtrados = [i for i in itens if _passa(i, filtro)]

    def situacao_ativo(ativo_id: int) -> SituacaoPosicao:
        if filtro.instituicao_id is not None:
            return analise.da_posicao(ativo_id, filtro.instituicao_id)
        return analise.do_ativo(ativo_id)

    return ConsultaHistorico(
        itens=ordenar(filtrados, campo, direcao),
        situacao_posicao=analise.da_posicao,
        situacao_ativo=situacao_ativo,
    )


def contar_todas(sessao: Session) -> int:
    """Total de transações sem filtro nenhum (o "M" de "N de M operações")."""
    return sessao.scalar(select(func.count()).select_from(m.Transacao)) or 0


def resumir(
    sessao: Session,
    filtro: FiltroHistorico,
    hoje: date,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> ResumoHistorico:
    """Totais dos cartões, série mensal do gráfico e a visão por ativo do filtro.

    Período do gráfico: do início do filtro (ou da operação mais antiga encontrada) até o
    fim do filtro (ou hoje). Sem operações e sem início, a série fica vazia.
    """
    consulta = consultar(sessao, filtro, registro=registro)
    operacoes = [i.operacao for i in consulta.itens]
    inicio = filtro.inicio or (min(op.data for op in operacoes) if operacoes else None)
    fim = filtro.fim or hoje
    serie = serie_mensal(operacoes, inicio, fim) if inicio is not None else []
    # A visão por ativo segue a ordem do histórico (data mais recente primeiro).
    por_ativo = agrupar_por_ativo(operacoes, consulta.situacao_posicao, consulta.situacao_ativo)
    return ResumoHistorico(
        totais=totalizar(operacoes),
        total_sem_filtros=contar_todas(sessao),
        inicio=inicio,
        fim=fim,
        serie=serie,
        por_ativo=por_ativo,
    )


def tipos_efetivos(
    tipo: TipoTransacao | None, tipos: Collection[TipoTransacao] | None
) -> frozenset[TipoTransacao] | None:
    """Combina o filtro antigo ``tipo`` (um só) com a lista ``tipos`` (interseção)."""
    conjunto = frozenset(tipos) if tipos else None
    if tipo is None:
        return conjunto
    if conjunto is None:
        return frozenset({tipo})
    return conjunto & {tipo}
