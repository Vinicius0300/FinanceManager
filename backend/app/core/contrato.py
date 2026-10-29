"""Texto canônico do contrato OpenAPI (``docs/openapi.json``).

Usado pelo ``scripts/contrato.py`` (que grava o arquivo e gera os tipos TS) e pelo teste
``tests/test_contrato.py`` (que falha se o arquivo commitado estiver desatualizado). Os
dois precisam produzir exatamente o mesmo texto, por isso a serialização mora aqui.
"""

import json

from app.core.config import Settings
from app.main import create_app

TOKEN_FICTICIO = "contrato" * 8  # só a estrutura do app é usada; nenhuma rota é chamada


def texto_openapi() -> str:
    especificacao = create_app(Settings(token=TOKEN_FICTICIO)).openapi()
    return json.dumps(especificacao, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
