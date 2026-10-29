"""Interfaces (``Protocol``) da futura camada de previsão e sugestão.

**Nenhum modelo é implementado agora.** Os contratos usam só a biblioteca padrão e
pandas (já dependência do app), para que implementações com ML pesado (scikit-learn,
statsmodels, PyTorch...) fiquem em pacotes **opcionais** e importados sob demanda.
Plano completo em ``docs/ANALYTICS.md``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True)
class Previsao:
    """Valor previsto para um alvo (ex.: preço de um ativo) numa data futura."""

    alvo: str  # ex.: "ativo:12:preco"
    data_referencia: date  # quando a previsão foi feita
    data_alvo: date  # a que data ela se refere
    valor: Decimal
    limite_inferior: Decimal | None = None
    limite_superior: Decimal | None = None


@dataclass(frozen=True)
class Sugestao:
    """Sugestão de ação gerada por uma estratégia (nunca executada automaticamente)."""

    data_referencia: date
    acao: str  # ex.: "rebalancear", "aportar"
    ativo_id: int | None
    justificativa: str
    confianca: Decimal | None = None  # razão entre 0 e 1
    detalhes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoBacktest:
    inicio: date
    fim: date
    metricas: Mapping[str, Decimal]  # ex.: {"retorno_total": ..., "max_drawdown": ...}
    previsoes: Sequence[Previsao] = ()


@runtime_checkable
class FeatureBuilder(Protocol):
    """Transforma dados históricos (preços, indicadores, carteira) em features."""

    nome: str

    def construir(self, dados: Mapping[str, pd.DataFrame], data_referencia: date) -> pd.DataFrame:
        """Devolve uma tabela de features usando só dados até ``data_referencia``."""
        ...


@runtime_checkable
class Predictor(Protocol):
    """Modelo de previsão treinável e persistível em ``%APPDATA%\\Financas\\models``."""

    nome: str
    versao: str

    def treinar(self, features: pd.DataFrame, alvo: pd.Series) -> None: ...

    def prever(self, features: pd.DataFrame, data_referencia: date) -> Sequence[Previsao]: ...


@runtime_checkable
class Strategy(Protocol):
    """Estratégia que transforma previsões e a carteira atual em sugestões."""

    nome: str
    versao: str

    def sugerir(
        self, previsoes: Sequence[Previsao], carteira: pd.DataFrame, data_referencia: date
    ) -> Sequence[Sugestao]: ...


@runtime_checkable
class Backtester(Protocol):
    """Avalia um preditor ou estratégia em janelas históricas, sem olhar o futuro."""

    def executar(
        self,
        modelo: Predictor | Strategy,
        dados: Mapping[str, pd.DataFrame],
        inicio: date,
        fim: date,
    ) -> ResultadoBacktest: ...
