"""Tipos de coluna próprios para SQLite.

- ``DecimalTexto``: o SQLite não tem decimal exato (NUMERIC vira REAL/float). Por isso
  dinheiro, quantidades e taxas são gravados como TEXT na forma ``"1234.5600"`` e
  devolvidos como ``Decimal``, sem nenhuma passagem por ``float``.
- ``DataHoraUTC``: instantes são gravados em UTC (sem fuso no texto) e devolvidos com
  ``tzinfo=UTC``. Recusa ``datetime`` sem fuso para não misturar horários locais.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Dialect, String
from sqlalchemy.types import TypeDecorator

from app.domain.numeros import dec, texto_decimal

TAMANHO_DECIMAL = 40


class DecimalTexto(TypeDecorator[Decimal]):
    impl = String(TAMANHO_DECIMAL)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return texto_decimal(dec(value))

    def process_result_value(self, value: object, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"Valor decimal gravado com tipo inesperado: {type(value).__name__}.")
        return dec(value)


class DataHoraUTC(TypeDecorator[datetime]):
    impl = DateTime()
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Data/hora sem fuso horário: informe um datetime com tzinfo.")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)
