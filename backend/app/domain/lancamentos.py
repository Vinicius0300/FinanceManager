"""Receitas e despesas: resumo mensal, totais por categoria e resumo por instituição.

Proventos de investimentos **não** entram aqui (ficam na conta corrente da instituição).
Transferências entre instituições (só em BRL) aparecem apenas no resumo por instituição,
em colunas próprias; não entram nos totais nem nas categorias. A tarifa de uma
transferência é uma despesa comum.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import TipoLancamento
from app.domain.erros import exigir
from app.domain.numeros import ZERO, dividir

NOME_SEM_CATEGORIA = "Sem categoria"


@dataclass(frozen=True)
class Lancamento:
    data: date
    tipo: TipoLancamento
    valor: Decimal
    categoria_id: int | None = None
    categoria_nome: str | None = None
    instituicao_id: int | None = None

    def __post_init__(self) -> None:
        exigir(self.valor > ZERO, "valor", "O valor do lançamento deve ser maior que zero.")


@dataclass(frozen=True)
class TransferenciaMes:
    """Transferência em BRL (só o valor; a tarifa já é um lançamento de despesa)."""

    data: date
    origem_id: int
    destino_id: int
    valor: Decimal


@dataclass(frozen=True)
class ResumoInstituicao:
    instituicao_id: int
    receitas: Decimal
    despesas: Decimal
    entrou: Decimal  # transferências recebidas
    saiu: Decimal  # transferências enviadas

    @property
    def saldo(self) -> Decimal:
        """Saldo do mês = receitas − despesas + entrou − saiu (ajustes de saldo não entram)."""
        return self.receitas - self.despesas + self.entrou - self.saiu


@dataclass(frozen=True)
class ResumoMensal:
    ano: int
    mes: int
    total_receitas: Decimal
    total_despesas: Decimal
    saldo: Decimal


@dataclass(frozen=True)
class TotalCategoria:
    tipo: TipoLancamento
    categoria_id: int | None
    categoria_nome: str
    total: Decimal
    percentual: Decimal  # razão sobre o total do tipo no mês


def validar_mes(ano: int, mes: int) -> None:
    exigir(1 <= mes <= 12, "mes", "O mês deve estar entre 1 e 12.")
    exigir(1900 <= ano <= 9999, "ano", "Ano inválido.")


def _do_mes(lancamentos: Iterable[Lancamento], ano: int, mes: int) -> list[Lancamento]:
    validar_mes(ano, mes)
    return [lanc for lanc in lancamentos if lanc.data.year == ano and lanc.data.month == mes]


def resumo_mensal(lancamentos: Iterable[Lancamento], ano: int, mes: int) -> ResumoMensal:
    """Total recebido, total gasto e saldo (receitas − despesas) do mês."""
    do_mes = _do_mes(lancamentos, ano, mes)
    receitas = sum((x.valor for x in do_mes if x.tipo is TipoLancamento.RECEITA), ZERO)
    despesas = sum((x.valor for x in do_mes if x.tipo is TipoLancamento.DESPESA), ZERO)
    return ResumoMensal(
        ano=ano,
        mes=mes,
        total_receitas=receitas,
        total_despesas=despesas,
        saldo=receitas - despesas,
    )


def totais_por_categoria(
    lancamentos: Iterable[Lancamento], ano: int, mes: int
) -> list[TotalCategoria]:
    """Totais do mês por (tipo, categoria), do maior para o menor dentro de cada tipo."""
    do_mes = _do_mes(lancamentos, ano, mes)
    totais: dict[tuple[TipoLancamento, int | None], Decimal] = defaultdict(lambda: ZERO)
    nomes: dict[int | None, str] = {None: NOME_SEM_CATEGORIA}
    for lanc in do_mes:
        totais[(lanc.tipo, lanc.categoria_id)] += lanc.valor
        if lanc.categoria_id is not None:
            nomes[lanc.categoria_id] = lanc.categoria_nome or NOME_SEM_CATEGORIA
    total_por_tipo: dict[TipoLancamento, Decimal] = defaultdict(lambda: ZERO)
    for (tipo, _), valor in totais.items():
        total_por_tipo[tipo] += valor
    resultado = [
        TotalCategoria(
            tipo=tipo,
            categoria_id=categoria_id,
            categoria_nome=nomes[categoria_id],
            total=valor,
            percentual=dividir(valor, total_por_tipo[tipo]),
        )
        for (tipo, categoria_id), valor in totais.items()
    ]
    ordem_tipo = {TipoLancamento.RECEITA: 0, TipoLancamento.DESPESA: 1}
    return sorted(resultado, key=lambda t: (ordem_tipo[t.tipo], -t.total, t.categoria_nome))


def resumo_por_instituicao(
    lancamentos: Iterable[Lancamento],
    transferencias: Iterable[TransferenciaMes],
    ano: int,
    mes: int,
) -> list[ResumoInstituicao]:
    """Receitas, despesas e transferências do mês por instituição (ordem: id).

    Ex.: Nubank com salário de 5.000, aluguel de 2.000, tarifa de 10 e transferência de
    1.000 para o Itaú → 5.000 − 2.010 + 0 − 1.000 = 1.990.
    """
    do_mes = _do_mes(lancamentos, ano, mes)
    vazio = (ZERO, ZERO, ZERO, ZERO)
    totais: dict[int, tuple[Decimal, Decimal, Decimal, Decimal]] = defaultdict(lambda: vazio)
    for lanc in do_mes:
        if lanc.instituicao_id is None:
            continue
        receitas, despesas, entrou, saiu = totais[lanc.instituicao_id]
        if lanc.tipo is TipoLancamento.RECEITA:
            receitas += lanc.valor
        else:
            despesas += lanc.valor
        totais[lanc.instituicao_id] = (receitas, despesas, entrou, saiu)
    for transf in transferencias:
        if transf.data.year != ano or transf.data.month != mes:
            continue
        r, d, e, s = totais[transf.origem_id]
        totais[transf.origem_id] = (r, d, e, s + transf.valor)
        r, d, e, s = totais[transf.destino_id]
        totais[transf.destino_id] = (r, d, e + transf.valor, s)
    return [
        ResumoInstituicao(instituicao_id, *valores)
        for instituicao_id, valores in sorted(totais.items())
    ]
