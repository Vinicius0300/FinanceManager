"""Câmbio gravado nos eventos corporativos.

Revisão: 0002_cambio_eventos
Anterior: 0001_schema_inicial
Criada em: 2026-10-29

Até aqui o câmbio de uma bonificação com custo atribuído (ativo estrangeiro) era buscado
nos indicadores a cada recálculo, então cadastrar um câmbio depois mudava o custo em BRL
já registrado. Agora ele fica gravado no evento, como nas transações.

Preenchimento dos eventos existentes: 1 para todos; nas bonificações com custo em
ativo estrangeiro, o câmbio mais recente com até 7 dias antes da data "ex" (a mesma
regra usada no registro). Reversível: o downgrade remove a coluna.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_cambio_eventos"
down_revision: str | Sequence[str] | None = "0001_schema_inicial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREENCHER_BONIFICACOES_ESTRANGEIRAS = """
UPDATE eventos_corporativos
SET cambio = (
    SELECT i.valor
    FROM indicadores AS i
    JOIN ativos AS a ON a.id = eventos_corporativos.ativo_id
    WHERE i.tipo = 'cambio'
      AND i.moeda = a.moeda
      AND i.data <= eventos_corporativos.data
      AND i.data >= date(eventos_corporativos.data, '-7 days')
    ORDER BY i.data DESC
    LIMIT 1
)
WHERE tipo = 'bonificacao'
  AND CAST(custo_unitario AS NUMERIC) > 0
  AND EXISTS (
    SELECT 1
    FROM indicadores AS i
    JOIN ativos AS a ON a.id = eventos_corporativos.ativo_id
    WHERE a.moeda <> 'BRL'
      AND i.tipo = 'cambio'
      AND i.moeda = a.moeda
      AND i.data <= eventos_corporativos.data
      AND i.data >= date(eventos_corporativos.data, '-7 days')
  )
"""


def upgrade() -> None:
    with op.batch_alter_table("eventos_corporativos") as batch:
        batch.add_column(
            sa.Column("cambio", sa.String(length=40), nullable=False, server_default="1")
        )
    op.execute(PREENCHER_BONIFICACOES_ESTRANGEIRAS)
    with op.batch_alter_table("eventos_corporativos") as batch:
        batch.alter_column("cambio", server_default=None)
        batch.create_check_constraint(
            op.f("ck_eventos_corporativos_cambio"), "CAST(cambio AS NUMERIC) > 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("eventos_corporativos") as batch:
        batch.drop_constraint(op.f("ck_eventos_corporativos_cambio"), type_="check")
        batch.drop_column("cambio")
