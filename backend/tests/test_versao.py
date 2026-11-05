"""Versão com fonte única (``package.json`` da raiz) e o ``scripts/versao.py``.

Os testes rodam o script de verdade (subprocesso) sobre uma cópia dos arquivos reais numa
pasta temporária, para nunca alterar o repositório.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "versao.py"
ARQUIVOS = (
    "package.json",
    "package-lock.json",
    "apps/web/package.json",
    "apps/desktop/package.json",
    "apps/desktop/src-tauri/tauri.conf.json",
    "apps/desktop/src-tauri/Cargo.toml",
    "apps/desktop/src-tauri/Cargo.lock",
    "backend/pyproject.toml",
    "backend/app/__init__.py",
    "docs/openapi.json",
)


def versao_do_package_json() -> str:
    versao = json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))["version"]
    assert isinstance(versao, str)
    return versao


def rodar(raiz: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - comando fixo do próprio projeto
        [sys.executable, str(SCRIPT), "--raiz", str(raiz), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )


@pytest.fixture
def copia(tmp_path: Path) -> Path:
    for arquivo in ARQUIVOS:
        destino = tmp_path / arquivo
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RAIZ / arquivo, destino)
    return tmp_path


def trocar(raiz: Path, arquivo: str, antes: str, depois: str) -> None:
    caminho = raiz / arquivo
    texto = caminho.read_text(encoding="utf-8")
    assert antes in texto, f"{antes!r} não está em {arquivo}"
    caminho.write_text(texto.replace(antes, depois, 1), encoding="utf-8", newline="\n")


def conteudos(raiz: Path) -> dict[str, bytes]:
    return {arquivo: (raiz / arquivo).read_bytes() for arquivo in ARQUIVOS}


def test_repositorio_esta_sincronizado() -> None:
    resultado = rodar(RAIZ, "--verificar")
    assert resultado.returncode == 0, resultado.stderr


def test_versao_do_backend_e_a_do_package_json() -> None:
    assert __version__ == versao_do_package_json()


def test_health_e_ping_devolvem_a_versao_do_package_json(
    cliente: TestClient, cabecalho_auth: dict[str, str]
) -> None:
    versao = versao_do_package_json()
    assert cliente.get("/health").json()["versao"] == versao
    assert cliente.get("/api/ping", headers=cabecalho_auth).json()["versao"] == versao


def test_divergencia_faz_a_verificacao_falhar(copia: Path) -> None:
    versao = versao_do_package_json()
    trocar(copia, "apps/desktop/src-tauri/Cargo.toml", f'version = "{versao}"', 'version = "9.9.9"')
    resultado = rodar(copia, "--verificar")
    assert resultado.returncode == 1
    assert "apps/desktop/src-tauri/Cargo.toml: [package].version = 9.9.9" in resultado.stderr
    assert f"(esperado {versao})" in resultado.stderr


def test_tauri_e_pyproject_nao_podem_ter_numero_proprio(copia: Path) -> None:
    trocar(
        copia,
        "apps/desktop/src-tauri/tauri.conf.json",
        '"version": "../../../package.json"',
        '"version": "1.0.0"',
    )
    trocar(copia, "backend/pyproject.toml", 'dynamic = ["version"]', 'version = "1.0.0"')
    resultado = rodar(copia, "--verificar")
    assert resultado.returncode == 1
    assert "tauri.conf.json" in resultado.stderr
    assert "não pode ter version fixa" in resultado.stderr


def test_sincronizar_propaga_a_versao_nova_e_e_idempotente(copia: Path) -> None:
    versao = versao_do_package_json()
    trocar(copia, "package.json", f'"version": "{versao}"', '"version": "1.0.1"')
    assert rodar(copia, "--verificar").returncode == 1

    primeira = rodar(copia)
    assert primeira.returncode == 0, primeira.stderr
    assert "Versão 1.0.1 consistente" in primeira.stdout
    lock = json.loads((copia / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == "1.0.1"
    assert {lock["packages"][k]["version"] for k in ("", "apps/web", "apps/desktop")} == {"1.0.1"}
    assert '__version__ = "1.0.1"' in (copia / "backend/app/__init__.py").read_text("utf-8")
    openapi = json.loads((copia / "docs/openapi.json").read_text(encoding="utf-8"))
    assert openapi["info"]["version"] == "1.0.1"
    cargo_lock = (copia / "apps/desktop/src-tauri/Cargo.lock").read_text(encoding="utf-8")
    assert '[[package]]\nname = "financas"\nversion = "1.0.1"' in cargo_lock
    # Dependências com o mesmo número antigo não são tocadas (só o pacote do projeto).
    lock_original = (RAIZ / "package-lock.json").read_text(encoding="utf-8")
    assert lock_original.count(f'"version": "{versao}"') - 4 == (
        (copia / "package-lock.json").read_text(encoding="utf-8").count(f'"version": "{versao}"')
    )

    depois_da_primeira = conteudos(copia)
    segunda = rodar(copia)
    assert segunda.returncode == 0
    assert "Nada a mudar." in segunda.stdout
    assert conteudos(copia) == depois_da_primeira


def test_package_json_com_bom_e_crlf_e_aceito(copia: Path) -> None:
    # Editado no Bloco de Notas / PowerShell 5.1: BOM e fim de linha CRLF.
    pacote = copia / "package.json"
    texto = pacote.read_text(encoding="utf-8").replace("\n", "\r\n")
    pacote.write_bytes(b"\xef\xbb\xbf" + texto.encode("utf-8"))
    resultado = rodar(copia, "--imprimir")
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == versao_do_package_json()
    assert rodar(copia, "--verificar").returncode == 0


def test_imprimir_mostra_so_a_versao(copia: Path) -> None:
    resultado = rodar(copia, "--imprimir")
    assert resultado.returncode == 0
    assert resultado.stdout == f"{versao_do_package_json()}\n"


def test_versao_invalida_no_package_json(copia: Path) -> None:
    versao = versao_do_package_json()
    trocar(copia, "package.json", f'"version": "{versao}"', '"version": "1.0"')
    resultado = rodar(copia)
    assert resultado.returncode == 1
    assert "deve ser X.Y.Z" in resultado.stderr
