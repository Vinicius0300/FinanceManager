"""Watchdog: encerra o backend se o processo do app (pai) morrer.

Complementa o Job Object criado pelo Tauri; juntos garantem que não sobram
processos órfãos mesmo se o app for finalizado à força.
"""

import logging
import os
import sys
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

INTERVALO_VERIFICACAO_S = 2.0

_iniciado = False
_trava = threading.Lock()


def _aguardar_fim_windows(pid: int) -> None:
    import ctypes

    sincronizar = 0x00100000  # SYNCHRONIZE
    infinito = 0xFFFFFFFF
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(sincronizar, False, pid)
    if not handle:
        return  # processo já não existe (ou sem acesso): trata como morto
    try:
        kernel32.WaitForSingleObject(handle, infinito)
    finally:
        kernel32.CloseHandle(handle)


def _processo_vivo_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def aguardar_fim_processo(pid: int) -> None:
    """Bloqueia até o processo ``pid`` terminar."""
    if sys.platform == "win32":
        _aguardar_fim_windows(pid)
        return
    while _processo_vivo_posix(pid):
        time.sleep(INTERVALO_VERIFICACAO_S)


def _encerrar_processo() -> None:
    logging.shutdown()
    os._exit(0)


def iniciar_watchdog(pid_pai: int, ao_morrer: Callable[[], None] = _encerrar_processo) -> bool:
    """Inicia (uma única vez por processo) a thread que vigia o processo pai.

    Retorna ``True`` se iniciou agora e ``False`` se já estava ativo.
    """
    global _iniciado
    with _trava:
        if _iniciado:
            return False
        _iniciado = True

    def vigiar() -> None:
        aguardar_fim_processo(pid_pai)
        logger.warning("Processo do app (PID %s) terminou; encerrando o backend.", pid_pai)
        ao_morrer()

    threading.Thread(target=vigiar, name="watchdog-pai", daemon=True).start()
    logger.info("Watchdog ativo vigiando o PID %s.", pid_pai)
    return True
