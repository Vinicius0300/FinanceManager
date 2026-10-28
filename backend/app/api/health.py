"""``/health``: única rota sem token, usada pelo Tauri para liberar a UI."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["sistema"])


class RespostaHealth(BaseModel):
    status: Literal["ok"]
    versao: str


@router.get(
    "/health",
    response_model=RespostaHealth,
    summary="Verifica se o backend está no ar",
    description="Não exige token. Responde assim que o servidor aceita requisições.",
)
def obter_health() -> RespostaHealth:
    return RespostaHealth(status="ok", versao=__version__)
