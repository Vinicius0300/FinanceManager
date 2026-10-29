"""Série diária de evolução do patrimônio, reconstruída do histórico (usa pandas).

Uma posição ou conta que não pode ser reconstruída não derruba a série: ela entra
pelo custo (posições) ou fica de fora (contas sem câmbio), e o motivo vai em ``avisos``.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy.orm import Session

from app.asset_types.base import HandlerMontante
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import TipoIndicador, TipoTransacao
from app.domain.erros import DominioError
from app.domain.indicadores import Indicadores
from app.domain.moedas import MOEDA_BASE
from app.domain.numeros import ZERO
from app.domain.posicao import historico_posicao
from app.domain.serie_patrimonio import (
    SerieDecimal,
    montar_serie_patrimonio,
    serie_caixa,
    serie_degraus,
    serie_valor_cotas,
    serie_valor_montante,
)
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.repositories.contas import RepositorioContas
from app.repositories.transacoes import RepositorioEventos, RepositorioTransacoes
from app.services.caixa import lancamentos, movimentos_da_conta
from app.services.mercado import carregar_indicadores, carregar_precos
from app.services.posicoes import agrupar_por_posicao, operacao_montante, operacoes_cotas


@dataclass(frozen=True)
class PontoPatrimonio:
    data: date
    investimentos: Decimal
    caixa: Decimal
    patrimonio: Decimal


@dataclass(frozen=True)
class SeriePatrimonio:
    pontos: tuple[PontoPatrimonio, ...]
    avisos: tuple[str, ...]


def _cambios(indicadores: Indicadores, moeda: str) -> list[tuple[date, Decimal]] | None:
    if moeda == MOEDA_BASE:
        return None
    serie = indicadores.serie(TipoIndicador.CAMBIO, moeda)
    return [(p.data, p.valor) for p in serie.pontos]


def _custo_nominal(transacoes: list[m.Transacao]) -> list[tuple[date, Decimal]]:
    """Plano B para montante: aportes − resgates (sem rendimento), nunca abaixo de zero."""
    saldo = ZERO
    pontos: list[tuple[date, Decimal]] = []
    for transacao in sorted(transacoes, key=lambda t: (t.data, t.id)):
        valor = transacao.valor or ZERO
        saldo += valor if transacao.tipo is TipoTransacao.APORTE else -valor
        saldo = max(saldo, ZERO)
        pontos.append((transacao.data, saldo))
    return pontos


def serie_patrimonio(
    sessao: Session,
    inicio: date,
    fim: date,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> SeriePatrimonio:
    indicadores = carregar_indicadores(sessao)
    ativos = {a.id: a for a in RepositorioAtivos(sessao).listar()}
    eventos_repo = RepositorioEventos(sessao)
    investimentos: list[SerieDecimal] = []
    avisos: list[str] = []

    grupos = agrupar_por_posicao(RepositorioTransacoes(sessao).listar_ate(fim))
    for chave in sorted(grupos, key=lambda c: (c.ativo_id, c.instituicao_id)):
        ativo, transacoes = ativos[chave.ativo_id], grupos[chave]
        handler = registro.obter(ativo.tipo)
        try:
            if isinstance(handler, HandlerMontante):
                fator = handler.criar_fator(ativo.metadados, indicadores)
                operacoes = [operacao_montante(t) for t in transacoes]
                investimentos.append(serie_valor_montante(operacoes, fator, inicio, fim))
            else:
                operacoes_ativo = operacoes_cotas(
                    transacoes, eventos_repo.do_ativo(ativo.id, fim), ativo.moeda, indicadores
                )
                precos = carregar_precos(sessao, ativo.id).ultimo_por_dia()
                investimentos.append(
                    serie_valor_cotas(
                        historico_posicao(operacoes_ativo),
                        precos,
                        _cambios(indicadores, ativo.moeda),
                        inicio,
                        fim,
                    )
                )
        except DominioError as falha:
            avisos.append(f"{ativo.nome}: {falha.mensagem} Considerado pelo valor aplicado.")
            investimentos.append(serie_degraus(_custo_nominal(transacoes), inicio, fim))

    caixas: list[SerieDecimal] = []
    for conta in RepositorioContas(sessao).listar():
        serie = serie_caixa(
            lancamentos(movimentos_da_conta(sessao, conta.id, fim)),
            _cambios(indicadores, conta.moeda),
            inicio,
            fim,
        )
        if serie is None:
            avisos.append(
                f"Conta {conta.instituicao.nome} ({conta.moeda}) fora da série: "
                f"não há câmbio {conta.moeda}/BRL registrado."
            )
        else:
            caixas.append(serie)

    quadro = montar_serie_patrimonio(investimentos, caixas, inicio, fim)
    pontos = tuple(
        PontoPatrimonio(pd.Timestamp(marca).date(), investido, caixa, total)
        for marca, investido, caixa, total in zip(
            quadro.index,
            quadro["investimentos"],
            quadro["caixa"],
            quadro["patrimonio"],
            strict=True,
        )
    )
    return SeriePatrimonio(pontos=pontos, avisos=tuple(avisos))
