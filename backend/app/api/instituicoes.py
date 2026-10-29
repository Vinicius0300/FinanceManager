"""Instituições e caixa: CRUD de instituições, contas por moeda, depósitos/saques e extrato."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, status

from app.api.dependencias import (
    PROTEGIDO,
    Deslocamento,
    HojeDep,
    Limite,
    SessaoDep,
    respostas,
)
from app.api.schemas import Modelo, Numero, Pagina
from app.domain.enums import TipoInstituicao, TipoMovimento
from app.repositories import modelos as m
from app.services import cadastros, caixa

router = APIRouter(prefix="/api", tags=["instituições e caixa"], dependencies=PROTEGIDO)


class InstituicaoEntrada(Modelo):
    nome: str
    tipo: TipoInstituicao


class InstituicaoSaida(Modelo):
    id: int
    nome: str
    tipo: TipoInstituicao
    criado_em: datetime


class ContaSaida(Modelo):
    id: int
    instituicao_id: int
    instituicao_nome: str
    moeda: str
    saldo: Numero


class MovimentoEntrada(Modelo):
    instituicao_id: int
    moeda: str = "BRL"
    tipo: Literal["deposito", "saque"]
    data: date
    valor: Numero
    descricao: str | None = None


class AlteracaoValor(Modelo):
    valor: Numero


class MovimentoSaida(Modelo):
    id: int
    conta_id: int
    transacao_id: int | None
    tipo: TipoMovimento
    data: date
    valor: Numero
    descricao: str | None
    criado_em: datetime


class ExtratoSaida(Pagina[MovimentoSaida]):
    instituicao_id: int
    moeda: str
    saldo_final: Numero


def _instituicao(instituicao: m.Instituicao) -> InstituicaoSaida:
    return InstituicaoSaida(
        id=instituicao.id,
        nome=instituicao.nome,
        tipo=instituicao.tipo,
        criado_em=instituicao.criado_em,
    )


def _movimento(movimento: m.MovimentoConta) -> MovimentoSaida:
    return MovimentoSaida(
        id=movimento.id,
        conta_id=movimento.conta_id,
        transacao_id=movimento.transacao_id,
        tipo=movimento.tipo,
        data=movimento.data,
        valor=movimento.valor,
        descricao=movimento.descricao,
        criado_em=movimento.criado_em,
    )


def _contas(itens: list[caixa.ContaComSaldo]) -> list[ContaSaida]:
    return [
        ContaSaida(
            id=item.conta.id,
            instituicao_id=item.conta.instituicao_id,
            instituicao_nome=item.conta.instituicao.nome,
            moeda=item.conta.moeda,
            saldo=item.saldo,
        )
        for item in itens
    ]


@router.get(
    "/instituicoes",
    response_model=list[InstituicaoSaida],
    summary="Lista as instituições",
    responses=respostas(),
)
def listar_instituicoes(sessao: SessaoDep) -> list[InstituicaoSaida]:
    return [_instituicao(i) for i in cadastros.listar_instituicoes(sessao)]


@router.post(
    "/instituicoes",
    response_model=InstituicaoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma instituição",
    responses=respostas(409, 422),
)
def criar_instituicao(dados: InstituicaoEntrada, sessao: SessaoDep) -> InstituicaoSaida:
    return _instituicao(cadastros.criar_instituicao(sessao, dados.nome, dados.tipo))


@router.get(
    "/instituicoes/{instituicao_id}",
    response_model=InstituicaoSaida,
    summary="Detalha uma instituição",
    responses=respostas(404),
)
def obter_instituicao(instituicao_id: int, sessao: SessaoDep) -> InstituicaoSaida:
    return _instituicao(cadastros.obter_instituicao(sessao, instituicao_id))


@router.put(
    "/instituicoes/{instituicao_id}",
    response_model=InstituicaoSaida,
    summary="Altera nome e tipo de uma instituição",
    responses=respostas(404, 409, 422),
)
def editar_instituicao(
    instituicao_id: int, dados: InstituicaoEntrada, sessao: SessaoDep
) -> InstituicaoSaida:
    return _instituicao(
        cadastros.editar_instituicao(sessao, instituicao_id, dados.nome, dados.tipo)
    )


@router.delete(
    "/instituicoes/{instituicao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui uma instituição sem transações nem movimentos",
    responses=respostas(404, 422),
)
def excluir_instituicao(instituicao_id: int, sessao: SessaoDep) -> None:
    cadastros.excluir_instituicao(sessao, instituicao_id)


@router.get(
    "/contas",
    response_model=list[ContaSaida],
    summary="Contas correntes (por instituição e moeda) com saldo",
    description="Saldo ao fim de `data` (padrão: hoje). Filtra por instituição se informada.",
    responses=respostas(),
)
def listar_contas(
    sessao: SessaoDep,
    hoje: HojeDep,
    instituicao_id: int | None = None,
    data: date | None = None,
) -> list[ContaSaida]:
    return _contas(caixa.listar_contas(sessao, data or hoje, instituicao_id))


@router.get(
    "/instituicoes/{instituicao_id}/extrato",
    response_model=ExtratoSaida,
    summary="Extrato da conta corrente de uma instituição numa moeda",
    responses=respostas(404, 422),
)
def obter_extrato(
    instituicao_id: int,
    sessao: SessaoDep,
    hoje: HojeDep,
    moeda: str = "BRL",
    inicio: date | None = None,
    fim: date | None = None,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> ExtratoSaida:
    resultado = caixa.extrato(
        sessao,
        instituicao_id,
        moeda,
        inicio=inicio,
        fim=fim,
        hoje=hoje,
        limite=limite,
        deslocamento=deslocamento,
    )
    return ExtratoSaida(
        itens=[_movimento(x) for x in resultado.itens],
        total=resultado.total,
        limite=limite,
        deslocamento=deslocamento,
        instituicao_id=instituicao_id,
        moeda=resultado.conta.moeda,
        saldo_final=resultado.saldo_final,
    )


@router.post(
    "/movimentos",
    response_model=MovimentoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Registra um depósito ou saque",
    description="Saque maior que o saldo disponível é recusado (422, `saldo_insuficiente`).",
    responses=respostas(404, 422),
)
def criar_movimento(dados: MovimentoEntrada, sessao: SessaoDep) -> MovimentoSaida:
    movimento = caixa.registrar_movimento_manual(
        sessao,
        caixa.NovoMovimentoManual(
            instituicao_id=dados.instituicao_id,
            moeda=dados.moeda,
            tipo=TipoMovimento(dados.tipo),
            data=dados.data,
            valor=dados.valor,
            descricao=dados.descricao,
        ),
    )
    return _movimento(movimento)


@router.patch(
    "/movimentos/{movimento_id}",
    response_model=MovimentoSaida,
    summary="Altera o valor de um depósito, saque ou ajuste de saldo",
    responses=respostas(404, 422),
)
def alterar_valor_movimento(
    movimento_id: int, dados: AlteracaoValor, sessao: SessaoDep
) -> MovimentoSaida:
    return _movimento(caixa.alterar_valor_movimento(sessao, movimento_id, dados.valor))


@router.delete(
    "/movimentos/{movimento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um depósito, saque ou ajuste de saldo",
    responses=respostas(404, 422),
)
def excluir_movimento(movimento_id: int, sessao: SessaoDep) -> None:
    caixa.excluir_movimento(sessao, movimento_id)
