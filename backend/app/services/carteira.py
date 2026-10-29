"""Avaliação da carteira em uma data: posições, caixa, patrimônio e alocação.

Cada posição (ativo, instituição) é avaliada isoladamente: uma falha (câmbio ou
indicador ausente) vira ``erro`` naquela posição e as demais continuam. Câmbio antigo
(ver ``domain/indicadores.TOLERANCIA_DEFASAGEM_CAMBIO``) é usado, mas marca a posição
ou a conta como defasada, com aviso.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.asset_types.base import HandlerCotado, HandlerMontante, HandlerTipoAtivo, Valoracao
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.carteira import (
    Avaliacao,
    PosicaoAvaliada,
    ResumoCarteira,
    SaldoCaixa,
    consolidar_por_ativo,
    resumir_carteira,
)
from app.domain.conta_corrente import saldo_em
from app.domain.erros import DominioError
from app.domain.indicadores import Indicadores, aviso_indicador_defasado
from app.domain.posicao import ValoresPosicao
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.repositories.contas import RepositorioContas
from app.repositories.transacoes import RepositorioEventos, RepositorioTransacoes
from app.services.caixa import lancamentos, movimentos_da_conta
from app.services.mercado import carregar_indicadores, carregar_precos
from app.services.posicoes import agrupar_por_posicao, estado_cotas, estado_montante


@dataclass(frozen=True)
class CarteiraAvaliada:
    """Posições por instituição e saldos de caixa numa data, com as duas análises."""

    data_ref: date
    posicoes: tuple[PosicaoAvaliada, ...]
    caixas: tuple[SaldoCaixa, ...]

    def geral(self) -> ResumoCarteira:
        """Análise Geral: cada ativo consolidado entre as instituições."""
        return resumir_carteira(consolidar_por_ativo(self.posicoes), self.caixas)

    def por_instituicao(self, instituicao_id: int) -> ResumoCarteira:
        """Análise por Instituição: só as posições e o caixa daquela instituição."""
        return resumir_carteira(
            [p for p in self.posicoes if p.instituicao_id == instituicao_id],
            [c for c in self.caixas if c.instituicao_id == instituicao_id],
        )

    @property
    def instituicoes(self) -> list[int]:
        ids = {p.instituicao_id for p in self.posicoes if p.instituicao_id is not None}
        ids |= {c.instituicao_id for c in self.caixas}
        return sorted(ids)


def _avaliacao(
    valoracao: Valoracao, moeda: str, indicadores: Indicadores, data_ref: date
) -> Avaliacao:
    valor_brl: Decimal | None = None
    erro = aviso_cambio = None
    cambio_defasado = False
    try:
        cambio = indicadores.cambio_vigente(moeda, data_ref)
        valor_brl = valoracao.valor * cambio.valor
        cambio_defasado, aviso_cambio = cambio.defasado, cambio.aviso
    except DominioError as falha:
        erro = falha.mensagem
    return Avaliacao(
        valor=valoracao.valor,
        valor_brl=valor_brl,
        preco_unitario=valoracao.preco_unitario,
        origem=valoracao.origem,
        data_preco=valoracao.data_preco,
        defasado=valoracao.defasado or cambio_defasado,
        aviso=_juntar_avisos(valoracao.aviso, aviso_cambio),
        erro=erro,
    )


def _juntar_avisos(*avisos: str | None) -> str | None:
    presentes = [a for a in avisos if a]
    return " ".join(presentes) if presentes else None


def _marcar_indicadores_defasados(
    valoracao: Valoracao,
    handler: HandlerMontante,
    ativo: m.Ativo,
    indicadores: Indicadores,
    data_ref: date,
) -> Valoracao:
    """Renda fixa/poupança: defasada se falta o indicador recente usado no cálculo."""
    referencia = handler.referencia_indicadores(ativo.metadados, data_ref)
    avisos = [
        aviso_indicador_defasado(indicadores.serie(tipo), referencia)
        for tipo in sorted(handler.indicadores_necessarios(ativo.metadados))
    ]
    aviso = _juntar_avisos(valoracao.aviso, *avisos)
    if aviso == valoracao.aviso:
        return valoracao
    return replace(valoracao, defasado=True, aviso=aviso)


def _avaliar_posicao(
    sessao: Session,
    ativo: m.Ativo,
    handler: HandlerTipoAtivo,
    instituicao_id: int,
    transacoes: Sequence[m.Transacao],
    eventos: Sequence[m.EventoCorporativo],
    indicadores: Indicadores,
    data_ref: date,
) -> PosicaoAvaliada:
    def posicao(
        quantidade: Decimal | None,
        valores: ValoresPosicao,
        valores_brl: ValoresPosicao,
        avaliacao: Avaliacao,
    ) -> PosicaoAvaliada:
        return PosicaoAvaliada(
            ativo_id=ativo.id,
            tipo_ativo=ativo.tipo,
            moeda=ativo.moeda,
            instituicao_id=instituicao_id,
            quantidade=quantidade,
            valores=valores,
            valores_brl=valores_brl,
            avaliacao=avaliacao,
        )

    try:
        if isinstance(handler, HandlerMontante):
            montante = estado_montante(transacoes, handler, ativo.metadados, indicadores)
            fator = handler.criar_fator(ativo.metadados, indicadores)
            valoracao = _marcar_indicadores_defasados(
                handler.avaliar(montante, fator, data_ref), handler, ativo, indicadores, data_ref
            )
            return posicao(
                None,
                montante.valores,
                montante.valores,
                _avaliacao(valoracao, ativo.moeda, indicadores, data_ref),
            )
        if not isinstance(handler, HandlerCotado):
            raise TypeError(f"Handler sem modo de avaliação conhecido: {handler.slug}.")
        cotas = estado_cotas(transacoes, eventos)
        valoracao = handler.avaliar(cotas, carregar_precos(sessao, ativo.id), data_ref)
        return posicao(
            cotas.quantidade,
            cotas.moeda,
            cotas.brl,
            _avaliacao(valoracao, ativo.moeda, indicadores, data_ref),
        )
    except DominioError as falha:
        return posicao(
            None,
            ValoresPosicao(),
            ValoresPosicao(),
            Avaliacao(valor=None, valor_brl=None, erro=falha.mensagem),
        )


def _avaliar_caixas(sessao: Session, indicadores: Indicadores, data_ref: date) -> list[SaldoCaixa]:
    caixas: list[SaldoCaixa] = []
    for conta in RepositorioContas(sessao).listar():
        valor = saldo_em(lancamentos(movimentos_da_conta(sessao, conta.id, data_ref)), data_ref)
        try:
            cambio = indicadores.cambio_vigente(conta.moeda, data_ref)
        except DominioError as falha:
            caixas.append(
                SaldoCaixa(conta.instituicao_id, conta.moeda, valor, None, erro=falha.mensagem)
            )
            continue
        caixas.append(
            SaldoCaixa(
                conta.instituicao_id,
                conta.moeda,
                valor,
                valor * cambio.valor,
                defasado=cambio.defasado,
                aviso=cambio.aviso,
            )
        )
    return caixas


def avaliar_carteira(
    sessao: Session, data_ref: date, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> CarteiraAvaliada:
    """Avalia todas as posições e contas considerando só o que aconteceu até ``data_ref``."""
    indicadores = carregar_indicadores(sessao)
    ativos = {a.id: a for a in RepositorioAtivos(sessao).listar()}
    eventos_repo = RepositorioEventos(sessao)
    grupos = agrupar_por_posicao(RepositorioTransacoes(sessao).listar_ate(data_ref))
    posicoes: list[PosicaoAvaliada] = []
    for chave in sorted(grupos, key=lambda c: (c.ativo_id, c.instituicao_id)):
        ativo = ativos[chave.ativo_id]
        posicoes.append(
            _avaliar_posicao(
                sessao,
                ativo,
                registro.obter(ativo.tipo),
                chave.instituicao_id,
                grupos[chave],
                eventos_repo.do_ativo(ativo.id, data_ref),
                indicadores,
                data_ref,
            )
        )
    return CarteiraAvaliada(
        data_ref=data_ref,
        posicoes=tuple(posicoes),
        caixas=tuple(_avaliar_caixas(sessao, indicadores, data_ref)),
    )
