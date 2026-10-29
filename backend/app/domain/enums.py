"""Enumerações do domínio (valores persistidos no banco: não renomeie sem migração)."""

from enum import StrEnum


class TipoInstituicao(StrEnum):
    """Onde o dinheiro está alocado."""

    CORRETORA = "corretora"
    BANCO = "banco"
    OUTRO = "outro"


class TipoTransacao(StrEnum):
    COMPRA = "compra"
    VENDA = "venda"
    APORTE = "aporte"
    RESGATE = "resgate"
    PROVENTO = "provento"


class SubtipoProvento(StrEnum):
    DIVIDENDO = "dividendo"
    JCP = "jcp"
    RENDIMENTO = "rendimento"
    OUTRO = "outro"


class TipoEvento(StrEnum):
    """Eventos corporativos. Proporção ``de:para`` (ex.: desdobramento 1:2)."""

    DESDOBRAMENTO = "desdobramento"
    GRUPAMENTO = "grupamento"
    BONIFICACAO = "bonificacao"


class TipoMovimento(StrEnum):
    """Movimentos da conta corrente de uma instituição.

    - ``deposito``/``saque``: manuais.
    - ``debito_compra``: compra ou aporte (automático, ligado à transação).
    - ``credito_venda``: venda ou resgate (automático, ligado à transação).
    - ``credito_provento``: provento líquido (automático, ligado à transação).
    - ``ajuste_saldo``: depósito não informado, criado quando uma compra/aporte
      excede o saldo e o usuário opta por não atualizar os valores.
    """

    DEPOSITO = "deposito"
    SAQUE = "saque"
    DEBITO_COMPRA = "debito_compra"
    CREDITO_VENDA = "credito_venda"
    CREDITO_PROVENTO = "credito_provento"
    AJUSTE_SALDO = "ajuste_saldo"


MOVIMENTOS_MANUAIS = frozenset({TipoMovimento.DEPOSITO, TipoMovimento.SAQUE})
MOVIMENTOS_DE_TRANSACAO = frozenset(
    {
        TipoMovimento.DEBITO_COMPRA,
        TipoMovimento.CREDITO_VENDA,
        TipoMovimento.CREDITO_PROVENTO,
    }
)
MOVIMENTOS_DE_SAIDA = frozenset({TipoMovimento.SAQUE, TipoMovimento.DEBITO_COMPRA})


class OrigemPreco(StrEnum):
    AUTOMATICO = "automatico"
    MANUAL = "manual"
    CALCULADO = "calculado"


class TipoIndicador(StrEnum):
    """Unidades: Selic e CDI em % ao ano; IPCA em % no mês; câmbio em BRL por unidade."""

    SELIC = "selic"
    CDI = "cdi"
    IPCA = "ipca"
    CAMBIO = "cambio"


class TipoLancamento(StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"


class Indexador(StrEnum):
    PRE = "pre"
    CDI = "cdi"
    IPCA = "ipca"
