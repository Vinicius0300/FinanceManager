"""Tipos comuns dos schemas da API.

**Números decimais trafegam como texto** (``"10.50"``): o front não faz aritmética em
``number`` e nada passa por ``float``. Na entrada também aceitamos inteiros JSON, mas
**recusamos float** (``10.5`` sem aspas), que já chegaria com erro binário.
"""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer, WithJsonSchema

from app.domain.numeros import dec, texto_decimal

T = TypeVar("T")


def _decimal_de_texto(valor: object) -> Decimal:
    if isinstance(valor, (bool, float)):
        raise ValueError('Informe o número como texto (ex.: "10.50").')
    if isinstance(valor, Decimal):
        return valor
    if not isinstance(valor, str | int):
        raise ValueError("Informe um número.")
    try:
        return dec(valor)
    except (ValueError, InvalidOperation) as erro:
        raise ValueError("Número inválido (use ponto como separador decimal).") from erro


Numero = Annotated[
    Decimal,
    BeforeValidator(_decimal_de_texto),
    PlainSerializer(texto_decimal, return_type=str),
    WithJsonSchema({"type": "string", "pattern": r"^-?\d+(\.\d+)?$", "examples": ["10.50"]}),
]
"""Decimal exato como texto (entrada e saída)."""


class Modelo(BaseModel):
    """Base dos schemas: campos desconhecidos são erro (evita digitação silenciosa)."""

    model_config = ConfigDict(extra="forbid")


class Pagina(BaseModel, Generic[T]):
    itens: list[T]
    total: int
    limite: int
    deslocamento: int
