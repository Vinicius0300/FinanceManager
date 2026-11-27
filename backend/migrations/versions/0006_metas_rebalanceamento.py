"""Metas de alocação do Rebalanceamento (Parte 10).

Revisão: 0006_metas_rebalanceamento
Anterior: 0005_lancamentos_instituicao_transferencias
Criada em: 2026-11-26

1. Nova tabela ``metas_classe``: meta de cada classe (tipo de ativo do registry, sem CHECK
   de lista) em % da carteira, entre 0 e 100.
2. Nova tabela ``metas_ativo``: peso opcional de um ativo dentro da classe, em % da classe,
   entre 0 e 100. A chave estrangeira para ``ativos`` usa ``ON DELETE CASCADE``: excluir o
   ativo apaga o peso (o plano passa a avisar que os pesos da classe não somam 100%).

Tabelas próprias em vez de JSON em ``configuracoes`` por causa da FK com ``ativos``.
A tolerância da banda continua em ``configuracoes`` (``rebalanceamento_tolerancia_pp``).

Reversível: o downgrade remove as duas tabelas (as metas cadastradas se perdem).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_metas_rebalanceamento"
down_revision: str | Sequence[str] | None = "0005_lancamentos_instituicao_transferencias"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _faixa(coluna: str) -> str:
    return f"CAST({coluna} AS NUMERIC) >= 0 AND CAST({coluna} AS NUMERIC) <= 100"


def upgrade() -> None:
    op.create_table(
        "metas_classe",
        sa.Column("tipo_ativo", sa.String(length=40), nullable=False),
        sa.Column("percentual", sa.String(length=40), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(_faixa("percentual"), name=op.f("ck_metas_classe_percentual")),
        sa.PrimaryKeyConstraint("tipo_ativo", name=op.f("pk_metas_classe")),
    )
    op.create_table(
        "metas_ativo",
        sa.Column("ativo_id", sa.Integer(), nullable=False),
        sa.Column("peso", sa.String(length=40), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(_faixa("peso"), name=op.f("ck_metas_ativo_peso")),
        sa.ForeignKeyConstraint(
            ["ativo_id"],
            ["ativos.id"],
            name=op.f("fk_metas_ativo_ativo_id_ativos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ativo_id", name=op.f("pk_metas_ativo")),
    )


def downgrade() -> None:
    op.drop_table("metas_ativo")
    op.drop_table("metas_classe")
