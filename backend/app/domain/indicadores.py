"""Séries de indicadores de mercado (Selic, CDI, IPCA, câmbio) como objetos puros.

Convenções de unidade (iguais às da tabela ``indicadores``):
- Selic e CDI: % ao ano, um valor por dia (``data`` = dia de referência);
- IPCA: % no mês, um valor por mês (``data`` = primeiro dia do mês de referência);
- câmbio: BRL por 1 unidade da moeda estrangeira, um valor por dia.

Dia sem valor usa o último valor conhecido anterior (preenchimento para frente).
"""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

from app.domain.enums import TipoIndicador
from app.domain.erros import CambioAusenteError, IndicadorAusenteError
from app.domain.moedas import MOEDA_BASE
from app.domain.numeros import UM
from app.domain.tempo import formatar_data

NOMES_INDICADORES = {
    TipoIndicador.SELIC: "Selic",
    TipoIndicador.CDI: "CDI",
    TipoIndicador.IPCA: "IPCA",
    TipoIndicador.CAMBIO: "câmbio",
}


@dataclass(frozen=True)
class PontoIndicador:
    data: date
    valor: Decimal


class SerieIndicador:
    """Série ordenada por data, com consulta "último valor até a data"."""

    def __init__(
        self,
        tipo: TipoIndicador,
        pontos: Iterable[PontoIndicador],
        moeda: str = MOEDA_BASE,
    ) -> None:
        self.tipo = tipo
        self.moeda = moeda
        ordenados = sorted(pontos, key=lambda p: p.data)
        for anterior, atual in pairwise(ordenados):
            if anterior.data == atual.data:
                raise ValueError(f"Data repetida na série de {self.nome}: {atual.data}.")
        self._pontos = ordenados
        self._datas = [p.data for p in ordenados]

    @property
    def nome(self) -> str:
        base = NOMES_INDICADORES[self.tipo]
        return f"{base} {self.moeda}" if self.tipo is TipoIndicador.CAMBIO else base

    @property
    def pontos(self) -> list[PontoIndicador]:
        return list(self._pontos)

    @property
    def vazia(self) -> bool:
        return not self._pontos

    def ponto_em(self, dia: date) -> PontoIndicador | None:
        """Último ponto com data ≤ ``dia`` (ou ``None``)."""
        indice = bisect_right(self._datas, dia)
        return self._pontos[indice - 1] if indice else None

    def valor_em(self, dia: date, *, tolerancia_dias: int | None = None) -> Decimal:
        """Último valor até ``dia``. Levanta ``IndicadorAusenteError`` se não houver
        valor ou se o último for mais antigo que ``tolerancia_dias``."""
        ponto = self.ponto_em(dia)
        if ponto is None:
            raise IndicadorAusenteError(f"Não há {self.nome} registrado até {formatar_data(dia)}.")
        if tolerancia_dias is not None and (dia - ponto.data).days > tolerancia_dias:
            raise IndicadorAusenteError(
                f"O último {self.nome} registrado ({formatar_data(ponto.data)}) é antigo "
                f"demais para {formatar_data(dia)}."
            )
        return ponto.valor


class Indicadores:
    """Conjunto de séries disponíveis para os cálculos (montado pelos services)."""

    def __init__(self, series: Iterable[SerieIndicador] = ()) -> None:
        self._series = {(s.tipo, s.moeda): s for s in series}

    def serie(self, tipo: TipoIndicador, moeda: str = MOEDA_BASE) -> SerieIndicador:
        return self._series.get((tipo, moeda)) or SerieIndicador(tipo, [], moeda)

    def cambio_em(self, moeda: str, dia: date, *, tolerancia_dias: int | None = None) -> Decimal:
        """BRL por unidade de ``moeda`` em ``dia`` (BRL → 1)."""
        if moeda == MOEDA_BASE:
            return UM
        try:
            return self.serie(TipoIndicador.CAMBIO, moeda).valor_em(
                dia, tolerancia_dias=tolerancia_dias
            )
        except IndicadorAusenteError as erro:
            raise CambioAusenteError(
                f"Câmbio {moeda}/BRL indisponível para {formatar_data(dia)}: {erro.mensagem}"
            ) from erro
