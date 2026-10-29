"""Migrações Alembic na inicialização, com backup prévio e restauração em caso de falha.

Fluxo de :func:`migrar_banco`:
1. descobre a revisão atual do banco e a ``head`` dos scripts;
2. se já está na ``head``, não faz nada (sem backup a cada abertura);
3. se o banco é de uma versão **mais nova** do app (revisão desconhecida), recusa;
4. se há banco com dados, cria um backup validado (``pre-migracao``) antes de migrar;
5. roda ``upgrade head``. Se falhar, restaura o backup (ou apaga o banco recém-criado)
   e levanta :class:`MigracaoError` com mensagem em pt-BR: o banco nunca fica pela metade.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.core.backup import BackupError, criar_backup, restaurar_backup
from app.core.banco import url_sqlite

logger = logging.getLogger(__name__)

PASTA_MIGRACOES = Path(__file__).resolve().parents[2] / "migrations"
MOTIVO_BACKUP = "pre-migracao"


class MigracaoError(Exception):
    """Falha ao preparar o banco; a mensagem já está em pt-BR para o usuário."""


@dataclass(frozen=True)
class ResultadoMigracao:
    revisao_anterior: str | None
    revisao_atual: str
    backup: Path | None

    @property
    def migrou(self) -> bool:
        return self.revisao_anterior != self.revisao_atual


def configuracao_alembic(caminho_banco: Path) -> Config:
    """Configuração programática (não depende de ``alembic.ini`` nem do diretório atual)."""
    config = Config()
    config.set_main_option("script_location", str(PASTA_MIGRACOES))
    config.attributes["caminho_banco"] = caminho_banco
    return config


def revisao_head(config: Config) -> str:
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise MigracaoError("Nenhuma migração encontrada no aplicativo.")
    return head


def revisao_do_banco(caminho_banco: Path) -> str | None:
    if not caminho_banco.exists() or caminho_banco.stat().st_size == 0:
        return None
    engine = create_engine(url_sqlite(caminho_banco), poolclass=NullPool)
    try:
        with engine.connect() as conexao:
            return MigrationContext.configure(conexao).get_current_revision()
    finally:
        engine.dispose()


def migrar_banco(caminho_banco: Path, pasta_backups: Path) -> ResultadoMigracao:
    config = configuracao_alembic(caminho_banco)
    head = revisao_head(config)
    atual = revisao_do_banco(caminho_banco)
    if atual == head:
        return ResultadoMigracao(atual, head, None)

    conhecidas = {r.revision for r in ScriptDirectory.from_config(config).walk_revisions()}
    if atual is not None and atual not in conhecidas:
        raise MigracaoError(
            "O banco de dados foi criado por uma versão mais nova do Finanças. "
            "Atualize o aplicativo para abrir esses dados."
        )

    banco_existia = caminho_banco.exists() and caminho_banco.stat().st_size > 0
    backup: Path | None = None
    if banco_existia:
        try:
            backup = criar_backup(caminho_banco, pasta_backups, MOTIVO_BACKUP)
        except BackupError as erro:
            raise MigracaoError(
                "Não foi possível criar o backup de segurança antes de atualizar o banco. "
                "Nenhuma alteração foi feita."
            ) from erro

    logger.info("Migrando banco de %s para %s.", atual or "vazio", head)
    try:
        command.upgrade(config, "head")
    except Exception as erro:
        logger.exception("Falha na migração do banco.")
        _desfazer(caminho_banco, backup)
        raise MigracaoError(
            "Não foi possível atualizar o banco de dados. Os dados anteriores foram "
            "preservados e os detalhes foram registrados no log."
        ) from erro
    return ResultadoMigracao(atual, head, backup)


def _desfazer(caminho_banco: Path, backup: Path | None) -> None:
    if backup is not None:
        restaurar_backup(backup, caminho_banco)
        return
    # Banco novo: remove o arquivo incompleto (e os auxiliares do WAL).
    for sufixo in ("", "-wal", "-shm"):
        Path(f"{caminho_banco}{sufixo}").unlink(missing_ok=True)
