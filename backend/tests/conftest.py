from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.banco import criar_engine
from app.core.config import Settings
from app.main import create_app
from app.repositories.modelos import Base

TOKEN_TESTE = "t" * 64


@pytest.fixture(autouse=True)
def diretorio_dados_isolado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Nenhum teste escreve no %APPDATA% real."""
    pasta = tmp_path / "Financas"
    monkeypatch.setenv("FINANCAS_DATA_DIR", str(pasta))
    return pasta


@pytest.fixture
def encerramentos() -> list[str]:
    return []


@pytest.fixture
def app(encerramentos: list[str]) -> FastAPI:
    settings = Settings(token=TOKEN_TESTE, porta=0, dev=True)
    return create_app(settings, solicitar_encerramento=lambda: encerramentos.append("ok"))


@pytest.fixture
def cliente(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cabecalho_auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN_TESTE}"}


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """Banco SQLite temporário com o schema dos models (rápido; as migrações têm testes próprios).

    Usa ``criar_engine``, então WAL e chaves estrangeiras valem como no app.
    """
    motor = criar_engine(tmp_path / "teste.db")
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def sessao(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as s:
        yield s
