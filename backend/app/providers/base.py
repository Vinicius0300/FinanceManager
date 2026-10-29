"""Contrato comum das fontes de cotação e de indicadores.

Cada fonte é uma classe própria que implementa :class:`ProviderCotacao` (preços de
ativos) e/ou :class:`ProviderIndicador` (Selic, CDI, IPCA, câmbio), registrada em
``providers/catalogo.py``. Trocar ou acrescentar uma fonte não altera as outras.

Regras de todos os providers:
- rede só pelo :class:`~app.providers.http.ClienteHttp` (timeout, retry com backoff,
  rate limit e cache curto);
- valores sempre em ``Decimal`` **arredondados antes de devolver**: cotação até 8 casas e
  câmbio até 6 (``registrar_preco``/``registrar_indicador`` recusam mais casas);
- falha de um alvo vira :class:`ProviderError` **naquele alvo** (os demais seguem); a
  mensagem já está em pt-BR para o usuário.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.domain.enums import TipoIndicador
from app.domain.indicadores import PontoIndicador
from app.domain.numeros import CASAS_CAMBIO, CASAS_PRECO, CONTEXTO, ZERO, arredondar, dec


class ProviderError(Exception):
    """Falha de uma fonte de dados, com mensagem em pt-BR."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


class FonteIndisponivelError(ProviderError):
    """Rede fora, tempo esgotado ou erro do servidor da fonte (tente de novo depois)."""


class LimiteRequisicoesError(FonteIndisponivelError):
    """A fonte recusou por excesso de requisições (HTTP 429)."""


class SimboloNaoEncontradoError(ProviderError):
    """A fonte não conhece o ativo (símbolo, id, CNPJ ou título)."""


class RespostaInvalidaError(ProviderError):
    """A fonte respondeu num formato inesperado."""


@dataclass(frozen=True)
class AlvoCotacao:
    """O que um provider precisa saber de um ativo para cotá-lo."""

    ativo_id: int
    tipo: str
    nome: str
    moeda: str
    simbolo: str | None = None
    simbolo_externo: str | None = None
    metadados: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Cotacao:
    data: date  # dia de referência do preço (pregão/data da cota)
    data_hora: datetime  # instante do preço na fonte (com fuso)
    valor: Decimal  # na moeda do ativo, até 8 casas


@dataclass(frozen=True)
class Fechamento:
    data: date
    valor: Decimal  # na moeda do ativo, até 8 casas


@dataclass(frozen=True)
class PedidoHistorico:
    alvo: AlvoCotacao
    inicio: date


ResultadoCotacao = Cotacao | ProviderError
ResultadoHistorico = list[Fechamento] | ProviderError


class ProviderCotacao(Protocol):
    nome: str
    identificador_persistente: bool
    """``True`` se o identificador resolvido deve ser gravado em ``simbolo_externo``
    (ex.: id da CoinGecko, que exige consulta à rede para ser descoberto)."""

    def identificar(self, alvo: AlvoCotacao) -> str:
        """Identificador do ativo na fonte; levanta ``ProviderError`` se não houver."""
        ...

    def cotacoes(self, alvos: Sequence[AlvoCotacao]) -> dict[int, ResultadoCotacao]:
        """Cotação atual de cada alvo (chave: ``ativo_id``)."""
        ...

    def historicos(
        self, pedidos: Sequence[PedidoHistorico], fim: date
    ) -> dict[int, ResultadoHistorico]:
        """Fechamentos diários de ``pedido.inicio`` até ``fim`` (chave: ``ativo_id``)."""
        ...


class ProviderIndicador(Protocol):
    nome: str

    def suporta(self, tipo: TipoIndicador, moeda: str) -> bool: ...

    def serie(
        self, tipo: TipoIndicador, moeda: str, inicio: date, fim: date
    ) -> list[PontoIndicador]:
        """Valores de ``inicio`` a ``fim`` nas unidades da tabela ``indicadores``."""
        ...


def _decimal(bruto: object, rotulo: str) -> Decimal:
    if isinstance(bruto, bool) or not isinstance(bruto, int | float | str | Decimal):
        raise RespostaInvalidaError(f"{rotulo}: valor ausente ou inválido na resposta.")
    try:
        # str(float) dá a representação curta (52.2 → "52.2"), sem lixo binário.
        return dec(str(bruto) if isinstance(bruto, float) else bruto)
    except (ValueError, InvalidOperation) as erro:
        raise RespostaInvalidaError(f"{rotulo}: valor inválido na resposta ({bruto!r}).") from erro


def _arredondado(valor: Decimal, casas: int) -> Decimal:
    # normalize tira zeros à direita (52.20000000 → 52.2) sem mudar o valor.
    return arredondar(valor, casas).normalize(CONTEXTO)


def valor_cotacao(bruto: object, rotulo: str, casas: int = CASAS_PRECO) -> Decimal:
    """Cotação positiva arredondada (padrão 8 casas, nunca mais que 8)."""
    valor = _arredondado(_decimal(bruto, rotulo), min(casas, CASAS_PRECO))
    if valor <= ZERO:
        raise RespostaInvalidaError(f"{rotulo}: a fonte devolveu cotação zerada ou negativa.")
    return valor


def valor_cambio(bruto: object, rotulo: str) -> Decimal:
    """Câmbio positivo arredondado a 6 casas."""
    valor = _arredondado(_decimal(bruto, rotulo), CASAS_CAMBIO)
    if valor <= ZERO:
        raise RespostaInvalidaError(f"{rotulo}: a fonte devolveu câmbio zerado ou negativo.")
    return valor


def valor_taxa(bruto: object, rotulo: str) -> Decimal:
    """Taxa em % (pode ser zero ou negativa, como IPCA de deflação), até 8 casas."""
    return _arredondado(_decimal(bruto, rotulo), CASAS_PRECO)
