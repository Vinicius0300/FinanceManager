"""Dependências comuns das rotas: sessão (unidade de trabalho), data de hoje, agendador.

A sessão usa ``scope="function"``: o commit (ou rollback) acontece **antes** de a resposta
sair, então o cliente nunca recebe 200 de algo que não foi gravado.
"""

from collections.abc import Callable, Iterator
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.banco import sessao_transacional
from app.core.errors import ErroApi
from app.core.security import exigir_token
from app.domain.tempo import data_local
from app.jobs.agendador import Agendador
from app.jobs.eventos import CanalEventos
from app.providers.registry import RegistroProviders

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 500


def obter_sessao(request: Request) -> Iterator[Session]:
    fabrica: sessionmaker[Session] = request.app.state.fabrica_sessoes
    with sessao_transacional(fabrica) as sessao:
        yield sessao


def obter_agora(request: Request) -> datetime:
    relogio: Callable[[], datetime] = request.app.state.relogio
    return relogio()


def obter_hoje(agora: Annotated[datetime, Depends(obter_agora)]) -> date:
    return data_local(agora)


def obter_agendador(request: Request) -> Agendador:
    agendador: Agendador = request.app.state.agendador
    return agendador


def obter_canal(request: Request) -> CanalEventos:
    canal: CanalEventos = request.app.state.canal_eventos
    return canal


def obter_providers(request: Request) -> RegistroProviders:
    providers: RegistroProviders = request.app.state.registro_providers
    return providers


def obter_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


SessaoDep = Annotated[Session, Depends(obter_sessao, scope="function")]
HojeDep = Annotated[date, Depends(obter_hoje)]
AgoraDep = Annotated[datetime, Depends(obter_agora)]
AgendadorDep = Annotated[Agendador, Depends(obter_agendador)]
CanalDep = Annotated[CanalEventos, Depends(obter_canal)]
EngineDep = Annotated[Engine, Depends(obter_engine)]
ProvidersDep = Annotated[RegistroProviders, Depends(obter_providers)]
Limite = Annotated[int, Query(ge=1, le=LIMITE_MAXIMO, description="Itens por página (máximo 500).")]
Deslocamento = Annotated[int, Query(ge=0, description="Quantos itens pular (paginação).")]

PROTEGIDO = [Depends(exigir_token)]


def respostas(*codigos: int) -> dict[int | str, dict[str, Any]]:
    """Documenta no OpenAPI as respostas de erro padronizadas da rota."""
    descricoes = {
        401: "Token de sessão ausente ou inválido.",
        404: "Registro não encontrado.",
        409: "Conflito com os dados atuais.",
        422: "Dados inválidos ou regra de negócio violada.",
    }
    return {c: {"model": ErroApi, "description": descricoes[c]} for c in (401, *codigos)}
