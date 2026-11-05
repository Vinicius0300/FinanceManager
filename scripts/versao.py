"""Versão do app com fonte única: o ``package.json`` da raiz.

Uso (na raiz do projeto, com o venv do backend):
    backend\\.venv\\Scripts\\python.exe scripts\\versao.py              # sincroniza
    backend\\.venv\\Scripts\\python.exe scripts\\versao.py --verificar  # só confere

Para gerar uma versão nova (ex.: 1.0.1): mude só o ``"version"`` do ``package.json`` da raiz e
rode o script (o ``3_gerar_instalador.bat`` já faz isso). Arquivos sincronizados:
- ``apps/web/package.json`` e ``apps/desktop/package.json`` (workspaces);
- ``package-lock.json`` (raiz e os três pacotes do monorepo);
- ``apps/desktop/src-tauri/Cargo.toml`` e ``Cargo.lock`` (pacote ``financas``);
- ``backend/app/__init__.py`` (``__version__``, gerado: é a versão do executável, do ``/health``,
  do ``/api/ping`` e do OpenAPI);
- ``docs/openapi.json`` (``info.version``, para o contrato não ficar desatualizado).

Conferidos sem número (não podem voltar a ter um):
- ``tauri.conf.json``: ``"version": "../../../package.json"`` (o Tauri lê do ``package.json``);
- ``backend/pyproject.toml``: ``dynamic = ["version"]`` lendo ``app.__version__``.

A edição é textual (só o número muda; formatação e ordem dos arquivos ficam intactas), sem
depender do Node. Rodar duas vezes não muda nada.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RAIZ_PADRAO = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
VERSAO_TAURI = "../../../package.json"


class VersaoError(Exception):
    """Arquivo fora do formato esperado (mensagem em pt-BR)."""


def _padrao(regex: str) -> re.Pattern[str]:
    return re.compile(regex, re.MULTILINE)


@dataclass(frozen=True)
class Local:
    """Um número de versão dentro de um arquivo: regex com os grupos (antes)(versão)(depois)."""

    descricao: str
    padrao: re.Pattern[str]


@dataclass(frozen=True)
class Alvo:
    arquivo: str
    locais: tuple[Local, ...]


def _json_topo() -> Local:
    # Chave de primeiro nível (2 espaços de recuo): o "version" do próprio pacote.
    return Local("version", _padrao(r'^(  "version": ")([^"]*)(")'))


def _pacote_do_lock(chave: str) -> Local:
    # "packages" → "<chave>": { ... "version": "x" } (6 espaços dentro do bloco do pacote).
    return Local(
        f'packages["{chave}"].version',
        _padrao(rf'^(    "{re.escape(chave)}": \{{\n(?:      .*\n)*?      "version": ")([^"]*)(")'),
    )


ALVOS = (
    Alvo("apps/web/package.json", (_json_topo(),)),
    Alvo("apps/desktop/package.json", (_json_topo(),)),
    Alvo(
        "package-lock.json",
        (
            _json_topo(),
            _pacote_do_lock(""),
            _pacote_do_lock("apps/web"),
            _pacote_do_lock("apps/desktop"),
        ),
    ),
    Alvo(
        "apps/desktop/src-tauri/Cargo.toml",
        (
            Local(
                "[package].version",
                _padrao(r'\A(\[package\]\n(?:(?!\[).*\n)*?version = ")([^"]*)(")'),
            ),
        ),
    ),
    Alvo(
        "apps/desktop/src-tauri/Cargo.lock",
        (
            Local(
                'pacote "financas"',
                _padrao(r'^(\[\[package\]\]\nname = "financas"\nversion = ")([^"]*)(")'),
            ),
        ),
    ),
    Alvo(
        "backend/app/__init__.py", (Local("__version__", _padrao(r'^(__version__ = ")([^"]*)(")')),)
    ),
    Alvo(
        "docs/openapi.json",
        (
            Local(
                "info.version",
                _padrao(r'^(  "info": \{\n(?:    .*\n)*?    "version": ")([^"]*)(")'),
            ),
        ),
    ),
)


def _ler(raiz: Path, arquivo: str) -> str:
    caminho = raiz / arquivo
    if not caminho.exists():
        raise VersaoError(f"{arquivo}: arquivo não encontrado.")
    # utf-8-sig: aceita o BOM que o Bloco de Notas e o PowerShell 5.1 costumam gravar.
    return caminho.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _encontrar(texto: str, local: Local, arquivo: str) -> re.Match[str]:
    achados = list(local.padrao.finditer(texto))
    if len(achados) != 1:
        raise VersaoError(
            f"{arquivo}: {local.descricao} não encontrado (ou repetido); "
            "confira o formato do arquivo."
        )
    return achados[0]


def versao_fonte(raiz: Path) -> str:
    """Versão do ``package.json`` da raiz (precisa ser X.Y.Z)."""
    dados = json.loads(_ler(raiz, "package.json"))
    versao = dados.get("version")
    if not isinstance(versao, str) or not SEMVER.match(versao):
        raise VersaoError(
            f'package.json: "version" deve ser X.Y.Z (ex.: 1.0.0); encontrado {versao!r}.'
        )
    return versao


def _conferir_sem_numero(raiz: Path) -> list[str]:
    """Arquivos que não podem ter número próprio (leem a versão de outro lugar)."""
    problemas: list[str] = []
    tauri = json.loads(_ler(raiz, "apps/desktop/src-tauri/tauri.conf.json"))
    if tauri.get("version") != VERSAO_TAURI:
        problemas.append(
            f'apps/desktop/src-tauri/tauri.conf.json: "version" deve ser "{VERSAO_TAURI}" '
            f"(encontrado {tauri.get('version')!r})."
        )
    pyproject = _ler(raiz, "backend/pyproject.toml")
    projeto = pyproject.split("[project]", 1)[-1].split("\n[", 1)[0]
    if re.search(r"^version\s*=", projeto, re.MULTILINE):
        problemas.append(
            "backend/pyproject.toml: [project] não pode ter version fixa (use dynamic)."
        )
    if not re.search(r'^dynamic = \["version"\]', projeto, re.MULTILINE):
        problemas.append('backend/pyproject.toml: falta dynamic = ["version"] em [project].')
    if 'version = {attr = "app.__version__"}' not in pyproject:
        problemas.append(
            "backend/pyproject.toml: falta [tool.setuptools.dynamic] "
            'version = {attr = "app.__version__"}.'
        )
    return problemas


def divergencias(raiz: Path) -> list[str]:
    """Lista (em pt-BR) tudo que não bate com o ``package.json`` da raiz."""
    versao = versao_fonte(raiz)
    problemas = _conferir_sem_numero(raiz)
    for alvo in ALVOS:
        texto = _ler(raiz, alvo.arquivo)
        for local in alvo.locais:
            atual = _encontrar(texto, local, alvo.arquivo).group(2)
            if atual != versao:
                problemas.append(
                    f"{alvo.arquivo}: {local.descricao} = {atual} (esperado {versao})."
                )
    return problemas


def sincronizar(raiz: Path, avisar: Callable[[str], None] = print) -> list[str]:
    """Grava a versão da fonte nos arquivos; devolve os arquivos alterados."""
    versao = versao_fonte(raiz)
    alterados: list[str] = []
    for alvo in ALVOS:
        original = _ler(raiz, alvo.arquivo)
        texto = original
        for local in alvo.locais:
            achado = _encontrar(texto, local, alvo.arquivo)
            texto = texto[: achado.start(2)] + versao + texto[achado.end(2) :]
        if texto != original:
            (raiz / alvo.arquivo).write_text(texto, encoding="utf-8", newline="\n")
            alterados.append(alvo.arquivo)
            avisar(f"  {alvo.arquivo} -> {versao}")
    return alterados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sincroniza a versão a partir do package.json.")
    parser.add_argument("--verificar", action="store_true", help="só confere; falha se divergir")
    parser.add_argument(
        "--imprimir", action="store_true", help="só imprime a versão (usado pelos scripts .bat)"
    )
    parser.add_argument("--raiz", type=Path, default=RAIZ_PADRAO, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        versao = versao_fonte(args.raiz)
        if args.imprimir:
            print(versao)
            return 0
        if not args.verificar:
            print(f"Sincronizando a versão {versao} (fonte: package.json da raiz)...")
            if not sincronizar(args.raiz):
                print("  Nada a mudar.")
        problemas = divergencias(args.raiz)
    except VersaoError as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1
    if problemas:
        print(f"[ERRO] Versão divergente do package.json da raiz ({versao}):", file=sys.stderr)
        for problema in problemas:
            print(f"  - {problema}", file=sys.stderr)
        print("Rode: backend\\.venv\\Scripts\\python.exe scripts\\versao.py", file=sys.stderr)
        return 1
    print(f"Versão {versao} consistente em todos os arquivos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
