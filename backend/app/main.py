"""Fábrica da aplicação FastAPI."""

import logging
import signal
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import __version__
from app.api import health, sistema
from app.core import paths
from app.core.config import Settings
from app.core.errors import registrar_tratadores
from app.core.logs import configurar_logging
from app.core.watchdog import iniciar_watchdog

logger = logging.getLogger(__name__)


def _encerrar_por_sinal() -> None:
    """Pede ao uvicorn um encerramento gracioso (mesmo efeito de Ctrl+C).

    Usado quando não temos acesso direto ao ``uvicorn.Server`` (modo reload).
    """
    signal.raise_signal(signal.SIGINT)


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    paths.garantir_diretorios()
    configurar_logging(arquivo=True, console=settings.dev)
    if settings.pid_pai:
        iniciar_watchdog(settings.pid_pai)
    logger.info("Backend %s pronto (dados em %s).", __version__, paths.diretorio_dados())
    yield
    logger.info("Backend encerrado.")


def _id_operacao(rota: APIRoute) -> str:
    # operation_id estável = nome da função (gera nomes legíveis no cliente TS).
    return rota.name


def create_app(
    settings: Settings | None = None,
    solicitar_encerramento: Callable[[], None] = _encerrar_por_sinal,
) -> FastAPI:
    settings = settings or Settings.do_ambiente()
    app = FastAPI(
        title="Finanças API",
        version=__version__,
        description="API local do app Finanças. Acessível apenas em 127.0.0.1.",
        lifespan=_ciclo_de_vida,
        generate_unique_id_function=_id_operacao,
        docs_url="/docs" if settings.dev else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.solicitar_encerramento = solicitar_encerramento

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origens_cors,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    registrar_tratadores(app)
    app.include_router(health.router)
    app.include_router(sistema.router)
    return app
