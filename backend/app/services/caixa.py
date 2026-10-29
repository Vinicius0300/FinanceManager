"""Casos de uso da conta corrente de cada instituição (caixa).

Depósito e saque são manuais; os movimentos de compra/venda/provento são criados por
``services/transacoes.py``. O saldo nunca fica negativo (ver ``domain/conta_corrente.py``).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.conta_corrente import LancamentoCaixa, deficit, saldo_em, valor_com_sinal
from app.domain.enums import MOVIMENTOS_MANUAIS, TipoMovimento
from app.domain.erros import (
    NaoEncontradoError,
    OperacaoNaoPermitidaError,
    SaldoInsuficienteError,
    exigir,
)
from app.domain.moedas import validar_moeda
from app.domain.numeros import ZERO, arredondar_moeda, formatar_numero
from app.domain.tempo import formatar_data
from app.repositories import modelos as m
from app.repositories.contas import RepositorioContas, RepositorioMovimentos
from app.services.cadastros import obter_instituicao

DESCRICAO_AJUSTE = "Ajuste de saldo (depósito não informado)"
TAMANHO_DESCRICAO = 300
TIPOS_EDITAVEIS = MOVIMENTOS_MANUAIS | {TipoMovimento.AJUSTE_SALDO}


def lancamentos(movimentos: Iterable[m.MovimentoConta]) -> list[LancamentoCaixa]:
    return [LancamentoCaixa(mov.data, valor_com_sinal(mov.tipo, mov.valor)) for mov in movimentos]


def obter_conta(sessao: Session, instituicao_id: int, moeda: str) -> m.ContaCorrente | None:
    return RepositorioContas(sessao).da_instituicao(instituicao_id, validar_moeda(moeda))


def obter_ou_criar_conta(sessao: Session, instituicao_id: int, moeda: str) -> m.ContaCorrente:
    obter_instituicao(sessao, instituicao_id)
    moeda = validar_moeda(moeda)
    conta = obter_conta(sessao, instituicao_id, moeda)
    if conta is None:
        conta = RepositorioContas(sessao).adicionar(
            m.ContaCorrente(instituicao_id=instituicao_id, moeda=moeda)
        )
    return conta


def movimentos_da_conta(
    sessao: Session, conta_id: int, ate: date | None = None
) -> list[m.MovimentoConta]:
    return list(RepositorioMovimentos(sessao).da_conta(conta_id, ate))


def saldo(sessao: Session, instituicao_id: int, moeda: str, dia: date) -> Decimal:
    """Saldo ao fim de ``dia`` (zero se a conta ainda não existe)."""
    conta = obter_conta(sessao, instituicao_id, moeda)
    if conta is None:
        return ZERO
    return saldo_em(lancamentos(movimentos_da_conta(sessao, conta.id)), dia)


def _nome_conta(conta: m.ContaCorrente) -> str:
    return f"{conta.instituicao.nome} ({conta.moeda})"


def _exigir_sem_deficit(
    conta: m.ContaCorrente, movimentos: list[LancamentoCaixa], a_partir_de: date, acao: str
) -> None:
    falta = deficit(movimentos, a_partir_de)
    if falta > ZERO:
        raise SaldoInsuficienteError(
            f"{acao} deixaria a conta {_nome_conta(conta)} negativa em "
            f"R$ {formatar_numero(arredondar_moeda(falta))} a partir de "
            f"{formatar_data(a_partir_de)}."
        )


def _descricao(descricao: str | None) -> str | None:
    if descricao is None or not descricao.strip():
        return None
    texto = descricao.strip()
    exigir(
        len(texto) <= TAMANHO_DESCRICAO,
        "descricao",
        f"Use no máximo {TAMANHO_DESCRICAO} caracteres.",
    )
    return texto


@dataclass(frozen=True)
class NovoMovimentoManual:
    instituicao_id: int
    moeda: str
    tipo: TipoMovimento  # deposito ou saque
    data: date
    valor: Decimal
    descricao: str | None = None


def registrar_movimento_manual(sessao: Session, dados: NovoMovimentoManual) -> m.MovimentoConta:
    """Depósito ou saque. Saque maior que o saldo disponível é recusado."""
    if dados.tipo not in MOVIMENTOS_MANUAIS:
        raise OperacaoNaoPermitidaError("Só depósitos e saques podem ser lançados manualmente.")
    exigir(dados.valor > ZERO, "valor", "O valor deve ser maior que zero.")
    descricao = _descricao(dados.descricao)
    conta = obter_ou_criar_conta(sessao, dados.instituicao_id, dados.moeda)
    if dados.tipo is TipoMovimento.SAQUE:
        existentes = lancamentos(movimentos_da_conta(sessao, conta.id))
        novo = LancamentoCaixa(dados.data, -dados.valor)
        _exigir_sem_deficit(conta, [*existentes, novo], dados.data, "Este saque")
    return RepositorioMovimentos(sessao).adicionar(
        m.MovimentoConta(
            conta_id=conta.id,
            tipo=dados.tipo,
            data=dados.data,
            valor=dados.valor,
            descricao=descricao,
        )
    )


def _obter_editavel(sessao: Session, movimento_id: int) -> m.MovimentoConta:
    movimento = RepositorioMovimentos(sessao).obter(movimento_id)
    if movimento is None:
        raise NaoEncontradoError(f"Movimento {movimento_id} não encontrado.")
    if movimento.tipo not in TIPOS_EDITAVEIS:
        raise OperacaoNaoPermitidaError(
            "Este movimento foi gerado por uma transação: altere ou exclua a transação."
        )
    return movimento


def alterar_valor_movimento(sessao: Session, movimento_id: int, valor: Decimal) -> m.MovimentoConta:
    """Altera o valor de um depósito, saque ou ajuste de saldo, mantendo o saldo ≥ 0."""
    exigir(valor > ZERO, "valor", "O valor deve ser maior que zero.")
    movimento = _obter_editavel(sessao, movimento_id)
    outros = [x for x in movimentos_da_conta(sessao, movimento.conta_id) if x.id != movimento.id]
    simulado = [
        *lancamentos(outros),
        LancamentoCaixa(movimento.data, valor_com_sinal(movimento.tipo, valor)),
    ]
    _exigir_sem_deficit(movimento.conta, simulado, movimento.data, "Este novo valor")
    movimento.valor = valor
    sessao.flush()
    return movimento


def excluir_movimento(sessao: Session, movimento_id: int) -> None:
    """Exclui depósito, saque ou ajuste de saldo, desde que o saldo continue ≥ 0."""
    movimento = _obter_editavel(sessao, movimento_id)
    outros = [x for x in movimentos_da_conta(sessao, movimento.conta_id) if x.id != movimento.id]
    _exigir_sem_deficit(
        movimento.conta, lancamentos(outros), movimento.data, "Excluir este movimento"
    )
    RepositorioMovimentos(sessao).remover(movimento)
