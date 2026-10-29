"""Receitas e despesas: resumo mensal e totais por categoria.

Proventos de investimentos **não** entram aqui (ficam na conta corrente da instituição).
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

    def __post_init__(self) -> None:
        exigir(self.valor > ZERO, "valor", "O valor do lançamento deve ser maior que zero.")


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
