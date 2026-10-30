"""Fábrica da aplicação FastAPI."""

import asyncio
import logging
import signal
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import __version__
from app.api import ROTEADORES, health, sistema
from app.core import paths
from app.core.banco import criar_engine, criar_fabrica_sessoes
from app.core.config import Settings
from app.core.errors import registrar_tratadores
from app.core.logs import configurar_logging
from app.core.migracoes import migrar_banco
from app.core.watchdog import iniciar_watchdog
from app.domain.tempo import agora_utc
from app.jobs.agendador import Agendador
from app.jobs.eventos import CanalEventos
from app.providers.catalogo import criar_registro_providers
from app.providers.registry import RegistroProviders
from app.services.coleta import Coletor
from app.services.simbolos import ImportadorListas

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
    # Migra antes de abrir o banco (com backup prévio). Se falhar, a exceção encerra o
    # backend com a mensagem no log e o Tauri mostra o erro com "Tentar novamente".
    resultado = migrar_banco(paths.caminho_banco(), paths.diretorio_backups())
    if resultado.migrou:
        logger.info("Banco migrado para a revisão %s.", resultado.revisao_atual)
    engine = criar_engine(paths.caminho_banco())
    fabrica = criar_fabrica_sessoes(engine)
    app.state.engine = engine
    app.state.fabrica_sessoes = fabrica

    # Atualização em segundo plano: providers → coletor (thread) → canal de eventos (SSE).
    providers: RegistroProviders = app.state.providers or criar_registro_providers()
    canal = CanalEventos()
    canal.vincular(asyncio.get_running_loop())
    coletor = Coletor(fabrica, providers, relogio=app.state.relogio, publicar=canal.publicar)
    importador = ImportadorListas(
        fabrica, providers, relogio=app.state.relogio, publicar=canal.publicar
    )
    agendador = Agendador(coletor, fabrica, importador=importador)
    app.state.canal_eventos = canal
    app.state.registro_providers = providers
    app.state.agendador = agendador
    if settings.atualizacao_automatica:
        agendador.iniciar()
    logger.info("Backend %s pronto (dados em %s).", __version__, paths.diretorio_dados())
    try:
        yield
    finally:
        await agendador.parar()
        providers.fechar()
        engine.dispose()
        logger.info("Backend encerrado.")


def _id_operacao(rota: APIRoute) -> str:
    # operation_id estável = nome da função (gera nomes legíveis no cliente TS).
    return rota.name


def create_app(
    settings: Settings | None = None,
    solicitar_encerramento: Callable[[], None] = _encerrar_por_sinal,
    *,
    providers: RegistroProviders | None = None,
    relogio: Callable[[], datetime] = agora_utc,
) -> FastAPI:
    """Cria o app. ``providers`` e ``relogio`` são injetáveis (testes sem rede e sem relógio)."""
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
    app.state.providers = providers
    app.state.relogio = relogio

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origens_cors,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    registrar_tratadores(app)
    app.include_router(health.router)
    app.include_router(sistema.router)
    for roteador in ROTEADORES:
        app.include_router(roteador)
    return app
