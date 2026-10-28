"""Caminhos dos dados do usuário, centralizados aqui.

Tudo fica em ``%APPDATA%\\Financas\\`` (nunca na pasta de instalação). A variável de
ambiente ``FINANCAS_DATA_DIR`` sobrescreve a raiz, o que é usado pelos testes.
"""

import os
from pathlib import Path

NOME_PASTA_APP = "Financas"
VARIAVEL_RAIZ = "FINANCAS_DATA_DIR"


def diretorio_dados() -> Path:
    """Raiz dos dados do usuário."""
    sobrescrita = os.environ.get(VARIAVEL_RAIZ)
    if sobrescrita:
        return Path(sobrescrita)
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / NOME_PASTA_APP


def diretorio_logs() -> Path:
    return diretorio_dados() / "logs"


def diretorio_backups() -> Path:
    return diretorio_dados() / "backups"


def diretorio_models() -> Path:
    return diretorio_dados() / "models"


def caminho_banco() -> Path:
    return diretorio_dados() / "financas.db"


def garantir_diretorios() -> None:
    """Cria a estrutura de pastas se ainda não existir (idempotente)."""
    for pasta in (diretorio_dados(), diretorio_logs(), diretorio_backups(), diretorio_models()):
        pasta.mkdir(parents=True, exist_ok=True)
