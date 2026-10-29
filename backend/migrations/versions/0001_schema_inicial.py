"""Schema inicial (Parte 2).

Revisão: 0001_schema_inicial
Anterior: nenhuma
Criada em: 2026-10-29

Tipos próprios do app (DecimalTexto, DataHoraUTC) aparecem aqui como os tipos de
armazenamento equivalentes (String/DateTime), para a migração não depender de código
do app que pode mudar no futuro. Reversível: o downgrade remove todas as tabelas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_schema_inicial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ativos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("simbolo", sa.String(length=30), nullable=True),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("moeda", sa.String(length=3), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("simbolo_externo", sa.String(length=60), nullable=True),
        sa.Column("metadados", sa.JSON(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(moeda) = 3 AND moeda = upper(moeda)", name=op.f("ck_ativos_moeda_valida")
        ),
        sa.CheckConstraint("length(trim(nome)) > 0", name=op.f("ck_ativos_nome_preenchido")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ativos")),
        sa.UniqueConstraint("tipo", "simbolo", name=op.f("uq_ativos_tipo_simbolo")),
    )
    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=80), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "receita",
                "despesa",
                name="tipo_categoria",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(nome)) > 0", name=op.f("ck_categorias_nome_preenchido")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categorias")),
        sa.UniqueConstraint("nome", "tipo", name=op.f("uq_categorias_nome_tipo")),
    )
    op.create_table(
        "configuracoes",
        sa.Column("chave", sa.String(length=80), nullable=False),
        sa.Column("valor", sa.JSON(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("chave", name=op.f("pk_configuracoes")),
    )
    op.create_table(
        "indicadores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "selic",
                "cdi",
                "ipca",
                "cambio",
                name="tipo_indicador",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("moeda", sa.String(length=3), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("valor", sa.String(length=40), nullable=False),
        sa.Column("fonte", sa.String(length=40), nullable=True),
        sa.CheckConstraint(
            "(tipo = 'cambio' AND moeda <> 'BRL') OR (tipo <> 'cambio' AND moeda = 'BRL')",
            name=op.f("ck_indicadores_moeda_por_tipo"),
        ),
        sa.CheckConstraint(
            "tipo <> 'ipca' OR strftime('%d', data) = '01'", name=op.f("ck_indicadores_ipca_mensal")
        ),
        sa.CheckConstraint(
            "tipo = 'ipca' OR (tipo = 'cambio' AND CAST(valor AS NUMERIC) > 0) OR (tipo IN ('selic', 'cdi') AND CAST(valor AS NUMERIC) >= 0)",
            name=op.f("ck_indicadores_valor_por_tipo"),
        ),
        sa.CheckConstraint(
            "length(moeda) = 3 AND moeda = upper(moeda)", name=op.f("ck_indicadores_moeda_valida")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_indicadores")),
        sa.UniqueConstraint("tipo", "moeda", "data", name=op.f("uq_indicadores_tipo_moeda_data")),
    )
    op.create_table(
        "instituicoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "corretora",
                "banco",
                "outro",
                name="tipo_instituicao",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(nome)) > 0", name=op.f("ck_instituicoes_nome_preenchido")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instituicoes")),
        sa.UniqueConstraint("nome", name=op.f("uq_instituicoes_nome")),
    )
    op.create_table(
        "contas_correntes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instituicao_id", sa.Integer(), nullable=False),
        sa.Column("moeda", sa.String(length=3), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(moeda) = 3 AND moeda = upper(moeda)",
            name=op.f("ck_contas_correntes_moeda_valida"),
        ),
        sa.ForeignKeyConstraint(
            ["instituicao_id"],
            ["instituicoes.id"],
            name=op.f("fk_contas_correntes_instituicao_id_instituicoes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contas_correntes")),
        sa.UniqueConstraint(
            "instituicao_id", "moeda", name=op.f("uq_contas_correntes_instituicao_id_moeda")
        ),
    )
    op.create_table(
        "eventos_corporativos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ativo_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "desdobramento",
                "grupamento",
                "bonificacao",
                name="tipo_evento",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("proporcao_de", sa.Integer(), nullable=False),
        sa.Column("proporcao_para", sa.Integer(), nullable=False),
        sa.Column("custo_unitario", sa.String(length=40), nullable=False),
        sa.Column("observacao", sa.String(length=500), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(tipo = 'grupamento' AND proporcao_para < proporcao_de) OR (tipo <> 'grupamento' AND proporcao_para > proporcao_de)",
            name=op.f("ck_eventos_corporativos_proporcao_por_tipo"),
        ),
        sa.CheckConstraint(
            "tipo = 'bonificacao' OR CAST(custo_unitario AS NUMERIC) = 0",
            name=op.f("ck_eventos_corporativos_custo_so_bonificacao"),
        ),
        sa.CheckConstraint(
            "CAST(custo_unitario AS NUMERIC) >= 0",
            name=op.f("ck_eventos_corporativos_custo_unitario"),
        ),
        sa.CheckConstraint(
            "proporcao_de > 0 AND proporcao_para > 0",
            name=op.f("ck_eventos_corporativos_proporcao_positiva"),
        ),
        sa.ForeignKeyConstraint(
            ["ativo_id"],
            ["ativos.id"],
            name=op.f("fk_eventos_corporativos_ativo_id_ativos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eventos_corporativos")),
        sa.UniqueConstraint(
            "ativo_id", "data", "tipo", name=op.f("uq_eventos_corporativos_ativo_id_data_tipo")
        ),
    )
    op.create_index(
        "ix_eventos_corporativos_ativo_data", "eventos_corporativos", ["ativo_id", "data"]
    )

    op.create_table(
        "lancamentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "receita",
                "despesa",
                name="tipo_lancamento",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False),
        sa.Column("valor", sa.String(length=40), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=True),
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
    )
    op.create_index("ix_lancamentos_categoria", "lancamentos", ["categoria_id"])
    op.create_index("ix_lancamentos_data", "lancamentos", ["data"])

    op.create_table(
        "precos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ativo_id", sa.Integer(), nullable=False),
        sa.Column("data_hora", sa.DateTime(), nullable=False),
        sa.Column("valor", sa.String(length=40), nullable=False),
        sa.Column("moeda", sa.String(length=3), nullable=False),
        sa.Column(
            "origem",
            sa.Enum(
                "automatico",
                "manual",
                "calculado",
                name="origem_preco",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.CheckConstraint(
            "origem <> 'automatico' OR provider IS NOT NULL",
            name=op.f("ck_precos_provider_automatico"),
        ),
        sa.CheckConstraint("CAST(valor AS NUMERIC) > 0", name=op.f("ck_precos_valor")),
        sa.CheckConstraint(
            "length(moeda) = 3 AND moeda = upper(moeda)", name=op.f("ck_precos_moeda_valida")
        ),
        sa.ForeignKeyConstraint(
            ["ativo_id"], ["ativos.id"], name=op.f("fk_precos_ativo_id_ativos"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_precos")),
        sa.UniqueConstraint("ativo_id", "data_hora", name=op.f("uq_precos_ativo_id_data_hora")),
    )
    op.create_table(
        "transacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ativo_id", sa.Integer(), nullable=False),
        sa.Column("instituicao_id", sa.Integer(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "compra",
                "venda",
                "aporte",
                "resgate",
                "provento",
                name="tipo_transacao",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("quantidade", sa.String(length=40), nullable=True),
        sa.Column("preco_unitario", sa.String(length=40), nullable=True),
        sa.Column("valor", sa.String(length=40), nullable=True),
        sa.Column("taxas", sa.String(length=40), nullable=False),
        sa.Column("moeda", sa.String(length=3), nullable=False),
        sa.Column("cambio", sa.String(length=40), nullable=False),
        sa.Column(
            "subtipo_provento",
            sa.Enum(
                "dividendo",
                "jcp",
                "rendimento",
                "outro",
                name="subtipo_provento",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=True,
        ),
        sa.Column("imposto_retido", sa.String(length=40), nullable=False),
        sa.Column("observacao", sa.String(length=500), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(tipo = 'provento' AND subtipo_provento IS NOT NULL) OR (tipo <> 'provento' AND subtipo_provento IS NULL)",
            name=op.f("ck_transacoes_subtipo_provento"),
        ),
        sa.CheckConstraint(
            "(tipo IN ('compra', 'venda') AND quantidade IS NOT NULL AND preco_unitario IS NOT NULL AND valor IS NULL) OR (tipo IN ('aporte', 'resgate', 'provento') AND valor IS NOT NULL AND quantidade IS NULL AND preco_unitario IS NULL)",
            name=op.f("ck_transacoes_campos_por_tipo"),
        ),
        sa.CheckConstraint(
            "moeda <> 'BRL' OR CAST(cambio AS NUMERIC) = 1",
            name=op.f("ck_transacoes_cambio_brl_unitario"),
        ),
        sa.CheckConstraint(
            "tipo = 'provento' OR CAST(imposto_retido AS NUMERIC) = 0",
            name=op.f("ck_transacoes_imposto_so_provento"),
        ),
        sa.CheckConstraint("CAST(cambio AS NUMERIC) > 0", name=op.f("ck_transacoes_cambio")),
        sa.CheckConstraint(
            "CAST(imposto_retido AS NUMERIC) >= 0", name=op.f("ck_transacoes_imposto_retido")
        ),
        sa.CheckConstraint("CAST(taxas AS NUMERIC) >= 0", name=op.f("ck_transacoes_taxas")),
        sa.CheckConstraint(
            "length(moeda) = 3 AND moeda = upper(moeda)", name=op.f("ck_transacoes_moeda_valida")
        ),
        sa.CheckConstraint(
            "preco_unitario IS NULL OR CAST(preco_unitario AS NUMERIC) >= 0",
            name=op.f("ck_transacoes_preco"),
        ),
        sa.CheckConstraint(
            "quantidade IS NULL OR CAST(quantidade AS NUMERIC) > 0",
            name=op.f("ck_transacoes_quantidade"),
        ),
        sa.CheckConstraint(
            "valor IS NULL OR CAST(valor AS NUMERIC) > 0", name=op.f("ck_transacoes_valor")
        ),
        sa.ForeignKeyConstraint(
            ["ativo_id"],
            ["ativos.id"],
            name=op.f("fk_transacoes_ativo_id_ativos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["instituicao_id"],
            ["instituicoes.id"],
            name=op.f("fk_transacoes_instituicao_id_instituicoes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transacoes")),
    )
    op.create_index("ix_transacoes_ativo_data", "transacoes", ["ativo_id", "data"])
    op.create_index("ix_transacoes_instituicao_data", "transacoes", ["instituicao_id", "data"])

    op.create_table(
        "movimentos_conta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conta_id", sa.Integer(), nullable=False),
        sa.Column("transacao_id", sa.Integer(), nullable=True),
        sa.Column(
            "tipo",
            sa.Enum(
                "deposito",
                "saque",
                "debito_compra",
                "credito_venda",
                "credito_provento",
                "ajuste_saldo",
                name="tipo_movimento",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("valor", sa.String(length=40), nullable=False),
        sa.Column("descricao", sa.String(length=300), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(tipo IN ('debito_compra', 'credito_venda', 'credito_provento') AND transacao_id IS NOT NULL) OR (tipo IN ('deposito', 'saque') AND transacao_id IS NULL) OR tipo = 'ajuste_saldo'",
            name=op.f("ck_movimentos_conta_vinculo_transacao"),
        ),
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
    )
    op.create_index("ix_movimentos_conta_conta_data", "movimentos_conta", ["conta_id", "data"])


def downgrade() -> None:
    op.drop_index("ix_movimentos_conta_conta_data", table_name="movimentos_conta")

    op.drop_table("movimentos_conta")
    op.drop_index("ix_transacoes_instituicao_data", table_name="transacoes")
    op.drop_index("ix_transacoes_ativo_data", table_name="transacoes")

    op.drop_table("transacoes")
    op.drop_table("precos")
    op.drop_index("ix_lancamentos_data", table_name="lancamentos")
    op.drop_index("ix_lancamentos_categoria", table_name="lancamentos")

    op.drop_table("lancamentos")
    op.drop_index("ix_eventos_corporativos_ativo_data", table_name="eventos_corporativos")

    op.drop_table("eventos_corporativos")
    op.drop_table("contas_correntes")
    op.drop_table("instituicoes")
    op.drop_table("indicadores")
    op.drop_table("configuracoes")
    op.drop_table("categorias")
    op.drop_table("ativos")
