"""Autenticação por token de sessão (``Authorization: Bearer <token>``).

O token é gerado pelo Tauri a cada abertura do app. Todas as rotas exigem o token,
exceto ``/health``.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.errors import AplicacaoError

_esquema_bearer = HTTPBearer(auto_error=False, description="Token de sessão gerado pelo app.")


def obter_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def exigir_token(
    request: Request,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)],
) -> None:
    esperado = obter_settings(request).token
    recebido = credenciais.credentials if credenciais else ""
    # compare_digest evita vazar o token por diferença de tempo de comparação.
    if not recebido or not secrets.compare_digest(recebido.encode(), esperado.encode()):
        raise AplicacaoError(401, "nao_autorizado", "Token de sessão ausente ou inválido.")
