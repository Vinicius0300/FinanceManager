"""Banco: tipos de coluna, pragmas, constraints, backup e migrações com backup prévio."""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core import backup as modulo_backup
from app.core import migracoes
from app.core.backup import (
    BackupError,
    aplicar_retencao,
    criar_backup,
    restaurar_backup,
    validar_integridade,
)
from app.core.banco import criar_engine, criar_fabrica_sessoes, sessao_transacional
from app.core.migracoes import (
    MigracaoError,
    configuracao_alembic,
    migrar_banco,
    revisao_do_banco,
    revisao_head,
)
from app.domain.enums import OrigemPreco, TipoInstituicao, TipoTransacao
from app.repositories import modelos as m

TABELAS = {
    "alembic_version",
    "ativos",
    "categorias",
    "configuracoes",
    "contas_correntes",
    "estados_coleta",
    "eventos_corporativos",
    "indicadores",
    "instituicoes",
    "lancamentos",
    "movimentos_conta",
    "precos",
    "transacoes",
}


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return tmp_path / "dados" / "financas.db"


@pytest.fixture
def pasta_backups(tmp_path: Path) -> Path:
    return tmp_path / "dados" / "backups"


def tabelas(caminho: Path) -> set[str]:
    with closing(sqlite3.connect(caminho)) as conexao:
        linhas = conexao.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {nome for (nome,) in linhas}


# ---------------------------------------------------------------- Migrações


def test_migra_banco_novo_ate_a_head_sem_backup(banco: Path, pasta_backups: Path) -> None:
    banco.parent.mkdir(parents=True)
    resultado = migrar_banco(banco, pasta_backups)
    assert resultado.revisao_anterior is None
    assert resultado.revisao_atual == "0003_precos_diarios_estado_coleta"
    assert resultado.migrou
    assert resultado.backup is None
    assert tabelas(banco) == TABELAS
    assert revisao_do_banco(banco) == revisao_head(configuracao_alembic(banco))


def test_segunda_inicializacao_nao_migra_nem_faz_backup(banco: Path, pasta_backups: Path) -> None:
    banco.parent.mkdir(parents=True)
    migrar_banco(banco, pasta_backups)
    resultado = migrar_banco(banco, pasta_backups)
    assert not resultado.migrou
    assert resultado.backup is None
    assert not pasta_backups.exists()


def test_banco_existente_ganha_backup_validado_antes_de_migrar(
    banco: Path, pasta_backups: Path
) -> None:
    # Banco com dados mas sem as tabelas do app (ex.: versão antiga): o backup sai antes.
    banco.parent.mkdir(parents=True)
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute("CREATE TABLE legado (valor TEXT)")
        conexao.execute("INSERT INTO legado VALUES ('preservar')")
        conexao.commit()
    resultado = migrar_banco(banco, pasta_backups)
    assert resultado.backup is not None
    assert resultado.backup.parent == pasta_backups
    assert "pre-migracao" in resultado.backup.name
    assert tabelas(resultado.backup) == {"legado"}
    assert tabelas(banco) >= TABELAS
    with closing(sqlite3.connect(banco)) as conexao:
        assert conexao.execute("SELECT valor FROM legado").fetchall() == [("preservar",)]


def test_falha_na_migracao_restaura_o_backup(
    banco: Path, pasta_backups: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco.parent.mkdir(parents=True)
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute("CREATE TABLE legado (valor TEXT)")
        conexao.execute("INSERT INTO legado VALUES ('original')")
        conexao.commit()

    def upgrade_que_quebra(_config: object, _alvo: str) -> None:
        # Simula uma migração que alterou o banco pela metade e depois falhou.
        with closing(sqlite3.connect(banco)) as conexao:
            conexao.execute("DELETE FROM legado")
            conexao.execute("CREATE TABLE pela_metade (x INTEGER)")
            conexao.commit()
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(command, "upgrade", upgrade_que_quebra)
    with pytest.raises(MigracaoError, match="Os dados anteriores foram preservados"):
        migrar_banco(banco, pasta_backups)
    assert tabelas(banco) == {"legado"}
    with closing(sqlite3.connect(banco)) as conexao:
        assert conexao.execute("SELECT valor FROM legado").fetchall() == [("original",)]
    assert len(list(pasta_backups.glob("*.db"))) == 1


def test_falha_em_banco_novo_remove_o_arquivo_incompleto(
    banco: Path, pasta_backups: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco.parent.mkdir(parents=True)

    def upgrade_que_quebra(_config: object, _alvo: str) -> None:
        with closing(sqlite3.connect(banco)) as conexao:
            conexao.execute("CREATE TABLE pela_metade (x INTEGER)")
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(command, "upgrade", upgrade_que_quebra)
    with pytest.raises(MigracaoError):
        migrar_banco(banco, pasta_backups)
    assert not banco.exists()


def test_banco_de_versao_mais_nova_e_recusado(banco: Path, pasta_backups: Path) -> None:
    banco.parent.mkdir(parents=True)
    migrar_banco(banco, pasta_backups)
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute("UPDATE alembic_version SET version_num = '9999_futuro'")
        conexao.commit()
    with pytest.raises(MigracaoError, match="versão mais nova do Finanças"):
        migrar_banco(banco, pasta_backups)


def test_falha_no_backup_impede_a_migracao(
    banco: Path, pasta_backups: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco.parent.mkdir(parents=True)
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute("CREATE TABLE legado (x INTEGER)")

    def backup_que_falha(*_args: object, **_kwargs: object) -> Path:
        raise BackupError("disco cheio")

    monkeypatch.setattr(migracoes, "criar_backup", backup_que_falha)
    with pytest.raises(MigracaoError, match="Nenhuma alteração foi feita"):
        migrar_banco(banco, pasta_backups)
    assert tabelas(banco) == {"legado"}


def test_downgrade_e_upgrade_sao_reversiveis(banco: Path, pasta_backups: Path) -> None:
    banco.parent.mkdir(parents=True)
    migrar_banco(banco, pasta_backups)
    configuracao = configuracao_alembic(banco)
    command.downgrade(configuracao, "base")
    assert tabelas(banco) == {"alembic_version"}
    command.upgrade(configuracao, "head")
    assert tabelas(banco) == TABELAS


def test_migracao_0002_preenche_o_cambio_das_bonificacoes_estrangeiras(banco: Path) -> None:
    # Eventos já gravados ganham câmbio 1; bonificação com custo em ativo estrangeiro
    # recebe o câmbio mais recente com até 7 dias antes da data "ex" (regra do registro).
    banco.parent.mkdir(parents=True)
    configuracao = configuracao_alembic(banco)
    command.upgrade(configuracao, "0001_schema_inicial")
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.executescript(
            """
            INSERT INTO ativos VALUES
                (1, 'acao_us', 'AAPL', 'A', 'USD', NULL, NULL, '{}', '2025-01-01'),
                (2, 'acao_br', 'TST11', 'T', 'BRL', NULL, NULL, '{}', '2025-01-01');
            INSERT INTO indicadores VALUES (1, 'cambio', 'USD', '2025-03-28', '5.5', NULL);
            INSERT INTO indicadores VALUES (2, 'cambio', 'USD', '2025-01-02', '4', NULL);
            INSERT INTO eventos_corporativos VALUES
                (1, 1, 'bonificacao', '2025-04-01', 10, 11, '4', NULL, '2025-01-01'),
                (2, 1, 'desdobramento', '2025-05-01', 1, 2, '0', NULL, '2025-01-01'),
                (3, 2, 'bonificacao', '2025-04-01', 10, 11, '4', NULL, '2025-01-01'),
                (4, 1, 'bonificacao', '2025-02-01', 10, 11, '4', NULL, '2025-01-01');
            """
        )
        conexao.commit()
    command.upgrade(configuracao, "head")
    with closing(sqlite3.connect(banco)) as conexao:
        cambios = conexao.execute("SELECT id, cambio FROM eventos_corporativos ORDER BY id")
        assert cambios.fetchall() == [(1, "5.5"), (2, "1"), (3, "1"), (4, "1")]
        with pytest.raises(sqlite3.IntegrityError, match="ck_eventos_corporativos_cambio"):
            conexao.execute("UPDATE eventos_corporativos SET cambio = '0' WHERE id = 2")
        # A recriação da tabela pelo batch preserva os CHECKs antigos.
        with pytest.raises(sqlite3.IntegrityError, match="proporcao_por_tipo"):
            conexao.execute("UPDATE eventos_corporativos SET proporcao_para = 1 WHERE id = 2")


def test_migracao_0003_deixa_um_preco_por_dia_mantendo_o_ultimo(banco: Path) -> None:
    # Instantes em UTC; a data é a de Brasília (UTC−3):
    # id 1: 29/10 13:00 UTC = 29/10 10:00 local  (descartado: há um mais tarde no dia)
    # id 2: 29/10 20:00 UTC = 29/10 17:00 local  (mantido: último do dia 29)
    # id 3: 30/10 02:00 UTC = 29/10 23:00 local  -> mesmo dia 29 local e ainda mais tarde!
    # id 4: 30/10 13:00 UTC = 30/10 10:00 local  (mantido: único do dia 30)
    # id 5: outro ativo no dia 29 (mantido)
    banco.parent.mkdir(parents=True)
    configuracao = configuracao_alembic(banco)
    command.upgrade(configuracao, "0002_cambio_eventos")
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.executescript(
            """
            INSERT INTO ativos VALUES
                (1, 'acao_br', 'AAA3', 'A', 'BRL', NULL, NULL, '{}', '2025-01-01'),
                (2, 'acao_br', 'BBB3', 'B', 'BRL', NULL, NULL, '{}', '2025-01-01');
            INSERT INTO precos VALUES
                (1, 1, '2026-10-29 13:00:00.000000', '10', 'BRL', 'manual', NULL),
                (2, 1, '2026-10-29 20:00:00.000000', '11', 'BRL', 'manual', NULL),
                (3, 1, '2026-10-30 02:00:00.000000', '12', 'BRL', 'manual', NULL),
                (4, 1, '2026-10-30 13:00:00.000000', '13', 'BRL', 'manual', NULL),
                (5, 2, '2026-10-29 13:00:00.000000', '20', 'BRL', 'manual', NULL);
            """
        )
        conexao.commit()
    command.upgrade(configuracao, "head")
    with closing(sqlite3.connect(banco)) as conexao:
        linhas = conexao.execute("SELECT id, ativo_id, data, valor FROM precos ORDER BY id")
        assert linhas.fetchall() == [
            (3, 1, "2026-10-29", "12"),
            (4, 1, "2026-10-30", "13"),
            (5, 2, "2026-10-29", "20"),
        ]
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            conexao.execute(
                "INSERT INTO precos VALUES "
                "(9, 1, '2026-10-30 15:00:00', '14', 'BRL', 'manual', NULL, '2026-10-30')"
            )
        # O CHECK antigo continua valendo depois da recriação da tabela.
        with pytest.raises(sqlite3.IntegrityError, match="provider_automatico"):
            conexao.execute("UPDATE precos SET origem = 'automatico' WHERE id = 4")


def test_estado_coleta_e_removido_com_o_ativo(sessao: Session) -> None:
    ativo = m.Ativo(tipo="acao_br", simbolo="AAA3", nome="A", moeda="BRL")
    sessao.add(ativo)
    sessao.flush()
    sessao.add(m.EstadoColeta(chave=f"ativo:{ativo.id}", ativo_id=ativo.id))
    sessao.add(m.EstadoColeta(chave="indicador:cdi:BRL"))
    sessao.commit()
    sessao.delete(ativo)
    sessao.commit()
    assert [e.chave for e in sessao.query(m.EstadoColeta).all()] == ["indicador:cdi:BRL"]


def test_models_e_migracao_estao_sincronizados(banco: Path, pasta_backups: Path) -> None:
    # Se alguém mudar um model sem criar migração, este teste falha.
    banco.parent.mkdir(parents=True)
    migrar_banco(banco, pasta_backups)
    engine = criar_engine(banco)
    try:
        with engine.connect() as conexao:
            diferencas = compare_metadata(MigrationContext.configure(conexao), m.Base.metadata)
    finally:
        engine.dispose()
    assert diferencas == []


def test_migracao_cria_indices_por_ativo_e_data(banco: Path, pasta_backups: Path) -> None:
    banco.parent.mkdir(parents=True)
    migrar_banco(banco, pasta_backups)
    engine = criar_engine(banco)
    try:
        inspetor = inspect(engine)
        indices = {i["name"]: i["column_names"] for i in inspetor.get_indexes("transacoes")}
        assert indices["ix_transacoes_ativo_data"] == ["ativo_id", "data"]
        eventos = {
            i["name"]: i["column_names"] for i in inspetor.get_indexes("eventos_corporativos")
        }
        assert eventos["ix_eventos_corporativos_ativo_data"] == ["ativo_id", "data"]
        movimentos = {
            i["name"]: i["column_names"] for i in inspetor.get_indexes("movimentos_conta")
        }
        assert movimentos["ix_movimentos_conta_conta_data"] == ["conta_id", "data"]
    finally:
        engine.dispose()


# ---------------------------------------------------------------- Engine, pragmas e constraints


def test_pragmas_wal_e_chaves_estrangeiras(engine: Engine) -> None:
    with engine.connect() as conexao:
        assert conexao.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conexao.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conexao.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def _instituicao_e_ativo(sessao: Session) -> tuple[m.Instituicao, m.Ativo]:
    instituicao = m.Instituicao(nome="RICO", tipo=TipoInstituicao.CORRETORA)
    ativo = m.Ativo(tipo="acao_br", nome="Teste", simbolo="TST11", moeda="BRL")
    sessao.add_all([instituicao, ativo])
    sessao.flush()
    return instituicao, ativo


def _transacao(ativo_id: int, instituicao_id: int, **campos: object) -> m.Transacao:
    padrao: dict[str, object] = {
        "ativo_id": ativo_id,
        "instituicao_id": instituicao_id,
        "tipo": TipoTransacao.COMPRA,
        "data": date(2025, 1, 2),
        "quantidade": Decimal(10),
        "preco_unitario": Decimal(10),
        "moeda": "BRL",
        "cambio": Decimal(1),
    }
    return m.Transacao(**{**padrao, **campos})


def test_chave_estrangeira_e_respeitada(sessao: Session) -> None:
    sessao.add(_transacao(ativo_id=999, instituicao_id=999))
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        sessao.flush()


@pytest.mark.parametrize(
    "campos",
    [
        {"quantidade": Decimal(0)},  # quantidade > 0
        {"preco_unitario": Decimal(-1)},
        {"taxas": Decimal(-1)},
        {"valor": Decimal(10)},  # compra não tem valor
        {"cambio": Decimal(5)},  # BRL exige câmbio 1
        {"imposto_retido": Decimal(1)},  # só provento
        {
            "tipo": TipoTransacao.PROVENTO,
            "quantidade": None,
            "preco_unitario": None,
            "valor": Decimal(1),
        },
        {"moeda": "brl"},
    ],
)
def test_check_constraints_de_transacoes(sessao: Session, campos: dict[str, object]) -> None:
    instituicao, ativo = _instituicao_e_ativo(sessao)
    sessao.add(_transacao(ativo.id, instituicao.id, **campos))
    with pytest.raises(IntegrityError, match="CHECK"):
        sessao.flush()


def test_check_constraints_de_indicadores_e_movimentos(engine: Engine) -> None:
    indicador = "INSERT INTO indicadores (tipo, moeda, data, valor) VALUES "
    comandos_invalidos = [
        indicador + "('ipca', 'BRL', '2025-01-15', '0.4')",  # IPCA fora do dia 1º
        indicador + "('cambio', 'BRL', '2025-01-01', '5')",  # câmbio de BRL
        indicador + "('cdi', 'BRL', '2025-01-01', '-1')",  # taxa negativa
        "INSERT INTO movimentos_conta (conta_id, tipo, data, valor, criado_em) "
        "VALUES (1, 'debito_compra', '2025-01-01', '10', '2025-01-01')",
    ]
    for comando in comandos_invalidos:
        with engine.begin() as conexao, pytest.raises(IntegrityError):
            conexao.execute(text(comando))


def test_decimal_texto_preserva_valor_exato(sessao: Session) -> None:
    instituicao, ativo = _instituicao_e_ativo(sessao)
    quantidade = Decimal("0.12345678901234567890")
    sessao.add(
        _transacao(ativo.id, instituicao.id, quantidade=quantidade, preco_unitario=Decimal("0.1"))
    )
    sessao.commit()
    sessao.expire_all()
    gravada = sessao.query(m.Transacao).one()
    assert gravada.quantidade == quantidade
    assert gravada.preco_unitario == Decimal("0.1")
    bruto = sessao.execute(text("SELECT quantidade, typeof(quantidade) FROM transacoes")).one()
    assert tuple(bruto) == ("0.12345678901234567890", "text")


def test_decimal_texto_recusa_float(sessao: Session) -> None:
    instituicao, ativo = _instituicao_e_ativo(sessao)
    sessao.add(_transacao(ativo.id, instituicao.id, quantidade=0.1))
    with pytest.raises(StatementError, match="float é proibido"):
        sessao.flush()


def test_data_hora_utc(sessao: Session) -> None:
    _, ativo = _instituicao_e_ativo(sessao)
    brasilia = timezone(timedelta(hours=-3))
    sessao.add(
        m.Preco(
            ativo_id=ativo.id,
            data=date(2025, 1, 2),
            data_hora=datetime(2025, 1, 2, 12, tzinfo=brasilia),
            valor=Decimal(10),
            moeda="BRL",
            origem=OrigemPreco.MANUAL,
        )
    )
    sessao.commit()
    sessao.expire_all()
    gravado = sessao.query(m.Preco).one()
    assert gravado.data_hora == datetime(2025, 1, 2, 15, tzinfo=UTC)
    assert gravado.data_hora.tzinfo is UTC
    sessao.add(
        m.Preco(
            ativo_id=ativo.id,
            data=date(2025, 1, 3),
            data_hora=datetime(2025, 1, 3, 12),
            valor=Decimal(10),
            moeda="BRL",
            origem=OrigemPreco.MANUAL,
        )
    )
    with pytest.raises(StatementError, match="sem fuso"):
        sessao.flush()


def test_sessao_transacional_confirma_ou_desfaz(engine: Engine) -> None:
    fabrica = criar_fabrica_sessoes(engine)
    with sessao_transacional(fabrica) as sessao:
        sessao.add(m.Instituicao(nome="RICO", tipo=TipoInstituicao.CORRETORA))

    def gravar_e_falhar() -> None:
        with sessao_transacional(fabrica) as sessao:
            sessao.add(m.Instituicao(nome="XP", tipo=TipoInstituicao.CORRETORA))
            sessao.flush()
            raise RuntimeError("desfazer")

    with pytest.raises(RuntimeError):
        gravar_e_falhar()
    with sessao_transacional(fabrica) as sessao:
        assert [i.nome for i in sessao.query(m.Instituicao)] == ["RICO"]


# ---------------------------------------------------------------- Backup


def _banco_com_dado(caminho: Path, valor: str = "a") -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(caminho)) as conexao:
        conexao.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        conexao.execute("DELETE FROM t")
        conexao.execute("INSERT INTO t VALUES (?)", (valor,))
        conexao.commit()
    return caminho


def test_criar_backup_valida_e_nomeia(tmp_path: Path) -> None:
    banco = _banco_com_dado(tmp_path / "financas.db")
    agora = datetime(2025, 3, 4, 5, 6, 7, tzinfo=UTC)
    primeiro = criar_backup(banco, tmp_path / "bk", "Pré Migração!", agora=agora)
    segundo = criar_backup(banco, tmp_path / "bk", "Pré Migração!", agora=agora)
    assert primeiro.name == "financas-20250304-050607-pr-migra-o.db"
    assert segundo.name == "financas-20250304-050607-pr-migra-o-1.db"
    validar_integridade(primeiro)
    with closing(sqlite3.connect(primeiro)) as conexao:
        assert conexao.execute("SELECT v FROM t").fetchall() == [("a",)]


def test_retencao_mantem_os_mais_recentes(tmp_path: Path) -> None:
    banco = _banco_com_dado(tmp_path / "financas.db")
    for minuto in range(4):
        criar_backup(
            banco,
            tmp_path / "bk",
            "manual",
            agora=datetime(2025, 1, 1, 0, minuto, tzinfo=UTC),
            manter=2,
        )
    restantes = sorted(p.name for p in (tmp_path / "bk").glob("*.db"))
    assert restantes == ["financas-20250101-000200-manual.db", "financas-20250101-000300-manual.db"]
    assert aplicar_retencao(tmp_path / "bk", "manual", 5) == []


def test_backup_de_banco_inexistente_ou_corrompido(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="não encontrado"):
        criar_backup(tmp_path / "nada.db", tmp_path / "bk", "x")
    corrompido = tmp_path / "corrompido.db"
    corrompido.write_bytes(b"isto nao e um banco sqlite" * 100)
    with pytest.raises(BackupError):
        validar_integridade(corrompido)
    with pytest.raises(BackupError, match="Não foi possível criar o backup"):
        criar_backup(corrompido, tmp_path / "bk", "x")
    assert list((tmp_path / "bk").glob("*.db")) == []


def test_restaurar_backup(tmp_path: Path) -> None:
    banco = _banco_com_dado(tmp_path / "financas.db", "original")
    copia = criar_backup(banco, tmp_path / "bk", "manual")
    _banco_com_dado(banco, "alterado")
    restaurar_backup(copia, banco)
    with closing(sqlite3.connect(banco)) as conexao:
        assert conexao.execute("SELECT v FROM t").fetchall() == [("original",)]


def test_restaurar_falha_com_mensagem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    banco = _banco_com_dado(tmp_path / "financas.db")
    copia = criar_backup(banco, tmp_path / "bk", "manual")

    def copiar_que_falha(_origem: Path, _destino: Path) -> None:
        raise sqlite3.OperationalError("disco bloqueado")

    monkeypatch.setattr(modulo_backup, "_copiar", copiar_que_falha)
    with pytest.raises(BackupError, match="Não foi possível restaurar"):
        restaurar_backup(copia, banco)
