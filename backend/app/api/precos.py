"""Preços (fechamentos diários), valor manual, status da atualização e atualização forçada."""

from datetime import date, datetime

from fastapi import APIRouter, status

from app.api.dependencias import (
    PROTEGIDO,
    AgendadorDep,
    AgoraDep,
    Deslocamento,
    HojeDep,
    Limite,
    SessaoDep,
    respostas,
)
from app.api.schemas import Modelo, Numero, Pagina
from app.core.errors import AplicacaoError
from app.domain.enums import OrigemPreco
from app.domain.erros import exigir
from app.domain.precos import instante_fechamento
from app.repositories import modelos as m
from app.services import mercado
from app.services.status_cotacoes import StatusAtivo, status_ativo, status_ativos

router = APIRouter(prefix="/api", tags=["preços e cotações"], dependencies=PROTEGIDO)


class PrecoSaida(Modelo):
    id: int
    ativo_id: int
    data: date
    data_hora: datetime
    valor: Numero
    moeda: str
    origem: OrigemPreco
    provider: str | None


class PrecoManualEntrada(Modelo):
    data: date
    valor: Numero


class StatusAtivoSaida(Modelo):
    ativo_id: int
    nome: str
    tipo: str
    provider: str | None
    origem: OrigemPreco | None
    data: date | None
    data_hora: datetime | None
    valor: Numero | None
    provider_preco: str | None
    defasado: bool
    aviso: str | None
    ultima_tentativa: datetime | None
    ultimo_sucesso: datetime | None
    ultimo_erro: str | None


class AtualizacaoStatus(Modelo):
    em_andamento: bool
    ultimo_ciclo_inicio: datetime | None
    ultimo_ciclo_fim: datetime | None
    precos_atualizados: int | None
    erros: int | None


class AtualizacaoIniciada(Modelo):
    mensagem: str


def _preco(preco: m.Preco) -> PrecoSaida:
    return PrecoSaida(
        id=preco.id,
        ativo_id=preco.ativo_id,
        data=preco.data,
        data_hora=preco.data_hora,
        valor=preco.valor,
        moeda=preco.moeda,
        origem=preco.origem,
        provider=preco.provider,
    )


def _status(item: StatusAtivo) -> StatusAtivoSaida:
    return StatusAtivoSaida(
        ativo_id=item.ativo_id,
        nome=item.nome,
        tipo=item.tipo,
        provider=item.provider,
        origem=item.origem,
        data=item.data,
        data_hora=item.data_hora,
        valor=item.valor,
        provider_preco=item.provider_preco,
        defasado=item.defasado,
        aviso=item.aviso,
        ultima_tentativa=item.ultima_tentativa,
        ultimo_sucesso=item.ultimo_sucesso,
        ultimo_erro=item.ultimo_erro,
    )


@router.get(
    "/ativos/{ativo_id}/precos",
    response_model=Pagina[PrecoSaida],
    summary="Histórico de preços (um por dia; o último do dia é o fechamento)",
    responses=respostas(404),
)
def listar_precos(
    ativo_id: int,
    sessao: SessaoDep,
    inicio: date | None = None,
    fim: date | None = None,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> Pagina[PrecoSaida]:
    pagina = mercado.listar_precos(sessao, ativo_id, inicio, fim, limite, deslocamento)
    return Pagina[PrecoSaida](
        itens=[_preco(p) for p in pagina.itens],
        total=pagina.total,
        limite=limite,
        deslocamento=deslocamento,
    )


@router.post(
    "/ativos/{ativo_id}/precos",
    response_model=PrecoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Informa o preço de um dia manualmente (só ativos cotados)",
    description=(
        "Substitui o preço automático daquele dia e não é sobrescrito pela coleta do mesmo "
        "dia. Renda fixa e poupança são calculadas e não aceitam preço manual."
    ),
    responses=respostas(404, 422),
)
def registrar_preco_manual(
    ativo_id: int,
    dados: PrecoManualEntrada,
    sessao: SessaoDep,
    hoje: HojeDep,
    agora: AgoraDep,
) -> PrecoSaida:
    exigir(dados.data <= hoje, "data", "Não é possível informar o preço de uma data futura.")
    instante = agora if dados.data == hoje else instante_fechamento(dados.data)
    preco = mercado.registrar_preco(sessao, ativo_id, instante, dados.valor, OrigemPreco.MANUAL)
    return _preco(preco)


@router.delete(
    "/precos/{preco_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um preço manual (a coleta automática volta a valer)",
    responses=respostas(404, 422),
)
def excluir_preco(preco_id: int, sessao: SessaoDep) -> None:
    mercado.excluir_preco_manual(sessao, preco_id)


@router.get(
    "/cotacoes/status",
    response_model=list[StatusAtivoSaida],
    summary="Status da última atualização de cada ativo",
    description="Data/hora, origem, provider, se está defasado e o último erro da coleta.",
    responses=respostas(),
)
def listar_status_cotacoes(sessao: SessaoDep, hoje: HojeDep) -> list[StatusAtivoSaida]:
    return [_status(item) for item in status_ativos(sessao, hoje)]


@router.get(
    "/ativos/{ativo_id}/status",
    response_model=StatusAtivoSaida,
    summary="Status da última atualização de um ativo",
    responses=respostas(404),
)
def obter_status_cotacao(ativo_id: int, sessao: SessaoDep, hoje: HojeDep) -> StatusAtivoSaida:
    return _status(status_ativo(sessao, ativo_id, hoje))


@router.get(
    "/cotacoes/atualizacao",
    response_model=AtualizacaoStatus,
    summary="Se há uma atualização em andamento e o resumo do último ciclo",
    responses=respostas(),
)
def obter_atualizacao(agendador: AgendadorDep) -> AtualizacaoStatus:
    resumo = agendador.ultimo_resumo
    return AtualizacaoStatus(
        em_andamento=agendador.em_execucao,
        ultimo_ciclo_inicio=resumo.inicio if resumo else None,
        ultimo_ciclo_fim=resumo.fim if resumo else None,
        precos_atualizados=resumo.precos_atualizados if resumo else None,
        erros=resumo.erros if resumo else None,
    )


@router.post(
    "/cotacoes/atualizar",
    response_model=AtualizacaoIniciada,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Força a atualização de cotações e indicadores agora",
    description=(
        "Ignora o intervalo e roda em segundo plano; o andamento chega pelo stream de "
        "eventos. Se já houver uma atualização rodando, responde 409."
    ),
    responses=respostas(409),
)
async def forcar_atualizacao(agendador: AgendadorDep) -> AtualizacaoIniciada:
    disparo = agendador.forcar_atualizacao()
    if not disparo.iniciado:
        raise AplicacaoError(409, "atualizacao_em_andamento", disparo.mensagem)
    return AtualizacaoIniciada(mensagem=disparo.mensagem)
