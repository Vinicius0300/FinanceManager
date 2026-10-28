import pytest

from app.core.config import ConfiguracaoInvalidaError, Settings


def test_le_configuracao_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINANCAS_TOKEN", "a" * 64)
    monkeypatch.setenv("FINANCAS_PORTA", "51234")
    monkeypatch.setenv("FINANCAS_PID_PAI", "999")
    monkeypatch.setenv("FINANCAS_DEV", "1")
    s = Settings.do_ambiente()
    assert (s.token, s.porta, s.pid_pai, s.dev) == ("a" * 64, 51234, 999, True)


def test_token_ausente_ou_curto_e_rejeitado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FINANCAS_TOKEN", raising=False)
    with pytest.raises(ConfiguracaoInvalidaError, match="Token de sessão"):
        Settings.do_ambiente()
    monkeypatch.setenv("FINANCAS_TOKEN", "curto")
    with pytest.raises(ConfiguracaoInvalidaError):
        Settings.do_ambiente()


def test_porta_invalida_tem_mensagem_clara(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINANCAS_TOKEN", "a" * 64)
    monkeypatch.setenv("FINANCAS_PORTA", "abc")
    with pytest.raises(ConfiguracaoInvalidaError, match="FINANCAS_PORTA"):
        Settings.do_ambiente()


def test_origens_de_dev_so_no_modo_dev() -> None:
    assert Settings(token="x").origens_cors == ["http://tauri.localhost"]
    assert "http://localhost:5173" in Settings(token="x", dev=True).origens_cors
