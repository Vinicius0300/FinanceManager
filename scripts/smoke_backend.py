"""Smoke test do executável do backend (PyInstaller), rodado pelo 3_gerar_instalador.bat.

Uso (na raiz do projeto, com o venv do backend):
    backend\\.venv\\Scripts\\python.exe scripts\\smoke_backend.py <exe>
    backend\\.venv\\Scripts\\python.exe scripts\\smoke_backend.py <exe> --https
    backend\\.venv\\Scripts\\python.exe scripts\\smoke_backend.py <exe> --repeticoes 5 --csv t.csv

A cada execução:
1. sobe o binário com ``FINANCAS_DATA_DIR`` temporário, token de teste, porta livre e
   ``FINANCAS_SEM_ATUALIZACAO=1`` (sem coleta de cotações);
2. mede o tempo do início do processo até o ``/health`` responder;
3. confere que a versão do ``/health`` é a do ``package.json`` da raiz;
4. confere que as migrações rodaram no banco vazio (revisão = ``head`` do Alembic);
5. com ``--https`` (só na primeira execução): pede a atualização da lista de tickers dos EUA
   e confere que o download HTTPS real funcionou (precisa de internet; fora dos testes
   automatizados);
6. encerra pela rota interna ``/api/sistema/encerrar`` e confere que o processo saiu e, no
   ``onefile``, que não sobrou pasta ``_MEIxxxx`` no ``%TEMP%``.

Sai com código 1 (e mensagem em pt-BR) no primeiro problema.
"""

import argparse
import csv
import json
import os
import secrets
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TIMEOUT_HEALTH_S = 120.0  # igual ao TIMEOUT_INICIO do Rust (1ª abertura com antivírus)
TIMEOUT_SAIDA_S = 10.0
TIMEOUT_HTTPS_S = 120.0


class SmokeError(Exception):
    """Falha do smoke test (mensagem em pt-BR)."""


def versao_esperada() -> str:
    versao = json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))["version"]
    return str(versao)


def revisao_head() -> str:
    from alembic.script import ScriptDirectory

    head = ScriptDirectory(str(RAIZ / "backend" / "migrations")).get_current_head()
    if head is None:
        raise SmokeError("Não há migrações em backend/migrations.")
    return head


def porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ouvinte:
        ouvinte.bind(("127.0.0.1", 0))
        return int(ouvinte.getsockname()[1])


def requisitar(
    url: str, metodo: str = "GET", token: str | None = None, timeout: float = 2.0
) -> tuple[int, object]:
    requisicao = urllib.request.Request(url, method=metodo)  # noqa: S310 - só 127.0.0.1
    if token:
        requisicao.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            corpo = resposta.read()
            return resposta.status, json.loads(corpo) if corpo else None
    except urllib.error.HTTPError as erro:
        return erro.code, None


def pastas_mei() -> set[str]:
    temp = Path(tempfile.gettempdir())
    return {p.name for p in temp.glob("_MEI*") if p.is_dir()}


def eh_onefile(exe: Path) -> bool:
    return not (exe.parent / "_internal").is_dir()


def conferir_https(base: str, token: str) -> None:
    """Listas de tickers (B3 e NASDAQ, HTTPS): a dos EUA baixada prova o truststore no
    executável. Espera a atualização inteira terminar antes de encerrar (um download em
    andamento seguraria o processo; no app o Tauri força o fim após 3 s)."""
    status, _ = requisitar(f"{base}/api/simbolos/atualizar", "POST", token)
    if status == 409:
        pass  # já havia uma atualização em andamento
    elif status != 202:
        raise SmokeError(f"POST /api/simbolos/atualizar respondeu {status}.")
    limite = time.monotonic() + TIMEOUT_HTTPS_S
    while time.monotonic() < limite:
        time.sleep(1)
        status, corpo = requisitar(f"{base}/api/simbolos/listas", token=token, timeout=5)
        if status != 200 or not isinstance(corpo, dict):
            continue
        eua = next((lista for lista in corpo["listas"] if lista["bolsa"] == "EUA"), None)
        if eua is None or corpo["em_andamento"]:
            continue
        if eua["quantidade"] > 0 and eua["atualizado_em"]:
            print(f"  HTTPS ok: lista dos EUA baixada ({eua['quantidade']} tickers).")
            return
        if eua["ultimo_erro"]:
            raise SmokeError(f"Download HTTPS falhou no executável: {eua['ultimo_erro']}")
    raise SmokeError(f"A lista dos EUA não foi baixada em {TIMEOUT_HTTPS_S:.0f} s.")


def executar(exe: Path, *, conferir: bool, https: bool) -> float:
    """Uma execução completa; devolve os segundos até o /health responder."""
    onefile = eh_onefile(exe)
    mei_antes = pastas_mei() if onefile else set()
    with tempfile.TemporaryDirectory(prefix="financas-smoke-") as dados:
        porta, token = porta_livre(), secrets.token_hex(32)
        ambiente = {
            **os.environ,
            "FINANCAS_DATA_DIR": dados,
            "FINANCAS_PORTA": str(porta),
            "FINANCAS_TOKEN": token,
            "FINANCAS_SEM_ATUALIZACAO": "1",
        }
        for variavel in ("FINANCAS_DEV", "FINANCAS_PID_PAI"):
            ambiente.pop(variavel, None)
        base = f"http://127.0.0.1:{porta}"
        stderr = Path(dados) / "stderr.log"
        with stderr.open("wb") as saida_erro:
            inicio = time.perf_counter()
            processo = subprocess.Popen(  # noqa: S603 - executável gerado pelo próprio build
                [str(exe)],
                env=ambiente,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=saida_erro,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                tempo = _aguardar_health(processo, base, inicio, stderr)
                if conferir:
                    _conferir_versao_e_migracoes(base, token, Path(dados))
                if https:
                    conferir_https(base, token)
                _encerrar(processo, base, token)
            finally:
                if processo.poll() is None:
                    processo.kill()
                    processo.wait()
    if onefile:
        # O bootloader apaga a pasta logo depois que o processo Python sai.
        limite = time.monotonic() + 5
        while (sobra := pastas_mei() - mei_antes) and time.monotonic() < limite:
            time.sleep(0.2)
        if sobra:
            raise SmokeError(f"Sobrou pasta temporária do PyInstaller em %TEMP%: {sorted(sobra)}.")
    return tempo


def _aguardar_health(
    processo: subprocess.Popen[bytes], base: str, inicio: float, stderr: Path
) -> float:
    limite = inicio + TIMEOUT_HEALTH_S
    while time.perf_counter() < limite:
        if processo.poll() is not None:
            detalhes = stderr.read_text(encoding="utf-8", errors="replace").strip()[-2000:]
            raise SmokeError(
                f"O executável fechou logo após iniciar (código {processo.returncode}).\n{detalhes}"
            )
        try:
            status, _ = requisitar(f"{base}/health", timeout=0.5)
            if status == 200:
                return time.perf_counter() - inicio
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(0.05)
    raise SmokeError(f"O /health não respondeu em {TIMEOUT_HEALTH_S:.0f} s.")


def _conferir_versao_e_migracoes(base: str, token: str, dados: Path) -> None:
    _, saude = requisitar(f"{base}/health")
    esperado = versao_esperada()
    versao = saude.get("versao") if isinstance(saude, dict) else None
    if versao != esperado:
        raise SmokeError(f"/health devolveu a versão {versao!r}; esperado {esperado!r}.")
    status, _ = requisitar(f"{base}/api/ping", token=token)
    if status != 200:
        raise SmokeError(f"/api/ping respondeu {status} com o token de teste.")
    banco = dados / "financas.db"
    if not banco.exists():
        raise SmokeError("O banco não foi criado na pasta de dados.")
    # closing(): o "with" da conexão do sqlite3 só faz commit, não fecha o arquivo.
    with closing(sqlite3.connect(f"file:{banco}?mode=ro", uri=True)) as conexao:
        linha = conexao.execute("SELECT version_num FROM alembic_version").fetchone()
    head = revisao_head()
    if linha is None or linha[0] != head:
        raise SmokeError(f"Migrações não chegaram ao head ({head}); banco em {linha!r}.")
    print(f"  Versão {versao} e migrações no head ({head}).")


def _encerrar(processo: subprocess.Popen[bytes], base: str, token: str) -> None:
    status, _ = requisitar(f"{base}/api/sistema/encerrar", "POST", token)
    if status != 202:
        raise SmokeError(f"Rota de encerramento respondeu {status}.")
    try:
        processo.wait(timeout=TIMEOUT_SAIDA_S)
    except subprocess.TimeoutExpired as erro:
        raise SmokeError(
            f"O processo não saiu em {TIMEOUT_SAIDA_S:.0f} s após o pedido de encerramento."
        ) from erro


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test do executável do backend.")
    parser.add_argument("exe", type=Path, help="financas-backend.exe gerado pelo PyInstaller")
    parser.add_argument("--https", action="store_true", help="confere um download HTTPS real")
    parser.add_argument("--repeticoes", type=int, default=1, help="execuções para medir o tempo")
    parser.add_argument("--csv", type=Path, help="acrescenta os tempos medidos neste arquivo")
    parser.add_argument("--rotulo", default="", help="rótulo da medição no CSV")
    args = parser.parse_args(argv)
    exe = args.exe.resolve()
    if not exe.is_file():
        print(f"[ERRO] Executável não encontrado: {exe}", file=sys.stderr)
        return 1
    modo = "onefile" if eh_onefile(exe) else "onedir"
    print(f"Smoke test do backend ({modo}): {exe}")
    tempos: list[float] = []
    try:
        for indice in range(args.repeticoes):
            tempo = executar(exe, conferir=indice == 0, https=args.https and indice == 0)
            tempos.append(tempo)
            print(f"  Execução {indice + 1}: /health em {tempo:.2f} s; encerrou sem sobras.")
    except SmokeError as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1
    if len(tempos) > 1:
        print(
            f"  Tempo até o /health: mín {min(tempos):.2f} s, mediana "
            f"{statistics.median(tempos):.2f} s, máx {max(tempos):.2f} s (N={len(tempos)})."
        )
    if args.csv:
        novo = not args.csv.exists()
        with args.csv.open("a", newline="", encoding="utf-8") as arquivo:
            escritor = csv.writer(arquivo)
            if novo:
                escritor.writerow(["modo", "rotulo", "execucao", "segundos"])
            for indice, tempo in enumerate(tempos, 1):
                escritor.writerow([modo, args.rotulo, indice, f"{tempo:.3f}"])
    print("Smoke test do executável: OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
