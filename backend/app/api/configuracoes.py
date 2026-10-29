"""Configurações: intervalo da atualização automática (1 a 15 min, padrão 5).

Não existe configuração de moeda: o app é todo em BRL. A mudança do intervalo vale na hora
(o agendador é acordado e passa a usar o novo valor sem reiniciar o app).
"""

from fastapi import APIRouter

from app.api.dependencias import PROTEGIDO, AgendadorDep, SessaoDep, respostas
from app.api.schemas import Modelo
from app.services import configuracoes

router = APIRouter(prefix="/api", tags=["configurações"], dependencies=PROTEGIDO)


class ConfiguracoesSaida(Modelo):
    intervalo_atualizacao_min: int


class ConfiguracoesEntrada(Modelo):
    intervalo_atualizacao_min: int


@router.get(
    "/configuracoes",
    response_model=ConfiguracoesSaida,
    summary="Configurações do app",
    responses=respostas(),
)
def obter_configuracoes(sessao: SessaoDep) -> ConfiguracoesSaida:
    atuais = configuracoes.obter_configuracoes(sessao)
    return ConfiguracoesSaida(intervalo_atualizacao_min=atuais.intervalo_atualizacao_min)


@router.put(
    "/configuracoes",
    response_model=ConfiguracoesSaida,
    summary="Altera o intervalo da atualização automática (1 a 15 minutos)",
    responses=respostas(422),
)
def alterar_configuracoes(
    dados: ConfiguracoesEntrada, sessao: SessaoDep, agendador: AgendadorDep
) -> ConfiguracoesSaida:
    novas = configuracoes.alterar_configuracoes(sessao, dados.intervalo_atualizacao_min)
    sessao.commit()  # grava antes de acordar o agendador, que relê a configuração
    agendador.acordar_de_outra_thread()
    return ConfiguracoesSaida(intervalo_atualizacao_min=novas.intervalo_atualizacao_min)
