"""Casos de uso de transferências entre instituições (mesma moeda nas duas pontas).

Uma transferência grava ``transferencia_saida`` (valor) no caixa da origem e
``transferencia_entrada`` (valor) no do destino. Tarifa > 0 (só em BRL) vira uma
**despesa** na origem, ligada à transferência: gravada, editada e excluída junto com ela,
e só para leitura em Receitas e Despesas.

Saldo: a origem precisa cobrir valor + tarifa, e nunca há ajuste (**recusa**, 422, como
o saque). Editar ou excluir uma transferência que deixaria qualquer caixa negativo
(em geral o do destino) também é recusado.

Ex.: 1.000 do Nubank (caixa 1.500) para o Itaú com tarifa de 10 → Nubank 490 (saída de
1.000 + despesa de 10), Itaú +1.000. Com 1.005 no Nubank é recusado (faltam 5).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.conta_corrente import LancamentoCaixa, movimentos_da_transferencia
from app.domain.enums import TipoLancamento, TipoMovimento
from app.domain.erros import NaoEncontradoError, exigir
from app.domain.moedas import validar_moeda
from app.domain.numeros import CASAS_MOEDA, ZERO, exigir_casas
from app.domain.textos import texto_opcional
from app.repositories import modelos as m
from app.repositories.contas import RepositorioMovimentos
from app.repositories.lancamentos import RepositorioLancamentos
from app.repositories.transferencias import RepositorioTransferencias
from app.services.cadastros import obter_instituicao
from app.services.caixa import (
    exigir_sem_deficit,
    lancamentos,
    movimentos_da_conta,
    obter_conta,
    obter_ou_criar_conta,
)
from app.services.financeiro import (
    MOEDA_LANCAMENTOS,
    gravar_movimentos_do_lancamento,
    validar_categoria,
)

TAMANHO_DESCRICAO = 300
MENSAGEM_TARIFA_USD = (
    "Tarifa só em transferências em reais. Em outra moeda, lance a tarifa como saque."
)


@dataclass(frozen=True)
class NovaTransferencia:
    data: date
    origem_id: int
    destino_id: int
    valor: Decimal
    moeda: str = "BRL"
    tarifa: Decimal = ZERO
    categoria_tarifa_id: int | None = None
    descricao: str | None = None


@dataclass(frozen=True)
class _Validada:
    dados: NovaTransferencia
    moeda: str
    descricao: str | None
    origem: m.Instituicao
    destino: m.Instituicao


def _validar(sessao: Session, dados: NovaTransferencia) -> _Validada:
    exigir(
        dados.origem_id != dados.destino_id,
        "destino_id",
        "Escolha uma instituição de destino diferente da origem.",
    )
    origem = obter_instituicao(sessao, dados.origem_id)
    destino = obter_instituicao(sessao, dados.destino_id)
    moeda = validar_moeda(dados.moeda)
    exigir(dados.valor > ZERO, "valor", "O valor deve ser maior que zero.")
    exigir_casas(dados.valor, CASAS_MOEDA, "valor")
    exigir(dados.tarifa >= ZERO, "tarifa", "A tarifa não pode ser negativa.")
    exigir_casas(dados.tarifa, CASAS_MOEDA, "tarifa")
    exigir(dados.tarifa == ZERO or moeda == MOEDA_LANCAMENTOS, "tarifa", MENSAGEM_TARIFA_USD)
    if dados.tarifa > ZERO:
        validar_categoria(sessao, dados.categoria_tarifa_id, TipoLancamento.DESPESA)
    descricao = texto_opcional(dados.descricao, "descricao", TAMANHO_DESCRICAO)
    return _Validada(dados, moeda, descricao, origem, destino)


def _movimentos_sem(
    sessao: Session, instituicao_id: int, moeda: str, transferencia: m.Transferencia | None
) -> list[LancamentoCaixa]:
    """Movimentos da conta, sem os da transferência e os da tarifa dela."""
    conta = obter_conta(sessao, instituicao_id, moeda)
    if conta is None:
        return []
    tarifa_id = (
        transferencia.tarifa_lancamento.id
        if transferencia is not None and transferencia.tarifa_lancamento is not None
        else None
    )
    return lancamentos(
        x
        for x in movimentos_da_conta(sessao, conta.id)
        if transferencia is None
        or (
            x.transferencia_id != transferencia.id
            and (tarifa_id is None or x.lancamento_id != tarifa_id)
        )
    )


def _efeitos(v: _Validada) -> dict[int, list[LancamentoCaixa]]:
    """Efeito no caixa de cada instituição (origem: valor + tarifa; destino: valor)."""
    efeito = movimentos_da_transferencia(v.dados.valor, v.dados.tarifa)
    origem = [LancamentoCaixa(v.dados.data, -efeito.saida)]
    if efeito.tarifa > ZERO:
        origem.append(LancamentoCaixa(v.dados.data, -efeito.tarifa))
    return {
        v.dados.origem_id: origem,
        v.dados.destino_id: [LancamentoCaixa(v.dados.data, efeito.entrada)],
    }


def _exigir_saldos(
    sessao: Session,
    contas: set[tuple[int, str]],
    efeitos: dict[tuple[int, str], list[LancamentoCaixa]],
    original: m.Transferencia | None,
    a_partir_de: date,
    acao: str,
) -> None:
    """Recusa (422) se alguma conta afetada ficar negativa em algum dia."""
    for instituicao_id, moeda in sorted(contas):
        simulado = [
            *_movimentos_sem(sessao, instituicao_id, moeda, original),
            *efeitos.get((instituicao_id, moeda), []),
        ]
        if not any(x.valor < ZERO for x in simulado):
            continue
        conta = obter_ou_criar_conta(sessao, instituicao_id, moeda)
        exigir_sem_deficit(conta, simulado, a_partir_de, acao)


def _gravar(sessao: Session, transferencia: m.Transferencia, v: _Validada) -> None:
    """Cria os movimentos e, com tarifa, a despesa ligada (na conta BRL da origem)."""
    efeito = movimentos_da_transferencia(v.dados.valor, v.dados.tarifa)
    movimentos = RepositorioMovimentos(sessao)
    for instituicao_id, tipo, valor in (
        (v.dados.origem_id, TipoMovimento.TRANSFERENCIA_SAIDA, efeito.saida),
        (v.dados.destino_id, TipoMovimento.TRANSFERENCIA_ENTRADA, efeito.entrada),
    ):
        conta = obter_ou_criar_conta(sessao, instituicao_id, v.moeda)
        movimentos.adicionar(
            m.MovimentoConta(
                conta_id=conta.id,
                transferencia_id=transferencia.id,
                tipo=tipo,
                data=v.dados.data,
                valor=valor,
                descricao=v.descricao,
            )
        )
    if efeito.tarifa > ZERO:
        tarifa = RepositorioLancamentos(sessao).adicionar(
            m.Lancamento(
                tipo=TipoLancamento.DESPESA,
                data=v.dados.data,
                descricao=f"Tarifa da transferência para {v.destino.nome}",
                valor=efeito.tarifa,
                instituicao_id=v.dados.origem_id,
                categoria_id=v.dados.categoria_tarifa_id,
                transferencia_id=transferencia.id,
            )
        )
        gravar_movimentos_do_lancamento(sessao, tarifa)
    sessao.expire(transferencia, ["movimentos", "tarifa_lancamento"])


def _efeitos_por_conta(v: _Validada) -> dict[tuple[int, str], list[LancamentoCaixa]]:
    return {(inst, v.moeda): efeitos for inst, efeitos in _efeitos(v).items()}


def registrar_transferencia(sessao: Session, dados: NovaTransferencia) -> m.Transferencia:
    v = _validar(sessao, dados)
    efeitos = _efeitos_por_conta(v)
    _exigir_saldos(sessao, set(efeitos), efeitos, None, dados.data, "Esta transferência")
    transferencia = RepositorioTransferencias(sessao).adicionar(
        m.Transferencia(
            data=dados.data,
            origem_id=dados.origem_id,
            destino_id=dados.destino_id,
            moeda=v.moeda,
            valor=dados.valor,
            tarifa=dados.tarifa,
            descricao=v.descricao,
        )
    )
    _gravar(sessao, transferencia, v)
    return transferencia


def obter_transferencia(sessao: Session, transferencia_id: int) -> m.Transferencia:
    transferencia = RepositorioTransferencias(sessao).obter(transferencia_id)
    if transferencia is None:
        raise NaoEncontradoError(f"Transferência {transferencia_id} não encontrada.")
    return transferencia


def _contas_da(transferencia: m.Transferencia) -> set[tuple[int, str]]:
    return {
        (transferencia.origem_id, transferencia.moeda),
        (transferencia.destino_id, transferencia.moeda),
    }


def _remover_vinculados(sessao: Session, transferencia: m.Transferencia) -> None:
    movimentos = RepositorioMovimentos(sessao)
    for movimento in movimentos.da_transferencia(transferencia.id):
        movimentos.remover(movimento)
    if transferencia.tarifa_lancamento is not None:
        RepositorioLancamentos(sessao).remover(transferencia.tarifa_lancamento)
    sessao.expire(transferencia, ["movimentos", "tarifa_lancamento"])


def editar_transferencia(
    sessao: Session, transferencia_id: int, dados: NovaTransferencia
) -> m.Transferencia:
    """Substitui a transferência (movimentos e tarifa refeitos); recusa se faltar saldo."""
    original = obter_transferencia(sessao, transferencia_id)
    v = _validar(sessao, dados)
    efeitos = _efeitos_por_conta(v)
    _exigir_saldos(
        sessao,
        _contas_da(original) | set(efeitos),
        efeitos,
        original,
        min(original.data, dados.data),
        "Alterar esta transferência",
    )
    _remover_vinculados(sessao, original)
    original.data = dados.data
    original.origem_id = dados.origem_id
    original.destino_id = dados.destino_id
    original.moeda = v.moeda
    original.valor = dados.valor
    original.tarifa = dados.tarifa
    original.descricao = v.descricao
    sessao.flush()
    sessao.expire(original, ["origem", "destino"])
    _gravar(sessao, original, v)
    return original


def excluir_transferencia(sessao: Session, transferencia_id: int) -> None:
    """Exclui a transferência, os movimentos e a tarifa (recusa se algum caixa ficar < 0)."""
    transferencia = obter_transferencia(sessao, transferencia_id)
    _exigir_saldos(
        sessao,
        _contas_da(transferencia),
        {},
        transferencia,
        transferencia.data,
        "Excluir esta transferência",
    )
    RepositorioTransferencias(sessao).remover(transferencia)


def listar_transferencias(
    sessao: Session,
    *,
    instituicao_id: int | None = None,
    inicio: date | None = None,
    fim: date | None = None,
) -> Sequence[m.Transferencia]:
    return RepositorioTransferencias(sessao).filtradas(
        instituicao_id=instituicao_id, inicio=inicio, fim=fim
    )
