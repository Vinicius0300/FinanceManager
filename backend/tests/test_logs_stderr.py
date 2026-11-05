"""stderr do processo redirecionado ao ``backend.log`` (rotativo) no app instalado."""

import io
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.core.logs import StderrParaLog

PASTA_BACKEND = Path(__file__).resolve().parents[1]


def test_cada_linha_vira_um_registro_de_aviso(caplog: pytest.LogCaptureFixture) -> None:
    original = io.StringIO()
    saida = StderrParaLog(logging.getLogger("teste-stderr"), original)
    with caplog.at_level(logging.WARNING, logger="teste-stderr"):
        saida.write("Traceback (most recent call last):\n  File")
        saida.write(' "x.py", line 1\r\n\nValueError: ruim')
        assert [r.getMessage() for r in caplog.records] == [
            "Traceback (most recent call last):",
            '  File "x.py", line 1',
        ]
        saida.flush()  # o resto sem quebra de linha também é registrado
    assert [r.getMessage() for r in caplog.records][-1] == "ValueError: ruim"
    assert all(r.levelno == logging.WARNING for r in caplog.records)
    assert original.getvalue() == ""


def test_erro_do_proprio_logging_vai_ao_stderr_original_sem_recursao() -> None:
    original = io.StringIO()
    logger = logging.getLogger("teste-stderr-reentrada")
    logger.propagate = False
    saida = StderrParaLog(logger, original)

    class HandlerQueEscreveNoStderr(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Como o Handler.handleError faz quando o arquivo de log falha.
            saida.write(f"--- Logging error --- {record.getMessage()}\n")

    handler = HandlerQueEscreveNoStderr()
    logger.addHandler(handler)
    try:
        saida.write("mensagem\n")
    finally:
        logger.removeHandler(handler)
    assert original.getvalue() == "--- Logging error --- mensagem\n"


def test_no_processo_o_stderr_vai_para_o_backend_log(tmp_path: Path) -> None:
    script = textwrap.dedent(
        """
        import sys, threading, warnings
        from app.core.logs import configurar_logging, redirecionar_stderr_para_log

        configurar_logging(arquivo=True, console=False)
        redirecionar_stderr_para_log()
        redirecionar_stderr_para_log()  # idempotente
        print("print no stderr", file=sys.stderr)
        warnings.warn("aviso de biblioteca", DeprecationWarning, stacklevel=1)

        def falhar():
            raise RuntimeError("falha na thread")

        t = threading.Thread(target=falhar)
        t.start()
        t.join()
        """
    )
    dados = tmp_path / "dados"
    resultado = subprocess.run(  # noqa: S603 - interpretador do próprio venv
        [sys.executable, "-W", "always", "-c", script],
        cwd=PASTA_BACKEND,
        env={**os.environ, "FINANCAS_DATA_DIR": str(dados), "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    # Nada no stderr real (no app, o backend-stderr.log sem rotação).
    assert resultado.stderr == ""
    log = (dados / "logs" / "backend.log").read_text(encoding="utf-8")
    assert "WARNING" in log
    assert "stderr: print no stderr" in log
    assert "aviso de biblioteca" in log
    assert "RuntimeError: falha na thread" in log
