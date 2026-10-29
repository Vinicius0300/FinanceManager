"""Tipos de ativo (schema de campos para gerar formulários) e CRUD de ativos."""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import Field

from app.api.dependencias import PROTEGIDO, AgendadorDep, SessaoDep, respostas
from app.api.schemas import Modelo
from app.asset_types.base import HandlerCotado
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.jobs.agendador import Agendador
from app.repositories import modelos as m
from app.services import ativos as servico_ativos
from app.services import cadastros

router = APIRouter(prefix="/api", tags=["ativos"], dependencies=PROTEGIDO)


class OpcaoCampo(Modelo):
    valor: str
    rotulo: str


class CampoTipo(Modelo):
    nome: str
    rotulo: str
    tipo: str  # texto, decimal, inteiro, data, escolha
    obrigatorio: bool
    ajuda: str | None
    opcoes: list[OpcaoCampo]
    minimo: str | None
    maximo: str | None
    tamanho_maximo: int | None


class TipoAtivoSaida(Modelo):
    slug: str
    nome: str
    descricao: str
    modo: str  # cotas ou montante
    moeda_padrao: str
    moedas_aceitas: list[str]
    provider: str | None
    tipos_transacao: list[str]
    aceita_taxas: bool
    campos: list[CampoTipo]


class AtivoEntrada(Modelo):
    tipo: str
    nome: str
    simbolo: str | None = None
    moeda: str | None = None
    simbolo_externo: str | None = None
    metadados: dict[str, str | int] = Field(default_factory=dict)


class AtivoEdicao(Modelo):
    nome: str
    simbolo_externo: str | None = None
    metadados: dict[str, str | int] = Field(default_factory=dict)


class AtivoSaida(Modelo):
    id: int
    tipo: str
    nome: str
    simbolo: str | None
    moeda: str
    provider: str | None
    simbolo_externo: str | None
    metadados: dict[str, str | int]
    criado_em: datetime


def _ativo(ativo: m.Ativo) -> AtivoSaida:
    return AtivoSaida(
        id=ativo.id,
        tipo=ativo.tipo,
        nome=ativo.nome,
        simbolo=ativo.simbolo,
        moeda=ativo.moeda,
        provider=ativo.provider,
        simbolo_externo=ativo.simbolo_externo,
        metadados=dict(ativo.metadados),
        criado_em=ativo.criado_em,
    )


def _coletar_depois(ativo: m.Ativo, agendador: Agendador, tarefas: BackgroundTasks) -> None:
    """Ativo cotado: coleta cotação e histórico logo depois da resposta (já gravado)."""
    if not isinstance(cadastros.handler_do_ativo(ativo), HandlerCotado):
        return

    async def coletar() -> None:
        agendador.coletar_ativo(ativo.id)

    tarefas.add_task(coletar)


@router.get(
    "/tipos-ativo",
    response_model=list[TipoAtivoSaida],
    summary="Tipos de ativo com o schema dos campos específicos",
    description="Usado pelo front para gerar o formulário de cadastro de cada tipo.",
    responses=respostas(),
)
def listar_tipos_ativo() -> list[TipoAtivoSaida]:
    return [TipoAtivoSaida.model_validate(h.schema()) for h in REGISTRO_PADRAO.todos()]


@router.get(
    "/tipos-ativo/{slug}",
    response_model=TipoAtivoSaida,
    summary="Schema de um tipo de ativo",
    responses=respostas(422),
)
def obter_tipo_ativo(slug: str) -> TipoAtivoSaida:
    return TipoAtivoSaida.model_validate(REGISTRO_PADRAO.obter(slug).schema())


@router.get(
    "/ativos",
    response_model=list[AtivoSaida],
    summary="Lista os ativos (opcionalmente de um tipo)",
    responses=respostas(),
)
def listar_ativos(sessao: SessaoDep, tipo: str | None = None) -> list[AtivoSaida]:
    return [_ativo(a) for a in cadastros.listar_ativos(sessao, tipo)]


@router.post(
    "/ativos",
    response_model=AtivoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um ativo",
    description=(
        "Ativos cotados começam a ser atualizados logo após o cadastro, em segundo plano "
        "(cotação do dia e fechamentos de até 1 ano)."
    ),
    responses=respostas(409, 422),
)
def criar_ativo(
    dados: AtivoEntrada,
    sessao: SessaoDep,
    agendador: AgendadorDep,
    tarefas: BackgroundTasks,
) -> AtivoSaida:
    ativo = cadastros.criar_ativo(
        sessao,
        cadastros.NovoAtivo(
            tipo=dados.tipo,
            nome=dados.nome,
            simbolo=dados.simbolo,
            moeda=dados.moeda,
            simbolo_externo=dados.simbolo_externo,
            metadados=dados.metadados,
        ),
    )
    _coletar_depois(ativo, agendador, tarefas)
    return _ativo(ativo)


@router.get(
    "/ativos/{ativo_id}",
    response_model=AtivoSaida,
    summary="Detalha um ativo",
    responses=respostas(404),
)
def obter_ativo(ativo_id: int, sessao: SessaoDep) -> AtivoSaida:
    return _ativo(cadastros.obter_ativo(sessao, ativo_id))


@router.put(
    "/ativos/{ativo_id}",
    response_model=AtivoSaida,
    summary="Altera nome, símbolo externo e campos específicos",
    description=(
        "Tipo e moeda não mudam. Alterar a identificação na fonte (símbolo externo, CNPJ, "
        "título) apaga os preços automáticos e baixa o histórico de novo."
    ),
    responses=respostas(404, 422),
)
def editar_ativo(
    ativo_id: int,
    dados: AtivoEdicao,
    sessao: SessaoDep,
    agendador: AgendadorDep,
    tarefas: BackgroundTasks,
) -> AtivoSaida:
    ativo = servico_ativos.editar_ativo(
        sessao,
        ativo_id,
        servico_ativos.EdicaoAtivo(
            nome=dados.nome, simbolo_externo=dados.simbolo_externo, metadados=dados.metadados
        ),
    )
    _coletar_depois(ativo, agendador, tarefas)  # sem efeito se nada precisar ser coletado
    return _ativo(ativo)


@router.delete(
    "/ativos/{ativo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um ativo sem transações nem eventos",
    responses=respostas(404, 422),
)
def excluir_ativo(ativo_id: int, sessao: SessaoDep) -> None:
    servico_ativos.excluir_ativo(sessao, ativo_id)
