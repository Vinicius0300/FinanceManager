"""Backup e restauração do banco (a tela fica para a Parte 4).

- **Backup manual:** API de backup do SQLite (nunca copia o arquivo aberto), cópia validada
  com ``integrity_check`` e retenção dos 10 mais recentes (``core/backup.py``).
- **Restauração** (de um backup da pasta ou de um arquivo escolhido pelo usuário):
  1. valida o arquivo: SQLite íntegro, com as tabelas do Finanças e uma revisão de schema
     conhecida (um banco de versão mais nova do app é recusado);
  2. cria um **backup de segurança** do banco atual (``pre-restauracao``);
  3. fecha as conexões, restaura pela API de backup e roda as migrações (um backup antigo
     é atualizado para o schema atual);
  4. se algo falhar depois de mexer no banco, volta o backup de segurança.
  Quem chama garante que nenhuma coleta está gravando (``Agendador.exclusivo``).
"""

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from app.core.backup import (
    PREFIXO,
    BackupError,
    criar_backup,
    restaurar_backup,
    validar_integridade,
)
from app.core.migracoes import (
    MigracaoError,
    configuracao_alembic,
    migrar_banco,
    revisao_do_banco,
)
from app.domain.erros import NaoEncontradoError, OperacaoNaoPermitidaError, ValidacaoError

logger = logging.getLogger(__name__)

MOTIVO_MANUAL = "manual"
MOTIVO_SEGURANCA = "pre-restauracao"
TABELAS_OBRIGATORIAS = frozenset({"alembic_version", "ativos", "transacoes", "instituicoes"})


@dataclass(frozen=True)
class InfoBackup:
    nome: str
    caminho: Path
    tamanho_bytes: int
    criado_em: datetime  # modificação do arquivo, em UTC


def _info(arquivo: Path) -> InfoBackup:
    estatisticas = arquivo.stat()
    return InfoBackup(
        nome=arquivo.name,
        caminho=arquivo,
        tamanho_bytes=estatisticas.st_size,
        criado_em=datetime.fromtimestamp(estatisticas.st_mtime, tz=UTC),
    )


def listar_backups(pasta: Path) -> list[InfoBackup]:
    """Backups da pasta do app, do mais recente para o mais antigo."""
    if not pasta.exists():
        return []
    arquivos = [a for a in pasta.glob(f"{PREFIXO}-*.db") if a.is_file()]
    return sorted((_info(a) for a in arquivos), key=lambda i: (i.criado_em, i.nome), reverse=True)


def criar_backup_manual(banco: Path, pasta: Path) -> InfoBackup:
    try:
        return _info(criar_backup(banco, pasta, MOTIVO_MANUAL))
    except BackupError as erro:
        raise OperacaoNaoPermitidaError(str(erro)) from erro


def localizar_backup(pasta: Path, nome: str | None, caminho: str | None) -> Path:
    """Arquivo a restaurar: ``nome`` de um backup da pasta do app ou ``caminho`` absoluto."""
    if (nome is None) == (caminho is None):
        raise ValidacaoError("Informe o nome de um backup da lista ou o caminho de um arquivo.")
    if nome is not None:
        candidatos = {i.nome: i.caminho for i in listar_backups(pasta)}
        if nome not in candidatos:  # impede caminhos como "../outro.db"
            raise NaoEncontradoError(f"Backup {nome!r} não encontrado.")
        return candidatos[nome]
    arquivo = Path(str(caminho))
    if not arquivo.is_absolute() or not arquivo.is_file():
        raise NaoEncontradoError("Arquivo de backup não encontrado.")
    return arquivo


def _tabelas(arquivo: Path) -> set[str]:
    uri = f"file:{arquivo.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conexao:
        linhas = conexao.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {nome for (nome,) in linhas}


def validar_arquivo_backup(arquivo: Path, banco: Path) -> str:
    """Confere se o arquivo é um banco do Finanças restaurável; devolve a revisão dele."""
    try:
        validar_integridade(arquivo)
        tabelas = _tabelas(arquivo)
    except (BackupError, sqlite3.Error) as erro:
        raise ValidacaoError("O arquivo escolhido não é um banco de dados válido.") from erro
    if not tabelas >= TABELAS_OBRIGATORIAS:
        raise ValidacaoError("O arquivo não é um backup do Finanças.")
    revisao = revisao_do_banco(arquivo)
    conhecidas = {
        r.revision
        for r in ScriptDirectory.from_config(configuracao_alembic(banco)).walk_revisions()
    }
    if revisao not in conhecidas:
        raise ValidacaoError(
            "O backup foi criado por uma versão mais nova do Finanças. "
            "Atualize o aplicativo para restaurá-lo."
        )
    return str(revisao)


@dataclass(frozen=True)
class ResultadoRestauracao:
    restaurado: str
    backup_seguranca: InfoBackup


def restaurar(arquivo: Path, banco: Path, pasta: Path, engine: Engine) -> ResultadoRestauracao:
    """Restaura ``arquivo`` sobre ``banco`` (ver passos no topo do módulo)."""
    validar_arquivo_backup(arquivo, banco)
    try:
        seguranca = criar_backup(banco, pasta, MOTIVO_SEGURANCA)
    except BackupError as erro:
        raise OperacaoNaoPermitidaError(
            "Não foi possível criar o backup de segurança. Nada foi restaurado."
        ) from erro
    engine.dispose()  # nenhuma conexão do pool fica aberta durante a cópia
    try:
        restaurar_backup(arquivo, banco)
        migrar_banco(banco, pasta)
    except (BackupError, MigracaoError, sqlite3.Error) as erro:
        logger.exception("Falha ao restaurar %s; voltando o backup de segurança.", arquivo)
        engine.dispose()
        restaurar_backup(seguranca, banco)
        raise OperacaoNaoPermitidaError(
            "Não foi possível restaurar o backup. Os dados anteriores foram mantidos."
        ) from erro
    engine.dispose()
    logger.warning("Banco restaurado de %s (segurança: %s).", arquivo, seguranca.name)
    return ResultadoRestauracao(restaurado=arquivo.name, backup_seguranca=_info(seguranca))
