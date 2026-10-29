"""Um preço por ativo por dia e estado da coleta automática.

Revisão: 0003_precos_diarios_estado_coleta
Anterior: 0002_cambio_eventos
Criada em: 2026-10-29

1. ``precos`` ganha ``data`` (data local de Brasília do instante do preço) e passa a ter
   unicidade por (ativo, data) no lugar de (ativo, data_hora). Registros já gravados são
   deduplicados mantendo, em cada dia, o **último** (maior ``data_hora``; empate: maior id),
   que é o fechamento do dia.
2. Nova tabela ``estados_coleta``: última tentativa, último sucesso, último erro, provider
   e início do histórico baixado de cada alvo da atualização automática.

A data local é calculada em Python (``zoneinfo``), porque o SQLite não conhece fusos e o
Brasil teve horário de verão até 2019. Reversível: o downgrade remove a coluna e a tabela
(os registros removidos na deduplicação não voltam).
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision: str = "0003_precos_diarios_estado_coleta"
down_revision: str | Sequence[str] | None = "0002_cambio_eventos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")


def _data_local(valor: object) -> date:
    instante = valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
    return instante.replace(tzinfo=UTC).astimezone(FUSO_LOCAL).date()


def _preencher_e_deduplicar() -> None:
    conexao = op.get_bind()
    linhas = conexao.execute(
        sa.text("SELECT id, ativo_id, data_hora FROM precos ORDER BY ativo_id, data_hora, id")
    ).all()
    manter: dict[tuple[int, date], int] = {}
    datas: dict[int, date] = {}
    for identificador, ativo_id, data_hora in linhas:
        dia = _data_local(data_hora)
        datas[identificador] = dia
        manter[(ativo_id, dia)] = identificador  # ordem crescente: fica o último do dia
    mantidos = set(manter.values())
    for identificador, dia in datas.items():
        if identificador in mantidos:
            conexao.execute(
                sa.text("UPDATE precos SET data = :data WHERE id = :id"),
                {"data": dia.isoformat(), "id": identificador},
            )
        else:
            conexao.execute(sa.text("DELETE FROM precos WHERE id = :id"), {"id": identificador})


def upgrade() -> None:
    with op.batch_alter_table("precos") as batch:
        batch.add_column(sa.Column("data", sa.Date(), nullable=True))
    _preencher_e_deduplicar()
    with op.batch_alter_table("precos") as batch:
        batch.alter_column("data", existing_type=sa.Date(), nullable=False)
        batch.drop_constraint(op.f("uq_precos_ativo_id_data_hora"), type_="unique")
        batch.create_unique_constraint(op.f("uq_precos_ativo_id_data"), ["ativo_id", "data"])

    op.create_table(
        "estados_coleta",
        sa.Column("chave", sa.String(length=60), nullable=False),
        sa.Column("ativo_id", sa.Integer(), nullable=True),
        sa.Column("ultima_tentativa", sa.DateTime(), nullable=True),
        sa.Column("ultimo_sucesso", sa.DateTime(), nullable=True),
        sa.Column("ultimo_erro", sa.String(length=500), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("historico_desde", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ativo_id"],
            ["ativos.id"],
            name=op.f("fk_estados_coleta_ativo_id_ativos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("chave", name=op.f("pk_estados_coleta")),
    )


def downgrade() -> None:
    op.drop_table("estados_coleta")
    with op.batch_alter_table("precos") as batch:
        batch.drop_constraint(op.f("uq_precos_ativo_id_data"), type_="unique")
        batch.create_unique_constraint(
            op.f("uq_precos_ativo_id_data_hora"), ["ativo_id", "data_hora"]
        )
        batch.drop_column("data")
