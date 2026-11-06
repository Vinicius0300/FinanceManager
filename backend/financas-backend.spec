# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller: backend do Finanças como executável de console.

Uso (na pasta backend, pelo scripts\\empacotar_backend.py, que também copia o resultado
para o Tauri):
    .venv\\Scripts\\pyinstaller financas-backend.spec --noconfirm --clean

Modo: variável FINANCAS_EMPACOTAMENTO = "onedir" (padrão, decisão da Parte 5B) ou "onefile"
(mantido só para medir/comparar; ver docs/HISTORICO.md, Parte 5B).

- Console (sem --noconsole): o Rust já cria o processo com CREATE_NO_WINDOW, e com
  --noconsole o sys.stdout/sys.stderr viram None.
- migrations/ entra como DADOS (.py originais): o Alembic lê env.py e versions/ do disco.
  Destino "migrations" na raiz do bundle = sys._MEIPASS/migrations, que é para onde
  core/migracoes.PASTA_MIGRACOES aponta (Path(__file__).parents[2] / "migrations").
- hiddenimports: o que só é importado por texto (uvicorn escolhe loops/protocols/lifespan
  por nome; o Alembic carrega env.py e as versões em tempo de execução).
- HTTPS: httpcore2 usa o truststore (repositório de certificados do Windows), não o certifi.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

MODO = os.environ.get("FINANCAS_EMPACOTAMENTO", "onedir")
if MODO not in ("onedir", "onefile"):
    raise SystemExit(f"FINANCAS_EMPACOTAMENTO inválido: {MODO!r} (use onedir ou onefile).")

NOME = "financas-backend"

hiddenimports = [
    *collect_submodules("uvicorn"),
    # Alembic: módulos usados pelo env.py e pelas migrações (carregados do disco).
    "alembic.op",
    "alembic.context",
    "alembic.runtime.migration",
    "alembic.runtime.environment",
    "alembic.ddl.sqlite",
    "alembic.ddl.impl",
    "alembic.autogenerate",
    # Módulos do app importados pelo env.py (que o PyInstaller não analisa).
    "app.repositories.modelos",
    "app.core.banco",
    "app.core.paths",
    # Dialeto SQLite do SQLAlchemy (escolhido pela URL).
    *collect_submodules("sqlalchemy.dialects.sqlite"),
    # HTTPS pelo repositório de certificados do Windows.
    "truststore",
    # Bibliotecas usadas pelas migrações.
    "zoneinfo",
]

datas = [
    ("migrations", "migrations"),
    *collect_data_files("tzdata"),  # base IANA de fusos (o Windows não traz)
    *collect_data_files("openpyxl"),
    *collect_data_files("alembic"),  # templates (script.py.mako) e afins
]

# Fora do executável: dependências de desenvolvimento, testes e qualquer ML.
excludes = [
    "watchfiles",
    "pytest",
    "_pytest",
    "mypy",
    "ruff",
    "IPython",
    "tkinter",
    "matplotlib",
    "scipy",
    "sklearn",
    "torch",
    "tensorflow",
    "certifi",
    "httpcore",
    "httpx",
    "pandas.tests",
    "numpy.tests",
]

a = Analysis(
    ["entrypoint.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if MODO == "onefile":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=NOME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        icon=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=NOME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        icon=None,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NOME)
