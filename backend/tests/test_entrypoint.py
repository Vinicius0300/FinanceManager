"""Teste de integração do sidecar: sobe o processo real e encerra de forma graciosa."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PASTA_BACKEND = Path(__file__).resolve().parents[1]
TOKEN = "x" * 64


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta: int = s.getsockname()[1]
        return porta


def _requisitar(url: str, metodo: str = "GET", token: str | None = None) -> int:
    req = urllib.request.Request(url, method=metodo)  # noqa: S310 - só loopback
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:  # noqa: S310
            json.loads(r.read() or b"null")
            return int(r.status)
    except urllib.error.HTTPError as erro:
        return erro.code


def test_sidecar_sobe_responde_e_encerra_gracioso(diretorio_dados_isolado: Path) -> None:
    porta = _porta_livre()
    env = {
        **os.environ,
        "FINANCAS_TOKEN": TOKEN,
        "FINANCAS_PORTA": str(porta),
        "FINANCAS_PID_PAI": str(os.getpid()),
    }
    processo = subprocess.Popen([sys.executable, "entrypoint.py"], cwd=PASTA_BACKEND, env=env)
    base = f"http://127.0.0.1:{porta}"
    try:
        limite = time.monotonic() + 20
        while True:
            try:
                if _requisitar(f"{base}/health") == 200:
                    break
            except OSError:
                pass
            if time.monotonic() > limite or processo.poll() is not None:
                pytest.fail("backend não respondeu ao /health")
            time.sleep(0.1)

        assert _requisitar(f"{base}/api/ping") == 401
        assert _requisitar(f"{base}/api/ping", token=TOKEN) == 200
        assert _requisitar(f"{base}/api/sistema/encerrar", "POST", token=TOKEN) == 202
        assert processo.wait(timeout=10) == 0
    finally:
        if processo.poll() is None:
            processo.kill()
    assert (diretorio_dados_isolado / "logs" / "backend.log").exists()


def test_sem_token_sai_com_erro_claro(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "FINANCAS_TOKEN"}
    env["PYTHONIOENCODING"] = "utf-8"
    resultado = subprocess.run(
        [sys.executable, "entrypoint.py", "--porta", "1"],
        cwd=PASTA_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert resultado.returncode == 2
    assert "Token de sessão" in resultado.stderr
