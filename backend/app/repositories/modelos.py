"""Modelos SQLAlchemy 2.0 (schema do banco). Alterou algo aqui? Crie uma migração Alembic.

Convenções:
- dinheiro, quantidades, taxas e câmbio em ``DecimalTexto`` (TEXT exato, nunca float);
- instantes em ``DataHoraUTC``; datas de negócio em ``Date``;
- enums gravados como texto com CHECK; o tipo de ativo é texto livre validado pelo
  registry (``asset_types``), para que um tipo novo não exija migração;
- nomes de constraints padronizados (necessário para ``batch_alter_table`` no SQLite).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.enums import (
    OrigemPreco,
    SubtipoProvento,
    TipoEvento,
    TipoIndicador,
    TipoInstituicao,
    TipoLancamento,
    TipoMovimento,
    TipoTransacao,
)
from app.repositories.tipos import DataHoraUTC, DecimalTexto

CONVENCAO_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)
    type_annotation_map = {  # noqa: RUF012 - API declarativa do SQLAlchemy
        Decimal: DecimalTexto(),
        datetime: DataHoraUTC(),
        date: Date(),
        dict[str, Any]: JSON(),
    }


def agora_utc() -> datetime:
    return datetime.now(UTC)


def enum_texto(classe: type[StrEnum], nome: str) -> Enum:
    """Enum gravado como texto (valor, não nome) com CHECK constraint."""
    return Enum(
        classe,
        name=nome,
        native_enum=False,
        create_constraint=True,
        length=30,
        values_callable=lambda membros: [m.value for m in membros],
        validate_strings=True,
    )


def _positivo(coluna: str) -> str:
    return f"CAST({coluna} AS NUMERIC) > 0"


def _nao_negativo(coluna: str) -> str:
    return f"CAST({coluna} AS NUMERIC) >= 0"


_MOEDA_VALIDA = "length({c}) = 3 AND {c} = upper({c})"


class Instituicao(Base):
    """Onde o dinheiro está alocado (corretora, banco ou outro lugar)."""

    __tablename__ = "instituicoes"
    __table_args__ = (CheckConstraint("length(trim(nome)) > 0", name="nome_preenchido"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), unique=True)
    tipo: Mapped[TipoInstituicao] = mapped_column(enum_texto(TipoInstituicao, "tipo_instituicao"))
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)


class ContaCorrente(Base):
    """Dinheiro parado em uma instituição, em uma moeda (não rende)."""

    __tablename__ = "contas_correntes"
    __table_args__ = (
        UniqueConstraint("instituicao_id", "moeda"),
        CheckConstraint(_MOEDA_VALIDA.format(c="moeda"), name="moeda_valida"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instituicao_id: Mapped[int] = mapped_column(ForeignKey("instituicoes.id", ondelete="RESTRICT"))
    moeda: Mapped[str] = mapped_column(String(3))
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)

    instituicao: Mapped[Instituicao] = relationship()


class Ativo(Base):
    __tablename__ = "ativos"
    __table_args__ = (
        UniqueConstraint("tipo", "simbolo"),
        CheckConstraint("length(trim(nome)) > 0", name="nome_preenchido"),
        CheckConstraint(_MOEDA_VALIDA.format(c="moeda"), name="moeda_valida"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(40))  # slug do registry de tipos de ativo
    simbolo: Mapped[str | None] = mapped_column(String(30))
    nome: Mapped[str] = mapped_column(String(150))
    moeda: Mapped[str] = mapped_column(String(3))
    provider: Mapped[str | None] = mapped_column(String(40))
    simbolo_externo: Mapped[str | None] = mapped_column(String(60))
    metadados: Mapped[dict[str, Any]] = mapped_column(default=dict)
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)


class Transacao(Base):
    """Compra, venda, aporte, resgate ou provento de um ativo em uma instituição."""

    __tablename__ = "transacoes"
    __table_args__ = (
        CheckConstraint(
            "(tipo IN ('compra', 'venda') AND quantidade IS NOT NULL "
            "AND preco_unitario IS NOT NULL AND valor IS NULL) OR "
            "(tipo IN ('aporte', 'resgate', 'provento') AND valor IS NOT NULL "
            "AND quantidade IS NULL AND preco_unitario IS NULL)",
            name="campos_por_tipo",
        ),
        CheckConstraint(f"quantidade IS NULL OR {_positivo('quantidade')}", name="quantidade"),
        CheckConstraint(
            f"preco_unitario IS NULL OR {_nao_negativo('preco_unitario')}", name="preco"
        ),
        CheckConstraint(f"valor IS NULL OR {_positivo('valor')}", name="valor"),
        CheckConstraint(_nao_negativo("taxas"), name="taxas"),
        CheckConstraint(_positivo("cambio"), name="cambio"),
        CheckConstraint(_nao_negativo("imposto_retido"), name="imposto_retido"),
        CheckConstraint(
            "(tipo = 'provento' AND subtipo_provento IS NOT NULL) OR "
            "(tipo <> 'provento' AND subtipo_provento IS NULL)",
            name="subtipo_provento",
        ),
        CheckConstraint(
            "tipo = 'provento' OR CAST(imposto_retido AS NUMERIC) = 0",
            name="imposto_so_provento",
        ),
        CheckConstraint(
            "moeda <> 'BRL' OR CAST(cambio AS NUMERIC) = 1", name="cambio_brl_unitario"
        ),
        CheckConstraint(_MOEDA_VALIDA.format(c="moeda"), name="moeda_valida"),
        Index("ix_transacoes_ativo_data", "ativo_id", "data"),
        Index("ix_transacoes_instituicao_data", "instituicao_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ativo_id: Mapped[int] = mapped_column(ForeignKey("ativos.id", ondelete="RESTRICT"))
    instituicao_id: Mapped[int] = mapped_column(ForeignKey("instituicoes.id", ondelete="RESTRICT"))
    tipo: Mapped[TipoTransacao] = mapped_column(enum_texto(TipoTransacao, "tipo_transacao"))
    data: Mapped[date]
    quantidade: Mapped[Decimal | None]
    preco_unitario: Mapped[Decimal | None]
    valor: Mapped[Decimal | None]  # aporte/resgate em R$; provento líquido
    taxas: Mapped[Decimal] = mapped_column(default=Decimal(0))
    moeda: Mapped[str] = mapped_column(String(3))
    cambio: Mapped[Decimal]  # BRL por unidade da moeda, na data da transação
    subtipo_provento: Mapped[SubtipoProvento | None] = mapped_column(
        enum_texto(SubtipoProvento, "subtipo_provento")
    )
    imposto_retido: Mapped[Decimal] = mapped_column(default=Decimal(0))
    observacao: Mapped[str | None] = mapped_column(String(500))
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)

    movimentos: Mapped[list["MovimentoConta"]] = relationship(
        back_populates="transacao", cascade="all, delete-orphan", passive_deletes=True
    )


class EventoCorporativo(Base):
    """Desdobramento, grupamento ou bonificação (proporção de:para, na data "ex")."""

    __tablename__ = "eventos_corporativos"
    __table_args__ = (
        UniqueConstraint("ativo_id", "data", "tipo"),
        CheckConstraint("proporcao_de > 0 AND proporcao_para > 0", name="proporcao_positiva"),
        CheckConstraint(
            "(tipo = 'grupamento' AND proporcao_para < proporcao_de) OR "
            "(tipo <> 'grupamento' AND proporcao_para > proporcao_de)",
            name="proporcao_por_tipo",
        ),
        CheckConstraint(_nao_negativo("custo_unitario"), name="custo_unitario"),
        CheckConstraint(
            "tipo = 'bonificacao' OR CAST(custo_unitario AS NUMERIC) = 0",
            name="custo_so_bonificacao",
        ),
        CheckConstraint(_positivo("cambio"), name="cambio"),
        Index("ix_eventos_corporativos_ativo_data", "ativo_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ativo_id: Mapped[int] = mapped_column(ForeignKey("ativos.id", ondelete="CASCADE"))
    tipo: Mapped[TipoEvento] = mapped_column(enum_texto(TipoEvento, "tipo_evento"))
    data: Mapped[date]
    proporcao_de: Mapped[int] = mapped_column(Integer)
    proporcao_para: Mapped[int] = mapped_column(Integer)
    custo_unitario: Mapped[Decimal] = mapped_column(default=Decimal(0))
    cambio: Mapped[Decimal] = mapped_column(default=Decimal(1))  # BRL por unidade, na data
    observacao: Mapped[str | None] = mapped_column(String(500))
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)


class Preco(Base):
    """Um preço por ativo por dia (data local de Brasília); o último do dia é o fechamento.

    ``data_hora`` é o instante da coleta (ou do lançamento manual) que gerou o valor.
    """

    __tablename__ = "precos"
    __table_args__ = (
        UniqueConstraint("ativo_id", "data"),
        CheckConstraint(_positivo("valor"), name="valor"),
        CheckConstraint(
            "origem <> 'automatico' OR provider IS NOT NULL", name="provider_automatico"
        ),
        CheckConstraint(_MOEDA_VALIDA.format(c="moeda"), name="moeda_valida"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ativo_id: Mapped[int] = mapped_column(ForeignKey("ativos.id", ondelete="CASCADE"))
    data: Mapped[date]
    data_hora: Mapped[datetime]
    valor: Mapped[Decimal]
    moeda: Mapped[str] = mapped_column(String(3))
    origem: Mapped[OrigemPreco] = mapped_column(enum_texto(OrigemPreco, "origem_preco"))
    provider: Mapped[str | None] = mapped_column(String(40))


class Indicador(Base):
    """Selic/CDI (% a.a., diário), IPCA (% no mês, data = dia 1º) e câmbio (BRL por unidade)."""

    __tablename__ = "indicadores"
    __table_args__ = (
        UniqueConstraint("tipo", "moeda", "data"),
        CheckConstraint(
            "(tipo = 'cambio' AND moeda <> 'BRL') OR (tipo <> 'cambio' AND moeda = 'BRL')",
            name="moeda_por_tipo",
        ),
        CheckConstraint(
            f"tipo = 'ipca' OR (tipo = 'cambio' AND {_positivo('valor')}) "
            f"OR (tipo IN ('selic', 'cdi') AND {_nao_negativo('valor')})",
            name="valor_por_tipo",
        ),
        CheckConstraint("tipo <> 'ipca' OR strftime('%d', data) = '01'", name="ipca_mensal"),
        CheckConstraint(_MOEDA_VALIDA.format(c="moeda"), name="moeda_valida"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoIndicador] = mapped_column(enum_texto(TipoIndicador, "tipo_indicador"))
    moeda: Mapped[str] = mapped_column(String(3), default="BRL")
    data: Mapped[date]
    valor: Mapped[Decimal]
    fonte: Mapped[str | None] = mapped_column(String(40))


class EstadoColeta(Base):
    """Situação da atualização automática de um alvo (um ativo ou um indicador).

    ``chave``: ``ativo:<id>`` ou ``indicador:<tipo>:<moeda>``. ``historico_desde`` é a
    data mais antiga já baixada do histórico (``None``: histórico ainda não baixado).
    """

    __tablename__ = "estados_coleta"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    ativo_id: Mapped[int | None] = mapped_column(ForeignKey("ativos.id", ondelete="CASCADE"))
    ultima_tentativa: Mapped[datetime | None]
    ultimo_sucesso: Mapped[datetime | None]
    ultimo_erro: Mapped[str | None] = mapped_column(String(500))
    provider: Mapped[str | None] = mapped_column(String(40))
    historico_desde: Mapped[date | None]


class MovimentoConta(Base):
    """Movimento da conta corrente; valor sempre positivo, o sinal vem do tipo."""

    __tablename__ = "movimentos_conta"
    __table_args__ = (
        UniqueConstraint("transacao_id", "tipo"),
        CheckConstraint(_positivo("valor"), name="valor"),
        CheckConstraint(
            "(tipo IN ('debito_compra', 'credito_venda', 'credito_provento') "
            "AND transacao_id IS NOT NULL) OR "
            "(tipo IN ('deposito', 'saque') AND transacao_id IS NULL) OR "
            "tipo = 'ajuste_saldo'",
            name="vinculo_transacao",
        ),
        Index("ix_movimentos_conta_conta_data", "conta_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas_correntes.id", ondelete="RESTRICT"))
    transacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("transacoes.id", ondelete="CASCADE")
    )
    tipo: Mapped[TipoMovimento] = mapped_column(enum_texto(TipoMovimento, "tipo_movimento"))
    data: Mapped[date]
    valor: Mapped[Decimal]
    descricao: Mapped[str | None] = mapped_column(String(300))
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)

    conta: Mapped[ContaCorrente] = relationship()
    transacao: Mapped[Transacao | None] = relationship(back_populates="movimentos")


class Categoria(Base):
    __tablename__ = "categorias"
    __table_args__ = (
        UniqueConstraint("nome", "tipo"),
        CheckConstraint("length(trim(nome)) > 0", name="nome_preenchido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[TipoLancamento] = mapped_column(enum_texto(TipoLancamento, "tipo_categoria"))


class Lancamento(Base):
    """Receita ou despesa do orçamento pessoal (não inclui proventos)."""

    __tablename__ = "lancamentos"
    __table_args__ = (
        CheckConstraint(_positivo("valor"), name="valor"),
        CheckConstraint("length(trim(descricao)) > 0", name="descricao_preenchida"),
        Index("ix_lancamentos_data", "data"),
        Index("ix_lancamentos_categoria", "categoria_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoLancamento] = mapped_column(enum_texto(TipoLancamento, "tipo_lancamento"))
    data: Mapped[date]
    descricao: Mapped[str] = mapped_column(String(200))
    valor: Mapped[Decimal]
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="RESTRICT")
    )
    observacao: Mapped[str | None] = mapped_column(String(500))
    criado_em: Mapped[datetime] = mapped_column(default=agora_utc)

    categoria: Mapped[Categoria | None] = relationship()


class Configuracao(Base):
    """Preferências do app em chave/valor (valor JSON)."""

    __tablename__ = "configuracoes"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[Any] = mapped_column(JSON)
    atualizado_em: Mapped[datetime] = mapped_column(default=agora_utc, onupdate=agora_utc)
