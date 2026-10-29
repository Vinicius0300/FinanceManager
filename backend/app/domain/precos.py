"""Histórico de preços de um ativo como objeto puro.

Um preço por ativo por dia (data local de Brasília): a cada coleta do dia o registro do
dia é atualizado, e o último valor do dia é o fechamento. Fechamentos baixados do
histórico de uma fonte recebem o instante :data:`HORA_FECHAMENTO` do próprio dia.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from app.domain.enums import OrigemPreco
from app.domain.numeros import UM, ZERO, dividir
from app.domain.tempo import FUSO_LOCAL, data_local

HORA_FECHAMENTO = time(18)
"""Horário (Brasília) atribuído a um fechamento diário vindo do histórico de uma fonte."""


def instante_fechamento(dia: date) -> datetime:
    """Instante usado para o fechamento de ``dia`` (18h de Brasília)."""
    return datetime.combine(dia, HORA_FECHAMENTO, tzinfo=FUSO_LOCAL)


def variacao(atual: Decimal, anterior: Decimal) -> Decimal | None:
    """Variação (razão) de ``atual`` sobre ``anterior``: 11 sobre 10 → 0,1 (10%)."""
    if anterior <= ZERO:
        return None
    return dividir(atual, anterior) - UM


@dataclass(frozen=True)
class PontoPreco:
    data_hora: datetime  # com fuso (gravado em UTC)
    valor: Decimal  # na moeda do ativo
    origem: OrigemPreco

    @property
    def data(self) -> date:
        return data_local(self.data_hora)


class SeriePrecos:
    """Preços ordenados por instante; a "data" de cada preço é a data local."""

    def __init__(self, pontos: Iterable[PontoPreco] = ()) -> None:
        self._pontos = sorted(pontos, key=lambda p: p.data_hora)
        self._datas = [p.data for p in self._pontos]

    @property
    def vazia(self) -> bool:
        return not self._pontos

    def ultimo_ate(self, dia: date) -> PontoPreco | None:
        """Último preço cuja data local é ≤ ``dia``."""
        indice = bisect_right(self._datas, dia)
        return self._pontos[indice - 1] if indice else None

    def anterior_a(self, dia: date) -> PontoPreco | None:
        """Último preço com data local estritamente anterior a ``dia``."""
        indice = bisect_left(self._datas, dia)
        return self._pontos[indice - 1] if indice else None

    def ultimo_por_dia(self) -> list[tuple[date, Decimal]]:
        """Um preço por dia (o último do dia), em ordem de data."""
        por_dia: dict[date, Decimal] = {}
        for ponto in self._pontos:
            por_dia[ponto.data] = ponto.valor
        return sorted(por_dia.items())
