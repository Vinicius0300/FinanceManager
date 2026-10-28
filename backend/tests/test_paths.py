from pathlib import Path

import pytest

from app.core import paths


def test_usa_appdata_quando_nao_ha_sobrescrita(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FINANCAS_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.diretorio_dados() == tmp_path / "Financas"
    assert paths.diretorio_logs() == tmp_path / "Financas" / "logs"
    assert paths.caminho_banco() == tmp_path / "Financas" / "financas.db"


def test_garantir_diretorios_e_idempotente(diretorio_dados_isolado: Path) -> None:
    paths.garantir_diretorios()
    paths.garantir_diretorios()
    assert {p.name for p in diretorio_dados_isolado.iterdir()} == {"logs", "backups", "models"}
