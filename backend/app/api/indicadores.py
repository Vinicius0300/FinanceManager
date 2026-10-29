"""Indicadores (Selic, CDI, IPCA, câmbio): consulta por tipo e período e lançamento manual.

Unidades: Selic e CDI em % ao ano; IPCA em % no mês (data = dia 1º); câmbio em BRL por
unidade da moeda. Registro manual (ou editado) nunca é sobrescrito pela coleta automática.
"""

from datetime import date

from fastapi import APIRouter, status

from app.api.dependencias import PROTEGIDO, SessaoDep, respostas
from app.api.schemas import Modelo, Numero
from app.domain.enums import TipoIndicador
from app.domain.moedas import MOEDA_BASE
from app.repositories import modelos as m
from app.services import mercado

router = APIRouter(prefix="/api", tags=["indicadores"], dependencies=PROTEGIDO)


class IndicadorEntrada(Modelo):
    tipo: TipoIndicador
    data: date
    valor: Numero
    moeda: str = MOEDA_BASE


class IndicadorEdicao(Modelo):
    valor: Numero


class IndicadorSaida(Modelo):
    id: int
    tipo: TipoIndicador
    moeda: str
    data: date
    valor: Numero
    fonte: str | None


def _indicador(indicador: m.Indicador) -> IndicadorSaida:
    return IndicadorSaida(
        id=indicador.id,
        tipo=indicador.tipo,
        moeda=indicador.moeda,
        data=indicador.data,
        valor=indicador.valor,
        fonte=indicador.fonte,
    )


@router.get(
    "/indicadores",
    response_model=list[IndicadorSaida],
    summary="Lista indicadores por tipo, moeda e período",
    responses=respostas(422),
)
def listar_indicadores(
    sessao: SessaoDep,
    tipo: TipoIndicador | None = None,
    moeda: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
) -> list[IndicadorSaida]:
    return [_indicador(i) for i in mercado.listar_indicadores(sessao, tipo, moeda, inicio, fim)]


@router.post(
    "/indicadores",
    response_model=IndicadorSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Lança um indicador manualmente",
    responses=respostas(409, 422),
)
def criar_indicador(dados: IndicadorEntrada, sessao: SessaoDep) -> IndicadorSaida:
    indicador = mercado.registrar_indicador(
        sessao, dados.tipo, dados.data, dados.valor, dados.moeda
    )
    return _indicador(indicador)


@router.put(
    "/indicadores/{indicador_id}",
    response_model=IndicadorSaida,
    summary="Altera o valor de um indicador (passa a ser manual)",
    responses=respostas(404, 422),
)
def editar_indicador(
    indicador_id: int, dados: IndicadorEdicao, sessao: SessaoDep
) -> IndicadorSaida:
    return _indicador(mercado.editar_indicador(sessao, indicador_id, dados.valor))


@router.delete(
    "/indicadores/{indicador_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um indicador",
    responses=respostas(404),
)
def excluir_indicador(indicador_id: int, sessao: SessaoDep) -> None:
    mercado.excluir_indicador(sessao, indicador_id)
