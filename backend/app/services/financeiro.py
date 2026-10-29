"""Casos de uso de receitas e despesas (orçamento pessoal)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.enums import TipoLancamento
from app.domain.erros import ConflitoError, NaoEncontradoError, OperacaoNaoPermitidaError, exigir
from app.domain.lancamentos import (
    Lancamento,
    ResumoMensal,
    TotalCategoria,
    resumo_mensal,
    totais_por_categoria,
    validar_mes,
)
from app.domain.numeros import CASAS_MOEDA, ZERO, exigir_casas
from app.repositories import modelos as m
from app.repositories.lancamentos import RepositorioCategorias, RepositorioLancamentos

TAMANHO_NOME_CATEGORIA = 80
TAMANHO_DESCRICAO = 200
TAMANHO_OBSERVACAO = 500


def criar_categoria(sessao: Session, nome: str, tipo: TipoLancamento) -> m.Categoria:
    nome_limpo = nome.strip()
    exigir(bool(nome_limpo), "nome", "Informe o nome da categoria.")
    exigir(
        len(nome_limpo) <= TAMANHO_NOME_CATEGORIA,
        "nome",
        f"Use no máximo {TAMANHO_NOME_CATEGORIA} caracteres.",
    )
    repositorio = RepositorioCategorias(sessao)
    if repositorio.por_nome(nome_limpo, tipo) is not None:
        raise ConflitoError(f"Já existe a categoria {nome_limpo!r} de {tipo.value}.")
    return repositorio.adicionar(m.Categoria(nome=nome_limpo, tipo=tipo))


def excluir_categoria(sessao: Session, categoria_id: int) -> None:
    repositorio = RepositorioCategorias(sessao)
    categoria = repositorio.obter(categoria_id)
    if categoria is None:
        raise NaoEncontradoError(f"Categoria {categoria_id} não encontrada.")
    if RepositorioLancamentos(sessao).existe_na_categoria(categoria_id):
        raise OperacaoNaoPermitidaError(
            "A categoria tem lançamentos. Mova-os para outra categoria antes de excluir."
        )
    repositorio.remover(categoria)


@dataclass(frozen=True)
class NovoLancamento:
    tipo: TipoLancamento
    data: date
    descricao: str
    valor: Decimal
    categoria_id: int | None = None
    observacao: str | None = None


def registrar_lancamento(sessao: Session, dados: NovoLancamento) -> m.Lancamento:
    descricao = dados.descricao.strip()
    exigir(bool(descricao), "descricao", "Informe a descrição.")
    exigir(
        len(descricao) <= TAMANHO_DESCRICAO,
        "descricao",
        f"Use no máximo {TAMANHO_DESCRICAO} caracteres.",
    )
    exigir(dados.valor > ZERO, "valor", "O valor deve ser maior que zero.")
    exigir_casas(dados.valor, CASAS_MOEDA, "valor")
    observacao = dados.observacao.strip() if dados.observacao and dados.observacao.strip() else None
    exigir(
        observacao is None or len(observacao) <= TAMANHO_OBSERVACAO,
        "observacao",
        f"Use no máximo {TAMANHO_OBSERVACAO} caracteres.",
    )
    if dados.categoria_id is not None:
        categoria = RepositorioCategorias(sessao).obter(dados.categoria_id)
        if categoria is None:
            raise NaoEncontradoError(f"Categoria {dados.categoria_id} não encontrada.")
        exigir(
            categoria.tipo is dados.tipo,
            "categoria_id",
            f"A categoria {categoria.nome!r} é de {categoria.tipo.value}, "
            f"não de {dados.tipo.value}.",
        )
    return RepositorioLancamentos(sessao).adicionar(
        m.Lancamento(
            tipo=dados.tipo,
            data=dados.data,
            descricao=descricao,
            valor=dados.valor,
            categoria_id=dados.categoria_id,
            observacao=observacao,
        )
    )


def excluir_lancamento(sessao: Session, lancamento_id: int) -> None:
    repositorio = RepositorioLancamentos(sessao)
    lancamento = repositorio.obter(lancamento_id)
    if lancamento is None:
        raise NaoEncontradoError(f"Lançamento {lancamento_id} não encontrado.")
    repositorio.remover(lancamento)


def _do_mes(sessao: Session, ano: int, mes: int) -> list[Lancamento]:
    validar_mes(ano, mes)
    return [
        Lancamento(
            data=registro.data,
            tipo=registro.tipo,
            valor=registro.valor,
            categoria_id=registro.categoria_id,
            categoria_nome=registro.categoria.nome if registro.categoria else None,
        )
        for registro in RepositorioLancamentos(sessao).do_mes(ano, mes)
    ]


def obter_resumo_mensal(sessao: Session, ano: int, mes: int) -> ResumoMensal:
    return resumo_mensal(_do_mes(sessao, ano, mes), ano, mes)


def obter_totais_por_categoria(sessao: Session, ano: int, mes: int) -> list[TotalCategoria]:
    return totais_por_categoria(_do_mes(sessao, ano, mes), ano, mes)
