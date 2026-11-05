"""Logs rotativos em ``%APPDATA%\\Financas\\logs\\backend.log``."""

import io
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from typing import TextIO, cast

from app.core import paths

NOME_HANDLER_ARQUIVO = "financas-arquivo"
NOME_HANDLER_CONSOLE = "financas-console"
TAMANHO_MAXIMO_BYTES = 1_000_000
QUANTIDADE_BACKUPS = 5
FORMATO = "%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s"
NOME_LOGGER_STDERR = "stderr"
# O Rust (apps/desktop/src-tauri/src/locais.rs) cita este nome nas mensagens de erro.
NOME_ARQUIVO_LOG = "backend.log"


class StderrParaLog(io.TextIOBase):
    """Substituto do ``sys.stderr`` que manda cada linha ao logging (nível WARNING).

    No app instalado o Tauri liga o stderr do processo a ``backend-stderr.log``, um arquivo sem
    rotação. Depois que o logging está configurado, o que ainda for escrito no stderr (avisos,
    exceção não tratada em thread, ``print`` de biblioteca) passa a ir para o ``backend.log``,
    que é rotativo. Erros do próprio logging (``Handler.handleError``) escrevem no stderr: essa
    reentrada vai direto para o stderr original, sem recursão.
    """

    def __init__(self, logger: logging.Logger, original: TextIO | None) -> None:
        super().__init__()
        self._logger = logger
        self._original = original
        self._pendente = ""
        self._trava = threading.Lock()
        self._local = threading.local()

    def writable(self) -> bool:
        return True

    def write(self, texto: str, /) -> int:
        if getattr(self._local, "ativo", False):
            self._escrever_no_original(texto)
            return len(texto)
        self._local.ativo = True
        try:
            with self._trava:
                self._pendente += texto
                *linhas, self._pendente = self._pendente.split("\n")
            for linha in linhas:
                if linha.strip():
                    self._logger.warning(linha.rstrip("\r"))
        finally:
            self._local.ativo = False
        return len(texto)

    def flush(self) -> None:
        with self._trava:
            resto, self._pendente = self._pendente, ""
        if resto.strip():
            self.write(resto + "\n")

    def _escrever_no_original(self, texto: str) -> None:
        if self._original is None:
            return
        try:
            self._original.write(texto)
            self._original.flush()
        except (OSError, ValueError):
            pass


def redirecionar_stderr_para_log() -> None:
    """Manda ``sys.stderr`` e os ``warnings`` para o logging (só no app instalado).

    O descritor 2 continua no ``backend-stderr.log``: falhas fatais do interpretador, que não
    passam pelo ``sys.stderr``, ainda ficam registradas lá.
    """
    if isinstance(sys.stderr, StderrParaLog):
        return
    logging.captureWarnings(True)
    sys.stderr = cast(TextIO, StderrParaLog(logging.getLogger(NOME_LOGGER_STDERR), sys.stderr))


def configurar_logging(*, arquivo: bool = True, console: bool = False) -> None:
    """Configura o logger raiz. Idempotente: pode ser chamada mais de uma vez.

    Com o reload do uvicorn (desenvolvimento) o processo supervisor só loga no
    console, porque dois processos rotacionando o mesmo arquivo falham no Windows.
    """
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    formatador = logging.Formatter(FORMATO)
    destino = paths.diretorio_logs() / NOME_ARQUIVO_LOG

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
