"""Conexão com o SQLite: engine, pragmas e sessões.

Pragmas aplicados em toda conexão:
- ``journal_mode=WAL``: leituras não bloqueiam escritas (UI fluida durante atualizações);
- ``foreign_keys=ON``: o SQLite só respeita chaves estrangeiras com esse pragma;
- ``busy_timeout=5000``: espera até 5 s por um lock em vez de falhar na hora;
- ``synchronous=NORMAL``: seguro com WAL e bem mais rápido que FULL.

Também registra a função SQL ``casefold(texto)``: o ``lower()`` do SQLite só entende
ASCII, e nomes como "Ágora" precisam ser comparados sem diferenciar maiúsculas.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from sqlite3 import Connection as ConexaoSqlite

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
    "PRAGMA synchronous=NORMAL",
)


def url_sqlite(caminho: Path) -> URL:
    # URL.create evita problemas com espaços e acentos no caminho do Windows.
    return URL.create("sqlite", database=str(caminho))


def _casefold(texto: str | None) -> str | None:
    return None if texto is None else texto.casefold()


def _configurar_conexao(conexao: ConexaoSqlite, _registro: object) -> None:
    conexao.create_function("casefold", 1, _casefold, deterministic=True)
    cursor = conexao.cursor()
    try:
        for pragma in PRAGMAS:
            cursor.execute(pragma)
    finally:
        cursor.close()


def criar_engine(caminho: Path) -> Engine:
    engine = create_engine(url_sqlite(caminho))
    event.listen(engine, "connect", _configurar_conexao)
    return engine


def criar_fabrica_sessoes(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def sessao_transacional(fabrica: sessionmaker[Session]) -> Iterator[Session]:
    """Unidade de trabalho: confirma no fim ou desfaz tudo se houver exceção."""
    sessao = fabrica()
    try:
        yield sessao
        sessao.commit()
    except BaseException:
        sessao.rollback()
        raise
    finally:
        sessao.close()
