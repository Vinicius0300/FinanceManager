"""Conta corrente por instituição (caixa): saldo, efeito das transações e ajuste.

Regras (decididas com o dono):
- compra/aporte debita (quantidade × preço + taxas, ou o valor do aporte);
- venda/resgate credita (quantidade × preço − taxas, ou o valor do resgate);
- provento credita o valor líquido; depósito e saque são manuais;
- o saldo **nunca fica negativo**. A verificação usa o saldo ao **fim de cada dia**
  (movimentos do mesmo dia se compensam), a partir da data do movimento novo, porque
  um lançamento retroativo afeta todos os saldos seguintes.
- se uma compra/aporte excede o saldo, o déficit vira um ``ajuste_saldo`` (depósito
  não informado) na mesma data, que leva o menor saldo futuro exatamente a zero.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import MOVIMENTOS_DE_SAIDA, TipoMovimento, TipoTransacao
from app.domain.numeros import ZERO

MENSAGEM_SALDO_INSUFICIENTE = (
    "Você está movimentando mais dinheiro do que o possível dentro desta conta corrente. "
    "Atualizar valores?"
)


@dataclass(frozen=True)
class LancamentoCaixa:
    """Movimento com sinal: positivo entra na conta, negativo sai."""

    data: date
    valor: Decimal


def valor_com_sinal(tipo: TipoMovimento, valor: Decimal) -> Decimal:
    """Movimentos são gravados com valor positivo; o sinal vem do tipo."""
    return -valor if tipo in MOVIMENTOS_DE_SAIDA else valor


def movimento_da_transacao(
    tipo: TipoTransacao,
    *,
    quantidade: Decimal | None = None,
    preco_unitario: Decimal | None = None,
    taxas: Decimal = ZERO,
    valor: Decimal | None = None,
) -> tuple[TipoMovimento, Decimal]:
    """Tipo e valor (positivo) do movimento automático gerado por uma transação."""
    if tipo in (TipoTransacao.COMPRA, TipoTransacao.VENDA):
        if quantidade is None or preco_unitario is None:
            raise ValueError("Compra e venda exigem quantidade e preço unitário.")
        bruto = quantidade * preco_unitario
        if tipo is TipoTransacao.COMPRA:
            return TipoMovimento.DEBITO_COMPRA, bruto + taxas
        return TipoMovimento.CREDITO_VENDA, bruto - taxas
    if valor is None:
        raise ValueError("Aporte, resgate e provento exigem valor.")
    if tipo is TipoTransacao.APORTE:
        return TipoMovimento.DEBITO_COMPRA, valor
    if tipo is TipoTransacao.RESGATE:
        return TipoMovimento.CREDITO_VENDA, valor
    return TipoMovimento.CREDITO_PROVENTO, valor


def saldo_em(lancamentos: Iterable[LancamentoCaixa], dia: date) -> Decimal:
    """Saldo ao fim de ``dia``."""
    return sum((lanc.valor for lanc in lancamentos if lanc.data <= dia), ZERO)


def saldos_fim_do_dia(lancamentos: Iterable[LancamentoCaixa]) -> list[tuple[date, Decimal]]:
    """Saldo acumulado ao fim de cada dia que teve movimento, em ordem de data."""
    por_dia: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for lanc in lancamentos:
        por_dia[lanc.data] += lanc.valor
    saldo = ZERO
    resultado: list[tuple[date, Decimal]] = []
    for dia in sorted(por_dia):
        saldo += por_dia[dia]
        resultado.append((dia, saldo))
    return resultado


def menor_saldo_a_partir(lancamentos: Iterable[LancamentoCaixa], dia: date) -> Decimal:
    """Menor saldo de fim de dia em ``dia`` ou depois (inclui o saldo vigente em ``dia``)."""
    lista = list(lancamentos)
    candidatos = [saldo_em(lista, dia)]
    candidatos += [saldo for data, saldo in saldos_fim_do_dia(lista) if data >= dia]
    return min(candidatos)


def deficit(lancamentos: Iterable[LancamentoCaixa], a_partir_de: date) -> Decimal:
    """Quanto falta (≥ 0) para nenhum saldo de fim de dia ficar negativo desde ``a_partir_de``."""
    menor = menor_saldo_a_partir(lancamentos, a_partir_de)
    return -menor if menor < ZERO else ZERO
