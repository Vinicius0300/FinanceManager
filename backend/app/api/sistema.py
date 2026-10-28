"""Rotas de sistema protegidas por token: exemplo (ping) e encerramento gracioso."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel

from app import __version__
from app.core.errors import ErroApi
from app.core.security import exigir_token

router = APIRouter(prefix="/api", tags=["sistema"], dependencies=[Depends(exigir_token)])

RESPOSTA_401: dict[int | str, dict[str, Any]] = {
    401: {"model": ErroApi, "description": "Token de sessão ausente ou inválido."}
}
ATRASO_ENCERRAMENTO_S = 0.1


class RespostaPing(BaseModel):
    mensagem: str
    horario: datetime
    versao: str


@router.get(
    "/ping",
    response_model=RespostaPing,
    summary="Rota protegida de exemplo",
    description="Confirma que o token de sessão é aceito. Devolve o horário do servidor (UTC).",
    responses=RESPOSTA_401,
)
def ping() -> RespostaPing:
    return RespostaPing(mensagem="pong", horario=datetime.now(UTC), versao=__version__)


@router.post(
    "/sistema/encerrar",
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,  # uso interno do Tauri ao fechar o app
)
async def encerrar(request: Request) -> None:
    # Responde primeiro e encerra logo depois, para o Tauri receber o 202.
    solicitar = request.app.state.solicitar_encerramento
    asyncio.get_running_loop().call_later(ATRASO_ENCERRAMENTO_S, solicitar)
