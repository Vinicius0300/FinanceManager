"""Configuração do backend, lida das variáveis de ambiente definidas pelo Tauri.

O Tauri escolhe a porta e gera o token de sessão a cada abertura e os repassa por
variáveis de ambiente (não por argumentos, para o token não aparecer na lista de
processos).
"""

import os
from dataclasses import dataclass

HOST = "127.0.0.1"

ORIGENS_PRODUCAO = ("http://tauri.localhost",)
ORIGENS_DEV = ("http://localhost:5173", "http://127.0.0.1:5173")


class ConfiguracaoInvalidaError(Exception):
    """Configuração obrigatória ausente ou inválida."""


@dataclass(frozen=True)
class Settings:
    token: str
    porta: int = 0
    pid_pai: int | None = None
    dev: bool = False
    atualizacao_automatica: bool = True  # FINANCAS_SEM_ATUALIZACAO=1 desliga (testes/diagnóstico)

    @property
    def origens_cors(self) -> list[str]:
        origens = list(ORIGENS_PRODUCAO)
        if self.dev:
            origens.extend(ORIGENS_DEV)
        return origens

    @classmethod
    def do_ambiente(cls) -> "Settings":
        token = os.environ.get("FINANCAS_TOKEN", "")
        if len(token) < 32:
            raise ConfiguracaoInvalidaError(
                "Token de sessão ausente ou curto demais (FINANCAS_TOKEN). "
                "O backend deve ser iniciado pelo app Finanças."
            )
        return cls(
            token=token,
            porta=_inteiro("FINANCAS_PORTA", padrao=0),
            pid_pai=_inteiro("FINANCAS_PID_PAI", padrao=0) or None,
            dev=os.environ.get("FINANCAS_DEV") == "1",
            atualizacao_automatica=os.environ.get("FINANCAS_SEM_ATUALIZACAO") != "1",
        )


def _inteiro(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome)
    if not valor:
        return padrao
    try:
        return int(valor)
    except ValueError as erro:
        raise ConfiguracaoInvalidaError(f"{nome} deve ser um número inteiro.") from erro
