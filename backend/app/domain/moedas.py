"""Moedas: o patrimônio é sempre apresentado em BRL (moeda base)."""

import re

from app.domain.erros import ValidacaoError

MOEDA_BASE = "BRL"
_PADRAO_MOEDA = re.compile(r"^[A-Z]{3}$")


def validar_moeda(codigo: str) -> str:
    """Normaliza e valida um código ISO 4217 (três letras, ex.: BRL, USD)."""
    normalizado = codigo.strip().upper()
    if not _PADRAO_MOEDA.match(normalizado):
        raise ValidacaoError(f"Moeda inválida: {codigo!r}. Use o código de três letras (ex.: BRL).")
    return normalizado
