"""Receitas e despesas: categorias, lançamentos e resumos do mês (proventos não entram).

Todo lançamento pertence a uma instituição e movimenta o caixa em BRL dela.
**Saldo:** despesa que deixaria o caixa negativo responde **409** ``saldo_insuficiente``
(reenvie com ``aceitar_ajuste=true`` para gravar com um ajuste de saldo); excluir ou
alterar uma receita que deixaria o caixa negativo responde **422** ``saldo_insuficiente``
(recusa, sem ajuste). A listagem traz também as transferências em BRL (``tag``), que não
entram nos totais.
"""

from datetime import date, datetime
from typing import Literal, cast

from fastapi import APIRouter, Query, status

from app.api.dependencias import PROTEGIDO, Deslocamento, Limite, SessaoDep, respostas
from app.api.schemas import Modelo, Numero, Pagina
from app.api.transacoes import erro_saldo_insuficiente
from app.core.errors import AplicacaoError
from app.domain.enums import TipoLancamento
from app.domain.numeros import arredondar, arredondar_moeda
from app.repositories import modelos as m
from app.services import financeiro

router = APIRouter(prefix="/api", tags=["receitas e despesas"], dependencies=PROTEGIDO)

CASAS_PERCENTUAL_SAIDA = 8

TagLancamento = Literal["lancamento", "tarifa", "transferencia_saida", "transferencia_entrada"]


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
    instituicao_id: int
    categoria_id: int | None = None
    observacao: str | None = None
    aceitar_ajuste: bool = False


class LancamentoSaida(Modelo):
    """Linha de Receitas e Despesas: lançamento, tarifa ou ponta de transferência.

    ``chave`` é única na listagem. Linhas de transferência não têm ``lancamento_id`` e,
    como as tarifas, vêm com ``editavel = false`` (edite em Movimentações → Caixa).
    """

    chave: str
    tag: TagLancamento
    lancamento_id: int | None
    transferencia_id: int | None
    tipo: TipoLancamento
    data: date
    descricao: str
    valor: Numero
    instituicao_id: int
    instituicao_nome: str
    categoria_id: int | None
    categoria_nome: str | None
    observacao: str | None
    criado_em: datetime
    editavel: bool


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


class ResumoInstituicaoSaida(Modelo):
    instituicao_id: int
    instituicao_nome: str
    receitas: Numero
    despesas: Numero  # inclui tarifas de transferência
    entrou: Numero  # transferências recebidas (BRL)
    saiu: Numero  # transferências enviadas (BRL)
    saldo: Numero  # receitas − despesas + entrou − saiu


def _categoria(categoria: m.Categoria) -> CategoriaSaida:
    return CategoriaSaida(id=categoria.id, nome=categoria.nome, tipo=categoria.tipo)


def _linha(linha: financeiro.LinhaLancamento) -> LancamentoSaida:
    return LancamentoSaida(
        chave=linha.chave,
        tag=cast(TagLancamento, linha.tag),
        lancamento_id=linha.lancamento_id,
        transferencia_id=linha.transferencia_id,
        tipo=linha.tipo,
        data=linha.data,
        descricao=linha.descricao,
        valor=linha.valor,
        instituicao_id=linha.instituicao_id,
        instituicao_nome=linha.instituicao_nome,
        categoria_id=linha.categoria_id,
        categoria_nome=linha.categoria_nome,
        observacao=linha.observacao,
        criado_em=linha.criado_em,
        editavel=linha.editavel,
    )


def _lancamento(lancamento: m.Lancamento) -> LancamentoSaida:
    return _linha(financeiro.linha_do_lancamento(lancamento))


def _resultado(sessao: SessaoDep, resultado: financeiro.ResultadoLancamento) -> LancamentoSaida:
    """Aviso de saldo insuficiente vira 409 (a sessão é desfeita)."""
    if resultado.aviso is not None:
        raise erro_saldo_insuficiente(sessao, resultado.aviso)
    if resultado.lancamento is None:  # pragma: no cover - sem aviso, sempre há lançamento
        raise AplicacaoError(500, "erro_interno", "Lançamento não gravado.")
    return _lancamento(resultado.lancamento)


def _novo(dados: LancamentoEntrada) -> financeiro.NovoLancamento:
    return financeiro.NovoLancamento(
        tipo=dados.tipo,
        data=dados.data,
        descricao=dados.descricao,
        valor=dados.valor,
        instituicao_id=dados.instituicao_id,
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
    summary="Lista lançamentos e transferências em BRL (mais recentes primeiro)",
    responses=respostas(),
)
def listar_lancamentos(
    sessao: SessaoDep,
    tipo: TipoLancamento | None = None,
    categoria_id: int | None = None,
    instituicao_id: int | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> Pagina[LancamentoSaida]:
    pagina = financeiro.listar_lancamentos(
        sessao,
        tipo=tipo,
        categoria_id=categoria_id,
        instituicao_id=instituicao_id,
        inicio=inicio,
        fim=fim,
        limite=limite,
        deslocamento=deslocamento,
    )
    return Pagina[LancamentoSaida](
        itens=[_linha(x) for x in pagina.itens],
        total=pagina.total,
        limite=limite,
        deslocamento=deslocamento,
    )


@router.post(
    "/lancamentos",
    response_model=LancamentoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma receita ou despesa (movimenta o caixa da instituição)",
    description=(
        "Despesa que deixaria o caixa negativo responde 409 `saldo_insuficiente` sem gravar; "
        "reenvie com `aceitar_ajuste=true` para gravar com um ajuste de saldo."
    ),
    responses=respostas(404, 409, 422),
)
def criar_lancamento(dados: LancamentoEntrada, sessao: SessaoDep) -> LancamentoSaida:
    resultado = financeiro.registrar_lancamento(
        sessao, _novo(dados), aceitar_ajuste=dados.aceitar_ajuste
    )
    return _resultado(sessao, resultado)


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
    description=(
        "Despesa que passa a faltar saldo: 409 (aceite com `aceitar_ajuste=true`). Receita "
        "alterada que deixaria o caixa negativo: 422 `saldo_insuficiente`. Tarifas de "
        "transferência não podem ser alteradas aqui (422)."
    ),
    responses=respostas(404, 409, 422),
)
def editar_lancamento(
    lancamento_id: int, dados: LancamentoEntrada, sessao: SessaoDep
) -> LancamentoSaida:
    resultado = financeiro.editar_lancamento(
        sessao, lancamento_id, _novo(dados), aceitar_ajuste=dados.aceitar_ajuste
    )
    return _resultado(sessao, resultado)


@router.delete(
    "/lancamentos/{lancamento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um lançamento (e o ajuste de saldo ligado a ele)",
    description=(
        "Recusa com 422 `saldo_insuficiente` se o caixa ficar negativo, e com 422 se for a "
        "tarifa de uma transferência."
    ),
    responses=respostas(404, 422),
)
def excluir_lancamento(lancamento_id: int, sessao: SessaoDep) -> None:
    financeiro.excluir_lancamento(sessao, lancamento_id)


@router.get(
    "/resumo-mensal",
    response_model=ResumoMensalSaida,
    summary="Receitas, despesas, saldo e totais por categoria do mês",
    description="Transferências não entram; a tarifa delas entra como despesa.",
    responses=respostas(422),
)
def obter_resumo_mensal(
    sessao: SessaoDep,
    ano: int = Query(ge=1900, le=9999),
    mes: int = Query(ge=1, le=12),
    instituicao_id: int | None = None,
) -> ResumoMensalSaida:
    resumo = financeiro.obter_resumo_mensal(sessao, ano, mes, instituicao_id)
    totais = financeiro.obter_totais_por_categoria(sessao, ano, mes, instituicao_id)
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


@router.get(
    "/resumo-mensal/instituicoes",
    response_model=list[ResumoInstituicaoSaida],
    summary="Receitas, despesas, transferências (BRL) e saldo do mês por instituição",
    responses=respostas(422),
)
def obter_resumo_por_instituicao(
    sessao: SessaoDep,
    ano: int = Query(ge=1900, le=9999),
    mes: int = Query(ge=1, le=12),
) -> list[ResumoInstituicaoSaida]:
    return [
        ResumoInstituicaoSaida(
            instituicao_id=item.instituicao.id,
            instituicao_nome=item.instituicao.nome,
            receitas=arredondar_moeda(item.resumo.receitas),
            despesas=arredondar_moeda(item.resumo.despesas),
            entrou=arredondar_moeda(item.resumo.entrou),
            saiu=arredondar_moeda(item.resumo.saiu),
            saldo=arredondar_moeda(item.resumo.saldo),
        )
        for item in financeiro.obter_resumo_por_instituicao(sessao, ano, mes)
    ]
