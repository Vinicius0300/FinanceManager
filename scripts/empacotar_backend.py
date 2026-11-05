"""Empacota o backend com o PyInstaller e entrega o resultado ao Tauri.

Uso (na raiz do projeto, com o venv do backend):
    backend\\.venv\\Scripts\\python.exe scripts\\empacotar_backend.py

1. Roda ``pyinstaller backend\\financas-backend.spec`` no modo ``onedir`` (decisão da Parte 5B;
   medições em docs/CONTEXTO.md §8.6), do zero (``--clean``).
2. Substitui ``apps/desktop/src-tauri/binaries/financas-backend/`` pela pasta gerada; o
   ``tauri.instalador.conf.json`` a inclui no instalador como recurso (``financas-backend\\``
   ao lado do app). A pasta ``binaries/`` não é versionada.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BACKEND = RAIZ / "backend"
NOME = "financas-backend"
DESTINO = RAIZ / "apps" / "desktop" / "src-tauri" / "binaries" / NOME
EXECUTAVEL = DESTINO / f"{NOME}.exe"


def main() -> int:
    pyinstaller = Path(sys.executable).with_name("pyinstaller.exe")
    if not pyinstaller.exists():
        print(
            "[ERRO] PyInstaller não encontrado no venv. Rode scripts\\2_preparar_projeto.bat "
            '(instala o extra "build").',
            file=sys.stderr,
        )
        return 1
    ambiente = {**os.environ, "FINANCAS_EMPACOTAMENTO": "onedir"}
    print("Gerando o executável do backend (PyInstaller, onedir)...")
    resultado = subprocess.run(  # noqa: S603 - comando fixo do próprio projeto
        [
            str(pyinstaller),
            f"{NOME}.spec",
            "--noconfirm",
            "--clean",
            "--log-level",
            "WARN",
            "--distpath",
            "dist",
            "--workpath",
            "build",
        ],
        cwd=BACKEND,
        env=ambiente,
        check=False,
    )
    if resultado.returncode != 0:
        print("[ERRO] O PyInstaller falhou (veja as mensagens acima).", file=sys.stderr)
        return 1
    gerado = BACKEND / "dist" / NOME
    if not (gerado / f"{NOME}.exe").is_file():
        print(f"[ERRO] Executável não gerado em {gerado}.", file=sys.stderr)
        return 1
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    shutil.copytree(gerado, DESTINO)
    tamanho = sum(p.stat().st_size for p in DESTINO.rglob("*") if p.is_file())
    print(f"Backend pronto em {DESTINO.relative_to(RAIZ)} ({tamanho / 1024 / 1024:.0f} MB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
