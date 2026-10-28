"""Gera o contrato OpenAPI e os tipos TypeScript do cliente.

Uso (na raiz do projeto, com o venv do backend):
    backend\\.venv\\Scripts\\python.exe scripts\\contrato.py             # gera/atualiza
    backend\\.venv\\Scripts\\python.exe scripts\\contrato.py --verificar # só confere

Saídas:
- docs/openapi.json            (exportado direto de app.openapi(), sem subir servidor)
- apps/web/src/api/schema.ts   (gerado pelo openapi-typescript; NUNCA editar à mão)

O modo --verificar gera tudo numa pasta temporária e sai com código 1 se houver
diferença em relação ao que está no repositório (usado pelo build e pelo CI).
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SAIDA_OPENAPI = RAIZ / "docs" / "openapi.json"
SAIDA_SCHEMA_TS = RAIZ / "apps" / "web" / "src" / "api" / "schema.ts"

sys.path.insert(0, str(RAIZ / "backend"))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def exportar_openapi(destino: Path) -> None:
    # Token fictício: só a estrutura do app é usada; nenhuma rota é chamada.
    app = create_app(Settings(token="contrato" * 8))
    especificacao = app.openapi()
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(especificacao, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    destino.write_text(texto, encoding="utf-8", newline="\n")


def gerar_tipos_ts(openapi: Path, destino: Path) -> None:
    npx = shutil.which("npx")
    if npx is None:
        sys.exit("Erro: 'npx' não encontrado. Instale o Node.js LTS e rode 'npm install' na raiz.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - comando fixo, sem entrada do usuário
        [npx, "--no-install", "openapi-typescript", str(openapi), "--output", str(destino)],
        cwd=RAIZ,
        check=True,
        capture_output=True,
    )
    # Normaliza fim de linha para o diff ser estável no Windows.
    texto = destino.read_text(encoding="utf-8").replace("\r\n", "\n")
    destino.write_text(texto, encoding="utf-8", newline="\n")


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8").replace("\r\n", "\n") if caminho.exists() else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="não altera arquivos; falha se o contrato commitado estiver desatualizado",
    )
    args = parser.parse_args()

    if not args.verificar:
        exportar_openapi(SAIDA_OPENAPI)
        gerar_tipos_ts(SAIDA_OPENAPI, SAIDA_SCHEMA_TS)
        print(f"Contrato gerado: {SAIDA_OPENAPI.relative_to(RAIZ)}")
        print(f"Tipos TS gerados: {SAIDA_SCHEMA_TS.relative_to(RAIZ)}")
        return 0

    with tempfile.TemporaryDirectory() as pasta:
        tmp_openapi = Path(pasta) / "openapi.json"
        tmp_schema = Path(pasta) / "schema.ts"
        exportar_openapi(tmp_openapi)
        gerar_tipos_ts(tmp_openapi, tmp_schema)
        desatualizados = [
            str(final.relative_to(RAIZ))
            for gerado, final in ((tmp_openapi, SAIDA_OPENAPI), (tmp_schema, SAIDA_SCHEMA_TS))
            if _ler(gerado) != _ler(final)
        ]
    if desatualizados:
        print("Contrato desatualizado: " + ", ".join(desatualizados), file=sys.stderr)
        print("Rode 'npm run contrato' e commite os arquivos gerados.", file=sys.stderr)
        return 1
    print("Contrato OpenAPI e tipos TS estão atualizados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
