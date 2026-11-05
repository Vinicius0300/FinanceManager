from pathlib import Path

import pytest

from app.core import logs, paths

LOCAIS_RS = Path(__file__).resolve().parents[2] / "apps/desktop/src-tauri/src/locais.rs"


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


def test_rust_usa_a_mesma_pasta_de_dados_e_de_logs() -> None:
    """O Tauri (locais.rs) repete a regra desta pasta para gravar o backend-stderr.log antes de
    o Python existir. Se uma das duas mudar, este teste falha."""
    rust = LOCAIS_RS.read_text(encoding="utf-8")
    assert f'pub const PASTA_DADOS: &str = "{paths.NOME_PASTA_APP}";' in rust
    assert f'std::env::var_os("{paths.VARIAVEL_RAIZ}")' in rust
    assert 'std::env::var_os("APPDATA")' in rust
    assert f'.map(|dados| dados.join("{paths.diretorio_logs().name}"))' in rust
    assert f'pub const ARQUIVO_LOG_BACKEND: &str = "{logs.NOME_ARQUIVO_LOG}";' in rust
