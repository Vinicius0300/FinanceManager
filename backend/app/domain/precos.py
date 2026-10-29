"""Histórico de preços de um ativo como objeto puro."""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.enums import OrigemPreco
from app.domain.tempo import data_local


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

    def ultimo_por_dia(self) -> list[tuple[date, Decimal]]:
        """Um preço por dia (o último do dia), em ordem de data."""
        por_dia: dict[date, Decimal] = {}
        for ponto in self._pontos:
            por_dia[ponto.data] = ponto.valor
        return sorted(por_dia.items())
