import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__


def test_health_nao_exige_token(cliente: TestClient) -> None:
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "versao": __version__}


def test_ping_com_token_valido(cliente: TestClient, cabecalho_auth: dict[str, str]) -> None:
    resposta = cliente.get("/api/ping", headers=cabecalho_auth)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["mensagem"] == "pong"
    assert corpo["versao"] == __version__
    horario = datetime.fromisoformat(corpo["horario"])
    assert horario.tzinfo is not None
    assert abs((datetime.now(UTC) - horario).total_seconds()) < 5


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer errado"},
        {"Authorization": "Basic abc"},
        {"Authorization": "t" * 64},  # sem o esquema Bearer
    ],
)
def test_ping_sem_token_valido_retorna_401_em_pt_br(
    cliente: TestClient, headers: dict[str, str]
) -> None:
    resposta = cliente.get("/api/ping", headers=headers)
    assert resposta.status_code == 401
    assert resposta.json() == {
        "codigo": "nao_autorizado",
        "mensagem": "Token de sessão ausente ou inválido.",
    }


def test_rota_inexistente_retorna_erro_padronizado(cliente: TestClient) -> None:
    resposta = cliente.get("/nao-existe")
    assert resposta.status_code == 404
    assert resposta.json() == {"codigo": "http_404", "mensagem": "Recurso não encontrado."}


def test_encerrar_exige_token(cliente: TestClient, encerramentos: list[str]) -> None:
    resposta = cliente.post("/api/sistema/encerrar")
    assert resposta.status_code == 401
    assert encerramentos == []


def test_encerrar_agenda_encerramento_gracioso(
    cliente: TestClient, cabecalho_auth: dict[str, str], encerramentos: list[str]
) -> None:
    resposta = cliente.post("/api/sistema/encerrar", headers=cabecalho_auth)
    assert resposta.status_code == 202
    # O encerramento é agendado ~0,1 s depois de responder.
    limite = time.monotonic() + 2
    while not encerramentos and time.monotonic() < limite:
        cliente.get("/health")
        time.sleep(0.05)
    assert encerramentos == ["ok"]


def test_encerrar_fica_fora_do_contrato(cliente: TestClient) -> None:
    caminhos = cliente.get("/openapi.json").json()["paths"]
    assert "/api/sistema/encerrar" not in caminhos
    assert set(caminhos) == {"/health", "/api/ping"}


def test_cors_permite_apenas_origens_do_app(cliente: TestClient) -> None:
    def preflight(origem: str) -> str | None:
        r = cliente.options(
            "/api/ping",
            headers={
                "Origin": origem,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        return r.headers.get("access-control-allow-origin")

    assert preflight("http://tauri.localhost") == "http://tauri.localhost"
    assert preflight("http://localhost:5173") == "http://localhost:5173"
    assert preflight("https://site-malicioso.com") is None


def test_inicializacao_cria_pastas_e_log(
    cliente: TestClient, diretorio_dados_isolado: Path
) -> None:
    for nome in ("logs", "backups", "models"):
        assert (diretorio_dados_isolado / nome).is_dir()
    assert (diretorio_dados_isolado / "logs" / "backend.log").exists()
