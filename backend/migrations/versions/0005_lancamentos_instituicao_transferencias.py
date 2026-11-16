"""Receitas e despesas por instituição e transferências entre instituições (Parte 8).

Revisão: 0005_lancamentos_instituicao_transferencias
Anterior: 0004_listas_simbolos
Criada em: 2026-11-15

1. Nova tabela ``transferencias`` (origem, destino, moeda, valor, tarifa).
2. ``lancamentos`` ganha ``instituicao_id`` (obrigatório) e ``transferencia_id`` (tarifa de
   uma transferência). A tabela é recriada; **se já tiver linhas, a migração falha** com
   mensagem em pt-BR (não há como saber a instituição de um lançamento antigo e não se
   inventa uma). O backup prévio da inicialização é restaurado nesse caso.
3. ``movimentos_conta`` ganha ``lancamento_id`` e ``transferencia_id``, os tipos
   ``credito_receita``, ``debito_despesa``, ``transferencia_saida`` e
   ``transferencia_entrada``, e a constraint ``vinculo`` (cada tipo com exatamente o
   vínculo certo). A tabela é recriada e os movimentos existentes são copiados.

O SQLite não altera CHECK nem tipo de coluna no lugar, por isso as tabelas são recriadas
(renomeia a antiga, cria a nova, copia, apaga a antiga).

Reversível com perda: o downgrade apaga as transferências, as receitas e despesas e os
movimentos ligados a elas (inclusive ajustes de saldo de despesas), porque o schema
antigo não tem onde guardá-los.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem

revision: str = "0005_lancamentos_instituicao_transferencias"
down_revision: str | Sequence[str] | None = "0004_listas_simbolos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MENSAGEM_LANCAMENTOS_EXISTENTES = (
    "Não foi possível atualizar o banco: há {quantidade} lançamento(s) de Receitas e "
    "Despesas sem instituição. A partir desta versão todo lançamento pertence a uma "
    "instituição. O banco foi restaurado do backup; exclua esses lançamentos na versão "
    "anterior do app (ou fale com o suporte) e abra o app de novo."
)

TIPOS_MOVIMENTO_ANTIGOS = (
    "deposito",
    "saque",
    "debito_compra",
    "credito_venda",
    "credito_provento",
    "ajuste_saldo",
)
TIPOS_MOVIMENTO_NOVOS = (
    *TIPOS_MOVIMENTO_ANTIGOS,
    "credito_receita",
    "debito_despesa",
    "transferencia_saida",
    "transferencia_entrada",
)

VINCULO_ANTIGO = (
    "(tipo IN ('debito_compra', 'credito_venda', 'credito_provento') "
    "AND transacao_id IS NOT NULL) OR "
    "(tipo IN ('deposito', 'saque') AND transacao_id IS NULL) OR "
    "tipo = 'ajuste_saldo'"
)
VINCULO_NOVO = (
    "(tipo IN ('debito_compra', 'credito_venda', 'credito_provento') "
    "AND transacao_id IS NOT NULL AND lancamento_id IS NULL AND transferencia_id IS NULL) OR "
    "(tipo IN ('credito_receita', 'debito_despesa') "
    "AND lancamento_id IS NOT NULL AND transacao_id IS NULL AND transferencia_id IS NULL) OR "
    "(tipo IN ('transferencia_saida', 'transferencia_entrada') "
    "AND transferencia_id IS NOT NULL AND transacao_id IS NULL AND lancamento_id IS NULL) OR "
    "(tipo IN ('deposito', 'saque') "
    "AND transacao_id IS NULL AND lancamento_id IS NULL AND transferencia_id IS NULL) OR "
    "(tipo = 'ajuste_saldo' AND transferencia_id IS NULL "
    "AND (transacao_id IS NULL OR lancamento_id IS NULL))"
)


def _enum(nome: str, valores: Sequence[str]) -> sa.Enum:
    return sa.Enum(*valores, name=nome, native_enum=False, create_constraint=True, length=30)


def _exigir_sem_lancamentos() -> None:
    quantidade = op.get_bind().execute(sa.text("SELECT count(*) FROM lancamentos")).scalar_one()
    if quantidade:
        raise RuntimeError(MENSAGEM_LANCAMENTOS_EXISTENTES.format(quantidade=quantidade))


def _criar_transferencias() -> None:
    op.create_table(
        "transferencias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("origem_id", sa.Integer(), nullable=False),
        sa.Column("destino_id", sa.Integer(), nullable=False),
        sa.Column("moeda", sa.String(length=3), nullable=False),
        sa.Column("valor", sa.String(length=40), nullable=False),
        sa.Column("tarifa", sa.String(length=40), nullable=False),
        sa.Column("descricao", sa.String(length=300), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "origem_id <> destino_id", name=op.f("ck_transferencias_origem_diferente_destino")
        ),
        sa.CheckConstraint("CAST(valor AS NUMERIC) > 0", name=op.f("ck_transferencias_valor")),
        sa.CheckConstraint("CAST(tarifa AS NUMERIC) >= 0", name=op.f("ck_transferencias_tarifa")),
        sa.CheckConstraint(
            "moeda = 'BRL' OR CAST(tarifa AS NUMERIC) = 0",
            name=op.f("ck_transferencias_tarifa_so_brl"),
        ),
        sa.CheckConstraint(
            "length(moeda) = 3 AND moeda = upper(moeda)",
            name=op.f("ck_transferencias_moeda_valida"),
        ),
        sa.ForeignKeyConstraint(
            ["origem_id"],
            ["instituicoes.id"],
            name=op.f("fk_transferencias_origem_id_instituicoes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destino_id"],
            ["instituicoes.id"],
            name=op.f("fk_transferencias_destino_id_instituicoes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transferencias")),
    )
    op.create_index("ix_transferencias_data", "transferencias", ["data"])
    op.create_index("ix_transferencias_origem", "transferencias", ["origem_id"])
    op.create_index("ix_transferencias_destino", "transferencias", ["destino_id"])


def _colunas_lancamentos(nova: bool) -> list[SchemaItem]:
    itens: list[SchemaItem] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo", _enum("tipo_lancamento", ("receita", "despesa")), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False),
        sa.Column("valor", sa.String(length=40), nullable=False),
    ]
    if nova:
        itens.append(sa.Column("instituicao_id", sa.Integer(), nullable=False))
    itens.append(sa.Column("categoria_id", sa.Integer(), nullable=True))
    if nova:
        itens.append(sa.Column("transferencia_id", sa.Integer(), nullable=True))
    itens += [
        sa.Column("observacao", sa.String(length=500), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint("CAST(valor AS NUMERIC) > 0", name=op.f("ck_lancamentos_valor")),
        sa.CheckConstraint(
            "length(trim(descricao)) > 0", name=op.f("ck_lancamentos_descricao_preenchida")
        ),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["categorias.id"],
            name=op.f("fk_lancamentos_categoria_id_categorias"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lancamentos")),
    ]
    if nova:
        itens += [
            sa.ForeignKeyConstraint(
                ["instituicao_id"],
                ["instituicoes.id"],
                name=op.f("fk_lancamentos_instituicao_id_instituicoes"),
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["transferencia_id"],
                ["transferencias.id"],
                name=op.f("fk_lancamentos_transferencia_id_transferencias"),
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("transferencia_id", name=op.f("uq_lancamentos_transferencia_id")),
        ]
    return itens


def _recriar_lancamentos(nova: bool) -> None:
    """Recria ``lancamentos`` no schema novo ou no antigo, copiando o que couber."""
    op.drop_index("ix_lancamentos_data", table_name="lancamentos")
    op.drop_index("ix_lancamentos_categoria", table_name="lancamentos")
    if nova:
        _exigir_sem_lancamentos()  # tabela vazia: não há o que copiar
    else:
        op.drop_index("ix_lancamentos_instituicao_data", table_name="lancamentos")
    op.rename_table("lancamentos", "lancamentos_antiga")
    op.create_table("lancamentos", *_colunas_lancamentos(nova))
    if not nova:
        # Volta sem instituição; as tarifas de transferência somem com as transferências.
        op.execute(
            "INSERT INTO lancamentos "
            "(id, tipo, data, descricao, valor, categoria_id, observacao, criado_em) "
            "SELECT id, tipo, data, descricao, valor, categoria_id, observacao, criado_em "
            "FROM lancamentos_antiga WHERE transferencia_id IS NULL"
        )
    op.drop_table("lancamentos_antiga")
    op.create_index("ix_lancamentos_data", "lancamentos", ["data"])
    op.create_index("ix_lancamentos_categoria", "lancamentos", ["categoria_id"])
    if nova:
        op.create_index(
            "ix_lancamentos_instituicao_data", "lancamentos", ["instituicao_id", "data"]
        )


def _recriar_movimentos(nova: bool) -> None:
    """Recria ``movimentos_conta`` no schema novo ou no antigo, copiando os movimentos."""
    op.drop_index("ix_movimentos_conta_conta_data", table_name="movimentos_conta")
    op.rename_table("movimentos_conta", "movimentos_conta_antiga")
    colunas: list[SchemaItem] = [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conta_id", sa.Integer(), nullable=False),
        sa.Column("transacao_id", sa.Integer(), nullable=True),
    ]
    if nova:
        colunas += [
            sa.Column("lancamento_id", sa.Integer(), nullable=True),
            sa.Column("transferencia_id", sa.Integer(), nullable=True),
        ]
    colunas += [
        sa.Column(
            "tipo",
            _enum("tipo_movimento", TIPOS_MOVIMENTO_NOVOS if nova else TIPOS_MOVIMENTO_ANTIGOS),
            nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("valor", sa.String(length=40), nullable=False),
        sa.Column("descricao", sa.String(length=300), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint("CAST(valor AS NUMERIC) > 0", name=op.f("ck_movimentos_conta_valor")),
        sa.ForeignKeyConstraint(
            ["conta_id"],
            ["contas_correntes.id"],
            name=op.f("fk_movimentos_conta_conta_id_contas_correntes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transacao_id"],
            ["transacoes.id"],
            name=op.f("fk_movimentos_conta_transacao_id_transacoes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movimentos_conta")),
        sa.UniqueConstraint(
            "transacao_id", "tipo", name=op.f("uq_movimentos_conta_transacao_id_tipo")
        ),
    ]
    if nova:
        colunas += [
            sa.CheckConstraint(VINCULO_NOVO, name=op.f("ck_movimentos_conta_vinculo")),
            sa.ForeignKeyConstraint(
                ["lancamento_id"],
                ["lancamentos.id"],
                name=op.f("fk_movimentos_conta_lancamento_id_lancamentos"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["transferencia_id"],
                ["transferencias.id"],
                name=op.f("fk_movimentos_conta_transferencia_id_transferencias"),
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "lancamento_id", "tipo", name=op.f("uq_movimentos_conta_lancamento_id_tipo")
            ),
            sa.UniqueConstraint(
                "transferencia_id", "tipo", name=op.f("uq_movimentos_conta_transferencia_id_tipo")
            ),
        ]
    else:
        colunas.append(
            sa.CheckConstraint(VINCULO_ANTIGO, name=op.f("ck_movimentos_conta_vinculo_transacao"))
        )
    op.create_table("movimentos_conta", *colunas)
    comuns = "id, conta_id, transacao_id, tipo, data, valor, descricao, criado_em"
    if nova:
        op.execute(
            f"INSERT INTO movimentos_conta ({comuns}) "
            f"SELECT {comuns} FROM movimentos_conta_antiga"
        )
    else:
        antigos = ", ".join(f"'{tipo}'" for tipo in TIPOS_MOVIMENTO_ANTIGOS)
        op.execute(
            f"INSERT INTO movimentos_conta ({comuns}) "
            f"SELECT {comuns} FROM movimentos_conta_antiga "
            f"WHERE tipo IN ({antigos}) AND lancamento_id IS NULL AND transferencia_id IS NULL"
        )
    op.drop_table("movimentos_conta_antiga")
    op.create_index("ix_movimentos_conta_conta_data", "movimentos_conta", ["conta_id", "data"])


def upgrade() -> None:
    _criar_transferencias()
    _recriar_lancamentos(nova=True)
    _recriar_movimentos(nova=True)


def downgrade() -> None:
    _recriar_movimentos(nova=False)
    _recriar_lancamentos(nova=False)
    op.drop_index("ix_transferencias_destino", table_name="transferencias")
    op.drop_index("ix_transferencias_origem", table_name="transferencias")
    op.drop_index("ix_transferencias_data", table_name="transferencias")
    op.drop_table("transferencias")
