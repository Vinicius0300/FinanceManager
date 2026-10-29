"""Receitas e despesas: categorias, lançamentos e resumo mensal (proventos não entram)."""

from datetime import date, datetime

from fastapi import APIRouter, Query, status

from app.api.dependencias import PROTEGIDO, Deslocamento, Limite, SessaoDep, respostas
from app.api.schemas import Modelo, Numero, Pagina
from app.domain.enums import TipoLancamento
from app.domain.numeros import arredondar, arredondar_moeda
from app.repositories import modelos as m
from app.services import financeiro

router = APIRouter(prefix="/api", tags=["receitas e despesas"], dependencies=PROTEGIDO)

CASAS_PERCENTUAL_SAIDA = 8


class CategoriaEntrada(Modelo):
    nome: str
    tipo: TipoLancamento


class CategoriaRenomear(Modelo):
    nome: str


class CategoriaSaida(Modelo):
    id: int
    nome: str
    tipo: TipoLancamento


class LancamentoEntrada(Modelo):
    tipo: TipoLancamento
    data: date
    descricao: str
    valor: Numero
    categoria_id: int | None = None
    observacao: str | None = None


class LancamentoSaida(Modelo):
    id: int
    tipo: TipoLancamento
    data: date
    descricao: str
    valor: Numero
    categoria_id: int | None
    categoria_nome: str | None
    observacao: str | None
    criado_em: datetime


class TotalCategoriaSaida(Modelo):
    tipo: TipoLancamento
    categoria_id: int | None
    categoria_nome: str
    total: Numero
    percentual: Numero  # razão sobre o total do tipo no mês


class ResumoMensalSaida(Modelo):
    ano: int
    mes: int
    total_receitas: Numero
    total_despesas: Numero
    saldo: Numero
    por_categoria: list[TotalCategoriaSaida]


def _categoria(categoria: m.Categoria) -> CategoriaSaida:
    return CategoriaSaida(id=categoria.id, nome=categoria.nome, tipo=categoria.tipo)


def _lancamento(lancamento: m.Lancamento) -> LancamentoSaida:
    return LancamentoSaida(
        id=lancamento.id,
        tipo=lancamento.tipo,
        data=lancamento.data,
        descricao=lancamento.descricao,
        valor=lancamento.valor,
        categoria_id=lancamento.categoria_id,
        categoria_nome=lancamento.categoria.nome if lancamento.categoria else None,
        observacao=lancamento.observacao,
        criado_em=lancamento.criado_em,
    )


def _novo(dados: LancamentoEntrada) -> financeiro.NovoLancamento:
    return financeiro.NovoLancamento(
        tipo=dados.tipo,
        data=dados.data,
        descricao=dados.descricao,
        valor=dados.valor,
        categoria_id=dados.categoria_id,
        observacao=dados.observacao,
    )


@router.get(
    "/categorias",
    response_model=list[CategoriaSaida],
    summary="Lista as categorias (opcionalmente de um tipo)",
    responses=respostas(),
)
def listar_categorias(
    sessao: SessaoDep, tipo: TipoLancamento | None = None
) -> list[CategoriaSaida]:
    return [_categoria(c) for c in financeiro.listar_categorias(sessao, tipo)]


@router.post(
    "/categorias",
    response_model=CategoriaSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma categoria",
    responses=respostas(409, 422),
)
def criar_categoria(dados: CategoriaEntrada, sessao: SessaoDep) -> CategoriaSaida:
    return _categoria(financeiro.criar_categoria(sessao, dados.nome, dados.tipo))


@router.put(
    "/categorias/{categoria_id}",
    response_model=CategoriaSaida,
    summary="Renomeia uma categoria",
    responses=respostas(404, 409, 422),
)
def renomear_categoria(
    categoria_id: int, dados: CategoriaRenomear, sessao: SessaoDep
) -> CategoriaSaida:
    return _categoria(financeiro.renomear_categoria(sessao, categoria_id, dados.nome))


@router.delete(
    "/categorias/{categoria_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui uma categoria sem lançamentos",
    responses=respostas(404, 422),
)
def excluir_categoria(categoria_id: int, sessao: SessaoDep) -> None:
    financeiro.excluir_categoria(sessao, categoria_id)


@router.get(
    "/lancamentos",
    response_model=Pagina[LancamentoSaida],
    summary="Lista lançamentos com filtros (mais recentes primeiro)",
    responses=respostas(),
)
def listar_lancamentos(
    sessao: SessaoDep,
    tipo: TipoLancamento | None = None,
    categoria_id: int | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> Pagina[LancamentoSaida]:
    pagina = financeiro.listar_lancamentos(
        sessao,
        tipo=tipo,
        categoria_id=categoria_id,
        inicio=inicio,
        fim=fim,
        limite=limite,
        deslocamento=deslocamento,
    )
    return Pagina[LancamentoSaida](
        itens=[_lancamento(x) for x in pagina.itens],
        total=pagina.total,
        limite=limite,
        deslocamento=deslocamento,
    )


@router.post(
    "/lancamentos",
    response_model=LancamentoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma receita ou despesa",
    responses=respostas(404, 422),
)
def criar_lancamento(dados: LancamentoEntrada, sessao: SessaoDep) -> LancamentoSaida:
    return _lancamento(financeiro.registrar_lancamento(sessao, _novo(dados)))


@router.get(
    "/lancamentos/{lancamento_id}",
    response_model=LancamentoSaida,
    summary="Detalha um lançamento",
    responses=respostas(404),
)
def obter_lancamento(lancamento_id: int, sessao: SessaoDep) -> LancamentoSaida:
    return _lancamento(financeiro.obter_lancamento(sessao, lancamento_id))


@router.put(
    "/lancamentos/{lancamento_id}",
    response_model=LancamentoSaida,
    summary="Altera um lançamento",
    responses=respostas(404, 422),
)
def editar_lancamento(
    lancamento_id: int, dados: LancamentoEntrada, sessao: SessaoDep
) -> LancamentoSaida:
    return _lancamento(financeiro.editar_lancamento(sessao, lancamento_id, _novo(dados)))


@router.delete(
    "/lancamentos/{lancamento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um lançamento",
    responses=respostas(404),
)
def excluir_lancamento(lancamento_id: int, sessao: SessaoDep) -> None:
    financeiro.excluir_lancamento(sessao, lancamento_id)


@router.get(
    "/resumo-mensal",
    response_model=ResumoMensalSaida,
    summary="Receitas, despesas, saldo e totais por categoria do mês",
    responses=respostas(422),
)
def obter_resumo_mensal(
    sessao: SessaoDep,
    ano: int = Query(ge=1900, le=9999),
    mes: int = Query(ge=1, le=12),
) -> ResumoMensalSaida:
    resumo = financeiro.obter_resumo_mensal(sessao, ano, mes)
    totais = financeiro.obter_totais_por_categoria(sessao, ano, mes)
    return ResumoMensalSaida(
        ano=resumo.ano,
        mes=resumo.mes,
        total_receitas=arredondar_moeda(resumo.total_receitas),
        total_despesas=arredondar_moeda(resumo.total_despesas),
        saldo=arredondar_moeda(resumo.saldo),
        por_categoria=[
            TotalCategoriaSaida(
                tipo=t.tipo,
                categoria_id=t.categoria_id,
                categoria_nome=t.categoria_nome,
                total=arredondar_moeda(t.total),
                percentual=arredondar(t.percentual, CASAS_PERCENTUAL_SAIDA).normalize(),
            )
            for t in totais
        ],
    )
