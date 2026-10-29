"""Números e dinheiro com ``Decimal``: construção segura, contexto e arredondamento.

Regras do projeto (únicas, documentadas aqui):

- Todo valor numérico é ``Decimal`` construído de ``str``, ``int`` ou ``Decimal``.
  ``float`` é recusado com ``TypeError``, porque já chega com erro binário.
- O contexto de cálculo é :data:`CONTEXTO`: 28 dígitos significativos,
  ``ROUND_HALF_EVEN`` (arredondamento bancário) e exceção em operação inválida,
  divisão por zero e estouro. Divisão e potência usam esse contexto explicitamente
  (:func:`dividir` e :func:`potencia`), pois são as operações que geram dízimas.
  Soma, subtração e multiplicação de valores financeiros cabem nos 28 dígitos.
- Cálculo interno com precisão cheia; arredondamento **só na apresentação**:
  :func:`arredondar_moeda` (2 casas), :func:`arredondar_quantidade` (8 casas)
  e :func:`percentual` (razão → % com 2 casas). A exceção é o movimento de caixa de
  uma compra/venda, arredondado a centavos como no extrato da corretora.
- **Entrada do usuário** com casas limitadas (valores com mais casas são recusados,
  nunca arredondados em silêncio, ver :func:`exigir_casas`): dinheiro 2, quantidade 8,
  preço unitário 8, câmbio 6.
"""

from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
)

from app.domain.erros import exigir

CONTEXTO = Context(
    prec=28,
    rounding=ROUND_HALF_EVEN,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)

ZERO = Decimal(0)
UM = Decimal(1)
CEM = Decimal(100)

CASAS_MOEDA = 2
CASAS_QUANTIDADE = 8
CASAS_PERCENTUAL = 2
CASAS_PRECO = 8
CASAS_CAMBIO = 6

NumeroEntrada = Decimal | int | str


def dec(valor: NumeroEntrada) -> Decimal:
    """Converte para ``Decimal`` com segurança (recusa ``float``, ``bool``, NaN e infinito)."""
    if isinstance(valor, bool) or not isinstance(valor, Decimal | int | str):
        raise TypeError(
            "Valor numérico deve ser Decimal, int ou str "
            f"(recebido {type(valor).__name__}); float é proibido."
        )
    try:
        if isinstance(valor, Decimal):
            resultado = valor
        elif isinstance(valor, str):
            resultado = Decimal(valor.strip())
        else:
            resultado = Decimal(valor)
    except InvalidOperation as erro:
        raise ValueError(f"Número inválido: {valor!r}.") from erro
    if not resultado.is_finite():
        raise ValueError(f"Número inválido: {valor!r}.")
    return resultado


def dividir(dividendo: Decimal, divisor: Decimal) -> Decimal:
    """Divisão no contexto do projeto (levanta ``DivisionByZero`` se o divisor for zero)."""
    return CONTEXTO.divide(dividendo, divisor)


def potencia(base: Decimal, expoente: Decimal) -> Decimal:
    """Potência no contexto do projeto (aceita expoente fracionário com base positiva)."""
    return CONTEXTO.power(base, expoente)


def arredondar(valor: Decimal, casas: int) -> Decimal:
    """Arredonda com ``ROUND_HALF_EVEN`` para ``casas`` decimais."""
    return valor.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_EVEN, context=CONTEXTO)


def arredondar_moeda(valor: Decimal) -> Decimal:
    """Valor monetário para apresentação (2 casas, arredondamento bancário)."""
    return arredondar(valor, CASAS_MOEDA)


def arredondar_quantidade(valor: Decimal) -> Decimal:
    """Quantidade para apresentação (até 8 casas, suficiente para cripto)."""
    return arredondar(valor, CASAS_QUANTIDADE)


def percentual(razao: Decimal) -> Decimal:
    """Converte uma razão (0,15) em percentual de apresentação (15,00)."""
    return arredondar(razao * CEM, CASAS_PERCENTUAL)


def casas_decimais(valor: Decimal) -> int:
    """Casas decimais significativas (zeros à direita não contam: 1,50 tem 1 casa)."""
    expoente = valor.normalize(context=CONTEXTO).as_tuple().exponent
    if not isinstance(expoente, int):
        raise ValueError(f"Número inválido: {valor!r}.")
    return max(-expoente, 0)


def exigir_casas(valor: Decimal | None, casas: int, campo: str) -> None:
    """Recusa (``ValidacaoError``) um valor informado com mais de ``casas`` decimais."""
    exigir(
        valor is None or casas_decimais(valor) <= casas,
        campo,
        f"Use no máximo {casas} casas decimais.",
    )


def texto_decimal(valor: Decimal) -> str:
    """Representação textual sem notação científica, usada para persistir no banco."""
    return format(valor, "f")


def formatar_numero(valor: Decimal) -> str:
    """Texto curto para mensagens ao usuário (sem zeros à direita, vírgula decimal)."""
    texto = format(valor.normalize(context=CONTEXTO), "f")
    return texto.replace(".", ",")


def formatar_dinheiro(valor: Decimal) -> str:
    """Valor monetário para mensagens: 2 casas, milhar com ponto e vírgula decimal (2.000,00)."""
    texto = f"{arredondar_moeda(valor):,.2f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")
