"""Logs rotativos em ``%APPDATA%\\Financas\\logs\\backend.log``."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from app.core import paths

NOME_HANDLER_ARQUIVO = "financas-arquivo"
NOME_HANDLER_CONSOLE = "financas-console"
TAMANHO_MAXIMO_BYTES = 1_000_000
QUANTIDADE_BACKUPS = 5
FORMATO = "%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s"


def configurar_logging(*, arquivo: bool = True, console: bool = False) -> None:
    """Configura o logger raiz. Idempotente: pode ser chamada mais de uma vez.

    Com o reload do uvicorn (desenvolvimento) o processo supervisor só loga no
    console, porque dois processos rotacionando o mesmo arquivo falham no Windows.
    """
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    formatador = logging.Formatter(FORMATO)
    destino = paths.diretorio_logs() / "backend.log"

    # Se a pasta de dados mudou (ex.: testes), troca o handler de arquivo.
    for handler in list(raiz.handlers):
        if handler.get_name() == NOME_HANDLER_ARQUIVO and (
            not arquivo
            or not isinstance(handler, RotatingFileHandler)
            or handler.baseFilename != os.path.abspath(destino)
        ):
            raiz.removeHandler(handler)
            handler.close()
    existentes = {h.get_name() for h in raiz.handlers}

    if arquivo and NOME_HANDLER_ARQUIVO not in existentes:
        paths.garantir_diretorios()
        handler_arquivo = RotatingFileHandler(
            destino,
            maxBytes=TAMANHO_MAXIMO_BYTES,
            backupCount=QUANTIDADE_BACKUPS,
            encoding="utf-8",
        )
        handler_arquivo.set_name(NOME_HANDLER_ARQUIVO)
        handler_arquivo.setFormatter(formatador)
        raiz.addHandler(handler_arquivo)

    if console and NOME_HANDLER_CONSOLE not in existentes:
        handler_console = logging.StreamHandler(sys.stderr)
        handler_console.set_name(NOME_HANDLER_CONSOLE)
        handler_console.setFormatter(formatador)
        raiz.addHandler(handler_console)
