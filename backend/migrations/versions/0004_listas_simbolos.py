"""Listas oficiais de tickers (B3 e EUA) e limpeza do tipo de papel "ETF".

Revisão: 0004_listas_simbolos
Anterior: 0003_precos_diarios_estado_coleta
Criada em: 2026-10-30

1. Nova tabela ``simbolos_listados``: ticker, nome e classificação oficial de cada papel
   (só para a busca do cadastro; nenhuma cotação).
2. Nova tabela ``listas_simbolos``: situação da última importação de cada bolsa.
3. ETFs passaram a ter tipo próprio (``etf_br``): ativos ``acao_br`` com
   ``tipo_papel = "ETF"`` perdem esse campo (opcional), senão a edição do ativo recusaria
   a opção que deixou de existir. O tipo do ativo **não** muda (não há reclassificação
   automática).

Reversível: o downgrade remove as tabelas (o campo removido não volta).
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_listas_simbolos"
down_revision: str | Sequence[str] | None = "0003_precos_diarios_estado_coleta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _remover_tipo_papel_etf() -> None:
    conexao = op.get_bind()
    linhas = conexao.execute(
        sa.text("SELECT id, metadados FROM ativos WHERE tipo = 'acao_br'")
    ).all()
    for identificador, bruto in linhas:
        metadados = json.loads(bruto) if isinstance(bruto, str) else (bruto or {})
        if metadados.get("tipo_papel") != "ETF":
            continue
        del metadados["tipo_papel"]
        conexao.execute(
            sa.text("UPDATE ativos SET metadados = :metadados WHERE id = :id"),
            {"metadados": json.dumps(metadados), "id": identificador},
        )


def upgrade() -> None:
    op.create_table(
        "listas_simbolos",
        sa.Column("bolsa", sa.String(length=10), nullable=False),
        sa.Column("ultima_tentativa", sa.DateTime(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(), nullable=True),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("status_arquivo", sa.String(length=60), nullable=True),
        sa.Column("data_arquivo", sa.Date(), nullable=True),
        sa.Column("ultimo_erro", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("bolsa", name=op.f("pk_listas_simbolos")),
    )
    op.create_table(
        "simbolos_listados",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bolsa", sa.String(length=10), nullable=False),
        sa.Column("simbolo", sa.String(length=30), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("tipo_papel", sa.String(length=20), nullable=True),
        sa.Column("bolsa_eua", sa.String(length=10), nullable=True),
        sa.Column("categoria", sa.String(length=60), nullable=False),
        sa.Column("simbolo_yahoo", sa.String(length=60), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simbolos_listados")),
        sa.UniqueConstraint("bolsa", "simbolo", name=op.f("uq_simbolos_listados_bolsa_simbolo")),
    )
    op.create_index("ix_simbolos_listados_simbolo", "simbolos_listados", ["simbolo"])
    _remover_tipo_papel_etf()


def downgrade() -> None:
    op.drop_index("ix_simbolos_listados_simbolo", table_name="simbolos_listados")
    op.drop_table("simbolos_listados")
    op.drop_table("listas_simbolos")
