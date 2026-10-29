"""Ambiente do Alembic.

O caminho do banco vem de ``config.attributes["caminho_banco"]`` (inicialização do app,
ver ``app/core/migracoes.py``) ou, pela linha de comando (``alembic upgrade head``),
de ``app.core.paths.caminho_banco()`` (respeita ``FINANCAS_DATA_DIR``).

SQLite: ``render_as_batch`` (alterações de coluna recriam a tabela) e chaves
estrangeiras desligadas durante a migração, com ``PRAGMA foreign_key_check`` no fim.
"""

from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core import paths
from app.core.banco import url_sqlite
from app.repositories.modelos import Base

config = context.config
target_metadata = Base.metadata


def _caminho_banco() -> Path:
    caminho = config.attributes.get("caminho_banco")
    if caminho is None:
        paths.garantir_diretorios()
        return paths.caminho_banco()
    return Path(caminho)


def run_migrations_offline() -> None:
    context.configure(
        url=str(url_sqlite(_caminho_banco())),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url_sqlite(_caminho_banco()), poolclass=NullPool)
    try:
        with engine.connect() as conexao:
            conexao.execute(text("PRAGMA journal_mode=WAL"))
            conexao.execute(text("PRAGMA foreign_keys=OFF"))
            conexao.commit()
            context.configure(
                connection=conexao,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            violacoes = conexao.execute(text("PRAGMA foreign_key_check")).fetchall()
            if violacoes:
                raise RuntimeError(f"Migração deixou chaves estrangeiras inválidas: {violacoes}")
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
