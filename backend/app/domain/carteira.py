"""Agregação da carteira: Análise Geral e Análise por Instituição, alocação e patrimônio.

- Uma posição é calculada por (ativo, instituição). A **Análise Geral** soma as posições
  do mesmo ativo em todas as instituições; a **Análise por Instituição** filtra as
  posições e o caixa de uma instituição.
- Patrimônio = investimentos (valor atual em BRL) + caixa (saldo das contas correntes em BRL).
- Alocação por tipo de ativo, com a fatia ``caixa``.
- Falhas de avaliação (câmbio/indicador ausente) ficam registradas na posição
  (``erro``) e não impedem o resto; o resumo marca ``completo = False``.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from app.domain.enums import OrigemPreco
from app.domain.metricas import Metricas, calcular_metricas
from app.domain.numeros import ZERO, dividir
from app.domain.posicao import ValoresPosicao

GRUPO_CAIXA = "caixa"


@dataclass(frozen=True)
class Avaliacao:
    """Valor atual de uma posição e de onde ele veio."""

    valor: Decimal | None  # moeda do ativo
    valor_brl: Decimal | None
    preco_unitario: Decimal | None = None
    origem: OrigemPreco | None = None
    data_preco: date | None = None
    defasado: bool = False
    aviso: str | None = None
    erro: str | None = None


@dataclass(frozen=True)
class PosicaoAvaliada:
    ativo_id: int
    tipo_ativo: str
    moeda: str
    instituicao_id: int | None  # None na Análise Geral (consolidada)
    quantidade: Decimal | None  # None para posições por montante
    valores: ValoresPosicao  # moeda do ativo
    valores_brl: ValoresPosicao
    avaliacao: Avaliacao

    @property
    def aberta(self) -> bool:
        if self.quantidade is None:
            return self.valores.custo > ZERO
        return self.quantidade > ZERO

    @property
    def preco_medio(self) -> Decimal | None:
        if not self.quantidade:
            return None
        return dividir(self.valores.custo, self.quantidade)

    @property
    def metricas(self) -> Metricas | None:
        if self.avaliacao.valor is None:
            return None
        return calcular_metricas(self.avaliacao.valor, self.valores)

    @property
    def metricas_brl(self) -> Metricas | None:
        if self.avaliacao.valor_brl is None:
            return None
        return calcular_metricas(self.avaliacao.valor_brl, self.valores_brl)


@dataclass(frozen=True)
class SaldoCaixa:
    instituicao_id: int
    moeda: str
    saldo: Decimal  # na moeda da conta
    saldo_brl: Decimal | None
    erro: str | None = None
    defasado: bool = False  # câmbio usado na conversão está defasado
    aviso: str | None = None


@dataclass(frozen=True)
class FatiaAlocacao:
    grupo: str  # slug do tipo de ativo ou "caixa"
    valor: Decimal  # BRL
    percentual: Decimal  # razão (0,25 = 25%)


@dataclass(frozen=True)
class ResumoCarteira:
    posicoes: tuple[PosicaoAvaliada, ...]
    caixas: tuple[SaldoCaixa, ...]
    investimentos_brl: Decimal
    caixa_brl: Decimal
    patrimonio_brl: Decimal
    alocacao: tuple[FatiaAlocacao, ...]
    completo: bool  # False se alguma posição/conta não pôde ser avaliada


def _somar_opcional(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    return None if a is None or b is None else a + b


def _juntar_textos(textos: Iterable[str | None]) -> str | None:
    unicos = list(dict.fromkeys(t for t in textos if t))
    return " ".join(unicos) if unicos else None


def _consolidar_avaliacoes(avaliacoes: list[Avaliacao]) -> Avaliacao:
    primeira = avaliacoes[0]
    valor: Decimal | None = primeira.valor
    valor_brl: Decimal | None = primeira.valor_brl
    for outra in avaliacoes[1:]:
        valor = _somar_opcional(valor, outra.valor)
        valor_brl = _somar_opcional(valor_brl, outra.valor_brl)
    return Avaliacao(
        valor=valor,
        valor_brl=valor_brl,
        preco_unitario=primeira.preco_unitario,
        origem=primeira.origem,
        data_preco=primeira.data_preco,
        defasado=any(a.defasado for a in avaliacoes),
        aviso=_juntar_textos(a.aviso for a in avaliacoes),
        erro=_juntar_textos(a.erro for a in avaliacoes),
    )


def consolidar_por_ativo(posicoes: Iterable[PosicaoAvaliada]) -> list[PosicaoAvaliada]:
    """Análise Geral: uma posição por ativo, somando todas as instituições."""
    grupos: dict[int, list[PosicaoAvaliada]] = defaultdict(list)
    for posicao in posicoes:
        grupos[posicao.ativo_id].append(posicao)
    consolidadas: list[PosicaoAvaliada] = []
    for ativo_id in sorted(grupos):
        itens = grupos[ativo_id]
        primeira = itens[0]
        quantidade = primeira.quantidade
        valores, valores_brl = primeira.valores, primeira.valores_brl
        for item in itens[1:]:
            quantidade = _somar_opcional(quantidade, item.quantidade)
            valores += item.valores
            valores_brl += item.valores_brl
        consolidadas.append(
            replace(
                primeira,
                instituicao_id=None,
                quantidade=quantidade,
                valores=valores,
                valores_brl=valores_brl,
                avaliacao=_consolidar_avaliacoes([i.avaliacao for i in itens]),
            )
        )
    return consolidadas


def calcular_alocacao(valores_por_grupo: Mapping[str, Decimal]) -> tuple[FatiaAlocacao, ...]:
    """Participação de cada grupo no total (grupos com valor ≤ 0 ficam de fora)."""
    positivos = {grupo: valor for grupo, valor in valores_por_grupo.items() if valor > ZERO}
    total = sum(positivos.values(), ZERO)
    if total == ZERO:
        return ()
    fatias = [
        FatiaAlocacao(grupo=grupo, valor=valor, percentual=dividir(valor, total))
        for grupo, valor in positivos.items()
    ]
    return tuple(sorted(fatias, key=lambda f: (-f.valor, f.grupo)))


def resumir_carteira(
    posicoes: Iterable[PosicaoAvaliada], caixas: Iterable[SaldoCaixa]
) -> ResumoCarteira:
    lista_posicoes = tuple(posicoes)
    lista_caixas = tuple(caixas)
    por_grupo: dict[str, Decimal] = defaultdict(lambda: ZERO)
    investimentos = ZERO
    for posicao in lista_posicoes:
        valor = posicao.avaliacao.valor_brl
        if valor is not None:
            investimentos += valor
            por_grupo[posicao.tipo_ativo] += valor
    caixa = sum((c.saldo_brl for c in lista_caixas if c.saldo_brl is not None), ZERO)
    if caixa:
        por_grupo[GRUPO_CAIXA] += caixa
    completo = all(p.avaliacao.valor_brl is not None for p in lista_posicoes) and all(
        c.saldo_brl is not None for c in lista_caixas
    )
    return ResumoCarteira(
        posicoes=lista_posicoes,
        caixas=lista_caixas,
        investimentos_brl=investimentos,
        caixa_brl=caixa,
        patrimonio_brl=investimentos + caixa,
        alocacao=calcular_alocacao(por_grupo),
        completo=completo,
    )
