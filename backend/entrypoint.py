"""Ponto de entrada do sidecar.

O Tauri inicia este processo com as variáveis de ambiente:
- ``FINANCAS_PORTA``: porta livre em 127.0.0.1 escolhida pelo app;
- ``FINANCAS_TOKEN``: token de sessão aleatório;
- ``FINANCAS_PID_PAI``: PID do app, vigiado pelo watchdog;
- ``FINANCAS_DEV=1``: modo desenvolvimento (CORS do Vite, /docs, logs no console).

Os argumentos de linha de comando servem para rodar à mão (ex.: ``--porta 8765``);
o token nunca é aceito por argumento para não aparecer na lista de processos.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn

from app.core.config import HOST, ConfiguracaoInvalidaError, Settings
from app.core.logs import configurar_logging
from app.core.watchdog import iniciar_watchdog
from app.main import create_app

PASTA_BACKEND = Path(__file__).resolve().parent
logger = logging.getLogger("entrypoint")


def _ler_argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backend local do app Finanças.")
    parser.add_argument("--porta", type=int, help="sobrescreve FINANCAS_PORTA")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="recarrega ao editar o código (somente desenvolvimento)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _ler_argumentos(argv)
    if args.porta is not None:
        os.environ["FINANCAS_PORTA"] = str(args.porta)

    try:
        settings = Settings.do_ambiente()
    except ConfiguracaoInvalidaError as erro:
        print(f"Erro de configuração: {erro}", file=sys.stderr)
        return 2
    if not settings.porta:
        print("Erro de configuração: porta não informada (FINANCAS_PORTA).", file=sys.stderr)
        return 2

    # No modo reload, este processo é só o supervisor: loga no console e o
    # processo filho (worker) cuida do arquivo de log.
    configurar_logging(arquivo=not args.reload, console=settings.dev or args.reload)
    if settings.pid_pai:
        iniciar_watchdog(settings.pid_pai)

    try:
        if args.reload:
            uvicorn.run(
                "app.main:create_app",
                factory=True,
                host=HOST,
                port=settings.porta,
                reload=True,
                reload_dirs=[str(PASTA_BACKEND / "app")],
                log_config=None,
            )
        else:
            servidor: uvicorn.Server | None = None

            def solicitar_encerramento() -> None:
                if servidor is not None:
                    servidor.should_exit = True

            app = create_app(settings, solicitar_encerramento=solicitar_encerramento)
            servidor = uvicorn.Server(
                uvicorn.Config(app, host=HOST, port=settings.porta, log_config=None)
            )
            servidor.run()
    except KeyboardInterrupt:
        pass
    logger.info("Processo do backend finalizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
