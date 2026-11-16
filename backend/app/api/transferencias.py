"""Transferências entre instituições (aba Caixa de Movimentações).

Mesma moeda nas duas pontas. A origem precisa cobrir valor + tarifa: sem saldo, responde
**422** ``saldo_insuficiente`` (recusa, sem ajuste, como o saque). Editar ou excluir uma
transferência que deixaria algum caixa negativo também é recusado. Tarifa só em BRL; ela
vira uma despesa na origem, gravada e excluída junto com a transferência.
"""

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, status

from app.api.dependencias import PROTEGIDO, Deslocamento, Limite, SessaoDep, respostas
from app.api.schemas import Modelo, Numero, Pagina
from app.repositories import modelos as m
from app.services import transferencias as servico

router = APIRouter(prefix="/api", tags=["transferências"], dependencies=PROTEGIDO)


class TransferenciaEntrada(Modelo):
    data: date
    origem_id: int
    destino_id: int
    moeda: str = "BRL"
    valor: Numero
    tarifa: Numero = Decimal(0)
    categoria_tarifa_id: int | None = None
    descricao: str | None = None


class TransferenciaSaida(Modelo):
    id: int
    data: date
    origem_id: int
    origem_nome: str
    destino_id: int
    destino_nome: str
    moeda: str
    valor: Numero
    tarifa: Numero
    categoria_tarifa_id: int | None
    tarifa_lancamento_id: int | None  # despesa gerada pela tarifa (só leitura)
    descricao: str | None
    criado_em: datetime


def _saida(transferencia: m.Transferencia) -> TransferenciaSaida:
    tarifa = transferencia.tarifa_lancamento
    return TransferenciaSaida(
        id=transferencia.id,
        data=transferencia.data,
        origem_id=transferencia.origem_id,
        origem_nome=transferencia.origem.nome,
        destino_id=transferencia.destino_id,
        destino_nome=transferencia.destino.nome,
        moeda=transferencia.moeda,
        valor=transferencia.valor,
        tarifa=transferencia.tarifa,
        categoria_tarifa_id=tarifa.categoria_id if tarifa else None,
        tarifa_lancamento_id=tarifa.id if tarifa else None,
        descricao=transferencia.descricao,
        criado_em=transferencia.criado_em,
    )


def _nova(dados: TransferenciaEntrada) -> servico.NovaTransferencia:
    return servico.NovaTransferencia(
        data=dados.data,
        origem_id=dados.origem_id,
        destino_id=dados.destino_id,
        moeda=dados.moeda,
        valor=dados.valor,
        tarifa=dados.tarifa,
        categoria_tarifa_id=dados.categoria_tarifa_id,
        descricao=dados.descricao,
    )


@router.get(
    "/transferencias",
    response_model=Pagina[TransferenciaSaida],
    summary="Lista transferências (mais recentes primeiro)",
    description="`instituicao_id` casa com a origem ou com o destino.",
    responses=respostas(),
)
def listar_transferencias(
    sessao: SessaoDep,
    instituicao_id: int | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> Pagina[TransferenciaSaida]:
    todas = servico.listar_transferencias(
        sessao, instituicao_id=instituicao_id, inicio=inicio, fim=fim
    )
    return Pagina[TransferenciaSaida](
        itens=[_saida(x) for x in todas[deslocamento : deslocamento + limite]],
        total=len(todas),
        limite=limite,
        deslocamento=deslocamento,
    )


@router.post(
    "/transferencias",
    response_model=TransferenciaSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma transferência entre instituições",
    description="Origem sem saldo para valor + tarifa: 422 `saldo_insuficiente`.",
    responses=respostas(404, 422),
)
def criar_transferencia(dados: TransferenciaEntrada, sessao: SessaoDep) -> TransferenciaSaida:
    return _saida(servico.registrar_transferencia(sessao, _nova(dados)))


@router.get(
    "/transferencias/{transferencia_id}",
    response_model=TransferenciaSaida,
    summary="Detalha uma transferência",
    responses=respostas(404),
)
def obter_transferencia(transferencia_id: int, sessao: SessaoDep) -> TransferenciaSaida:
    return _saida(servico.obter_transferencia(sessao, transferencia_id))


@router.put(
    "/transferencias/{transferencia_id}",
    response_model=TransferenciaSaida,
    summary="Altera uma transferência (movimentos e tarifa são refeitos)",
    description="Se algum caixa ficaria negativo: 422 `saldo_insuficiente`.",
    responses=respostas(404, 422),
)
def editar_transferencia(
    transferencia_id: int, dados: TransferenciaEntrada, sessao: SessaoDep
) -> TransferenciaSaida:
    return _saida(servico.editar_transferencia(sessao, transferencia_id, _nova(dados)))


@router.delete(
    "/transferencias/{transferencia_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui uma transferência (com os movimentos e a tarifa)",
    description="Se o destino (ou outro caixa) ficaria negativo: 422 `saldo_insuficiente`.",
    responses=respostas(404, 422),
)
def excluir_transferencia(transferencia_id: int, sessao: SessaoDep) -> None:
    servico.excluir_transferencia(sessao, transferencia_id)
