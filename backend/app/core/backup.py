"""Backup do banco pela API de backup do SQLite (nunca copiando o arquivo aberto).

A API de backup gera uma cópia consistente mesmo com o banco em uso e em WAL.
Toda cópia é validada com ``PRAGMA integrity_check`` antes de ser considerada boa.
A restauração completa (com backup de segurança e confirmação na UI) entra na Parte 4;
aqui existe só o necessário para proteger as migrações.
"""

import logging
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

PREFIXO = "financas"
QUANTIDADE_MANTIDA = 10
_MOTIVO_INVALIDO = re.compile(r"[^a-z0-9_-]+")


class BackupError(Exception):
    """Falha ao criar, validar ou restaurar um backup."""


def _copiar(origem: Path, destino: Path) -> None:
    with (
        closing(sqlite3.connect(origem)) as conexao_origem,
        closing(sqlite3.connect(destino)) as conexao_destino,
    ):
        conexao_origem.backup(conexao_destino)


def validar_integridade(caminho: Path) -> None:
    """Levanta ``BackupError`` se o arquivo não for um SQLite íntegro."""
    try:
        with closing(sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)) as conexao:
            resultado = conexao.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as erro:
        raise BackupError(f"Arquivo de banco inválido: {caminho.name}.") from erro
    if not resultado or resultado[0] != "ok":
        raise BackupError(f"O banco {caminho.name} falhou na verificação de integridade.")


def _nome_livre(pasta: Path, motivo: str, agora: datetime) -> Path:
    base = f"{PREFIXO}-{agora:%Y%m%d-%H%M%S}-{motivo}"
    candidato = pasta / f"{base}.db"
    contador = 1
    while candidato.exists():
        candidato = pasta / f"{base}-{contador}.db"
        contador += 1
    return candidato


def criar_backup(
    banco: Path,
    pasta_backups: Path,
    motivo: str,
    *,
    agora: datetime | None = None,
    manter: int = QUANTIDADE_MANTIDA,
) -> Path:
    """Copia ``banco`` para ``pasta_backups``, valida a cópia e aplica a retenção."""
    if not banco.exists():
        raise BackupError(f"Banco não encontrado para backup: {banco}.")
    motivo_limpo = _MOTIVO_INVALIDO.sub("-", motivo.lower()).strip("-") or "manual"
    pasta_backups.mkdir(parents=True, exist_ok=True)
    destino = _nome_livre(pasta_backups, motivo_limpo, agora or datetime.now(UTC))
    try:
        _copiar(banco, destino)
        validar_integridade(destino)
    except (sqlite3.Error, BackupError) as erro:
        destino.unlink(missing_ok=True)
        raise BackupError(f"Não foi possível criar o backup do banco: {erro}") from erro
    logger.info("Backup criado: %s", destino)
    aplicar_retencao(pasta_backups, motivo_limpo, manter)
    return destino


def aplicar_retencao(pasta_backups: Path, motivo: str, manter: int) -> list[Path]:
    """Mantém só os ``manter`` backups mais recentes daquele motivo; devolve os removidos."""
    arquivos = sorted(pasta_backups.glob(f"{PREFIXO}-*-{motivo}*.db"))
    removidos = arquivos[: max(len(arquivos) - manter, 0)]
    for arquivo in removidos:
        arquivo.unlink(missing_ok=True)
    return removidos


def restaurar_backup(backup: Path, banco: Path) -> None:
    """Sobrescreve ``banco`` com o conteúdo de ``backup`` (via API de backup).

    Só deve ser chamado sem outras conexões abertas no banco de destino.
    """
    validar_integridade(backup)
    try:
        _copiar(backup, banco)
    except sqlite3.Error as erro:
        raise BackupError(f"Não foi possível restaurar o backup {backup.name}: {erro}") from erro
    logger.warning("Banco restaurado a partir de %s", backup)
