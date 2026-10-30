"""Listas oficiais de tickers (B3 e EUA) e busca do cadastro de movimentações.

A busca devolve, para cada papel, o **tipo oficial** (da lista da bolsa) ou ``null``
quando não é possível identificar com certeza; o front avisa se o tipo escolhido diverge.
Ticker fora da lista (e lista não tentada hoje) dispara uma atualização em segundo plano;
o fim chega pelo evento SSE ``lista_atualizada`` (ou ``erro_lista``).
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.dependencias import (
    PROTEGIDO,
    AgendadorDep,
    HojeDep,
    ProvidersDep,
    SessaoDep,
    respostas,
)
from app.api.schemas import Modelo
from app.core.errors import AplicacaoError
from app.services import simbolos as servico

router = APIRouter(prefix="/api/simbolos", tags=["símbolos"], dependencies=PROTEGIDO)


class ItemBuscaSaida(Modelo):
    simbolo: str | None
    nome: str
    tipo: str | None  # tipo oficial; null = não identificado
    origem: str  # carteira, lista ou pesquisa
    ativo_id: int | None
    simbolo_externo: str | None
    categoria: str | None
    campos_sugeridos: dict[str, str]


class BuscaSimbolosSaida(Modelo):
    itens: list[ItemBuscaSaida]
    bolsa: str | None
    lista_disponivel: bool
    atualizando_lista: bool
    aviso: str | None


class ListaSimbolosSaida(Modelo):
    bolsa: str
    quantidade: int
    atualizado_em: datetime | None
    ultima_tentativa: datetime | None
    status_arquivo: str | None
    data_arquivo: date | None
    ultimo_erro: str | None


class SituacaoListasSaida(Modelo):
    em_andamento: bool
    listas: list[ListaSimbolosSaida]


class AtualizacaoListaIniciada(Modelo):
    mensagem: str


@router.get(
    "/busca",
    response_model=BuscaSimbolosSaida,
    summary="Busca um ativo para o cadastro de movimentações",
    description=(
        "Ativos já cadastrados, a lista oficial da bolsa do tipo (com o tipo oficial de "
        "cada papel) e, se o ticker não estiver na lista, a pesquisa externa (só para "
        "sugerir o nome). Cripto: pesquisa da CoinGecko."
    ),
    responses=respostas(422),
)
def buscar_simbolos(
    sessao: SessaoDep,
    providers: ProvidersDep,
    agendador: AgendadorDep,
    hoje: HojeDep,
    tipo: Annotated[str, Query(description="Slug do tipo de ativo escolhido.")],
    q: Annotated[str, Query(max_length=100, description="Ticker ou parte do nome.")] = "",
) -> BuscaSimbolosSaida:
    resultado = servico.buscar_simbolos(sessao, tipo, q, providers, hoje)
    atualizando = agendador.importando_listas
    if resultado.lista_desatualizada and resultado.bolsa is not None:
        atualizando = agendador.importar_listas_de_outra_thread([resultado.bolsa]) or atualizando
    return BuscaSimbolosSaida(
        itens=[
            ItemBuscaSaida(
                simbolo=i.simbolo,
                nome=i.nome,
                tipo=i.tipo,
                origem=i.origem,
                ativo_id=i.ativo_id,
                simbolo_externo=i.simbolo_externo,
                categoria=i.categoria,
                campos_sugeridos=i.campos_sugeridos,
            )
            for i in resultado.itens
        ],
        bolsa=resultado.bolsa,
        lista_disponivel=resultado.lista_disponivel,
        atualizando_lista=atualizando,
        aviso=resultado.aviso,
    )


@router.get(
    "/listas",
    response_model=SituacaoListasSaida,
    summary="Situação das listas oficiais de tickers",
    responses=respostas(),
)
def obter_listas(
    sessao: SessaoDep, providers: ProvidersDep, agendador: AgendadorDep
) -> SituacaoListasSaida:
    return SituacaoListasSaida(
        em_andamento=agendador.importando_listas,
        listas=[
            ListaSimbolosSaida(
                bolsa=lista.bolsa,
                quantidade=lista.quantidade or 0,
                atualizado_em=lista.atualizado_em,
                ultima_tentativa=lista.ultima_tentativa,
                status_arquivo=lista.status_arquivo,
                data_arquivo=lista.data_arquivo,
                ultimo_erro=lista.ultimo_erro,
            )
            for lista in servico.situacao_listas(sessao, providers.bolsas)
        ],
    )


@router.post(
    "/atualizar",
    response_model=AtualizacaoListaIniciada,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Baixa de novo as listas oficiais de tickers",
    description=(
        "Roda em segundo plano (B3 e EUA); o fim chega pelos eventos `lista_atualizada` "
        "ou `erro_lista`. Se já houver uma atualização rodando, responde 409."
    ),
    responses=respostas(409),
)
async def atualizar_listas(agendador: AgendadorDep) -> AtualizacaoListaIniciada:
    disparo = agendador.importar_listas()
    if not disparo.iniciado:
        raise AplicacaoError(409, "atualizacao_em_andamento", disparo.mensagem)
    return AtualizacaoListaIniciada(mensagem=disparo.mensagem)
