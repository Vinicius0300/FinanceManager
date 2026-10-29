"""Ponte entre registros do banco e o domínio de posições.

Converte transações/eventos gravados nas operações puras de ``domain.posicao`` e
``domain.montante`` e recalcula posições por (ativo, instituição). Usado tanto para
**validar** uma operação nova (reprocessando o histórico com ela incluída) quanto para
**avaliar** a carteira e reconstruir a série de patrimônio.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.asset_types.base import HandlerMontante, HandlerTipoAtivo, Metadados
from app.domain.enums import TipoTransacao
from app.domain.indicadores import Indicadores
from app.domain.moedas import MOEDA_BASE
from app.domain.montante import (
    Aporte,
    EstadoMontante,
    OperacaoMontante,
    Resgate,
    aplicar_operacoes_montante,
)
from app.domain.numeros import UM, ZERO
from app.domain.posicao import (
    Compra,
    EstadoPosicao,
    EventoCorporativo,
    OperacaoCotas,
    Provento,
    Venda,
    aplicar_operacoes,
)
from app.repositories import modelos as m

ORDEM_NOVA = 2**62
"""Ordem de uma operação ainda não gravada: fica por último entre as do mesmo dia."""

TOLERANCIA_CAMBIO_DIAS = 7
"""Idade máxima do câmbio buscado em ``indicadores`` quando a operação não informa um."""


def _ordem(identificador: int | None) -> int:
    return ORDEM_NOVA if identificador is None else identificador


def _exigir_decimal(valor: Decimal | None) -> Decimal:
    if valor is None:  # garantido pelas CHECK constraints do banco
        raise ValueError("Transação gravada sem um campo obrigatório.")
    return valor


def operacao_cotas(transacao: m.Transacao) -> OperacaoCotas:
    ordem = _ordem(transacao.id)
    if transacao.tipo is TipoTransacao.PROVENTO:
        return Provento(
            data=transacao.data,
            valor_liquido=_exigir_decimal(transacao.valor),
            imposto_retido=transacao.imposto_retido,
            cambio=transacao.cambio,
            ordem=ordem,
        )
    if transacao.tipo not in (TipoTransacao.COMPRA, TipoTransacao.VENDA):
        raise ValueError(f"Transação {transacao.tipo.value} não pertence a posição em cotas.")
    classe = Compra if transacao.tipo is TipoTransacao.COMPRA else Venda
    return classe(
        data=transacao.data,
        quantidade=_exigir_decimal(transacao.quantidade),
        preco_unitario=_exigir_decimal(transacao.preco_unitario),
        taxas=transacao.taxas,
        cambio=transacao.cambio,
        ordem=ordem,
    )


def operacao_montante(transacao: m.Transacao) -> OperacaoMontante:
    if transacao.tipo not in (TipoTransacao.APORTE, TipoTransacao.RESGATE):
        raise ValueError(f"Transação {transacao.tipo.value} não pertence a posição por montante.")
    classe = Aporte if transacao.tipo is TipoTransacao.APORTE else Resgate
    return classe(transacao.data, _exigir_decimal(transacao.valor), _ordem(transacao.id))


def cambio_do_evento(evento: m.EventoCorporativo, moeda: str, indicadores: Indicadores) -> Decimal:
    """Câmbio para converter o custo atribuído de uma bonificação em ativo estrangeiro."""
    if moeda == MOEDA_BASE or evento.custo_unitario == ZERO:
        return UM
    return indicadores.cambio_em(moeda, evento.data, tolerancia_dias=TOLERANCIA_CAMBIO_DIAS)


def operacao_evento(
    evento: m.EventoCorporativo, moeda: str, indicadores: Indicadores
) -> EventoCorporativo:
    return EventoCorporativo(
        data=evento.data,
        tipo=evento.tipo,
        proporcao_de=evento.proporcao_de,
        proporcao_para=evento.proporcao_para,
        custo_unitario=evento.custo_unitario,
        cambio=cambio_do_evento(evento, moeda, indicadores),
        ordem=_ordem(evento.id),
    )


def operacoes_cotas(
    transacoes: Iterable[m.Transacao],
    eventos: Iterable[m.EventoCorporativo],
    moeda: str,
    indicadores: Indicadores,
) -> list[OperacaoCotas]:
    operacoes: list[OperacaoCotas] = [operacao_cotas(t) for t in transacoes]
    operacoes += [operacao_evento(e, moeda, indicadores) for e in eventos]
    return operacoes


def estado_cotas(
    transacoes: Iterable[m.Transacao],
    eventos: Iterable[m.EventoCorporativo],
    moeda: str,
    indicadores: Indicadores,
) -> EstadoPosicao:
    return aplicar_operacoes(operacoes_cotas(transacoes, eventos, moeda, indicadores))


def estado_montante(
    transacoes: Iterable[m.Transacao],
    handler: HandlerMontante,
    metadados: Metadados,
    indicadores: Indicadores,
) -> EstadoMontante:
    fator = handler.criar_fator(metadados, indicadores)
    return aplicar_operacoes_montante([operacao_montante(t) for t in transacoes], fator)


@dataclass(frozen=True)
class ChavePosicao:
    ativo_id: int
    instituicao_id: int


def agrupar_por_posicao(
    transacoes: Iterable[m.Transacao],
) -> dict[ChavePosicao, list[m.Transacao]]:
    grupos: dict[ChavePosicao, list[m.Transacao]] = defaultdict(list)
    for transacao in transacoes:
        grupos[ChavePosicao(transacao.ativo_id, transacao.instituicao_id)].append(transacao)
    return dict(grupos)


def reprocessar_ativo(
    ativo: m.Ativo,
    handler: HandlerTipoAtivo,
    transacoes: Sequence[m.Transacao],
    eventos: Sequence[m.EventoCorporativo],
    indicadores: Indicadores,
) -> None:
    """Recalcula todas as posições do ativo; levanta ``DominioError`` se alguma ficar inválida."""
    for grupo in agrupar_por_posicao(transacoes).values():
        if isinstance(handler, HandlerMontante):
            estado_montante(grupo, handler, ativo.metadados, indicadores)
        else:
            estado_cotas(grupo, eventos, ativo.moeda, indicadores)


def houve_compra_ate(transacoes: Iterable[m.Transacao], dia: date) -> bool:
    return any(t.tipo is TipoTransacao.COMPRA and t.data <= dia for t in transacoes)
