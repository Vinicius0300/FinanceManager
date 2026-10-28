import subprocess
import sys
import threading

import pytest

from app.core import watchdog


def test_aguardar_fim_processo_retorna_quando_processo_termina() -> None:
    filho = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
    terminou = threading.Event()

    def esperar() -> None:
        watchdog.aguardar_fim_processo(filho.pid)
        terminou.set()

    threading.Thread(target=esperar, daemon=True).start()
    assert terminou.wait(timeout=10), "watchdog não percebeu o fim do processo"
    filho.wait()


def test_watchdog_chama_callback_quando_pai_morre(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watchdog, "_iniciado", False)
    pai_falso = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
    morreu = threading.Event()

    assert watchdog.iniciar_watchdog(pai_falso.pid, ao_morrer=morreu.set) is True
    # Segunda chamada no mesmo processo não cria outra thread.
    assert watchdog.iniciar_watchdog(pai_falso.pid, ao_morrer=morreu.set) is False
    assert morreu.wait(timeout=10)
    pai_falso.wait()
