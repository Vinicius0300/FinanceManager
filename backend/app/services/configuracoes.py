"""Configurações do app (chave/valor). Não existe configuração de moeda: o app é todo em BRL."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.agenda import INTERVALO_MAXIMO_MIN, INTERVALO_MINIMO_MIN, INTERVALO_PADRAO_MIN
from app.domain.erros import exigir
from app.repositories.configuracoes import RepositorioConfiguracoes

CHAVE_INTERVALO = "intervalo_atualizacao_min"


@dataclass(frozen=True)
class Configuracoes:
    intervalo_atualizacao_min: int


def _intervalo_valido(valor: object) -> bool:
    return (
        isinstance(valor, int)
        and not isinstance(valor, bool)
        and INTERVALO_MINIMO_MIN <= valor <= INTERVALO_MAXIMO_MIN
    )


def obter_intervalo(sessao: Session) -> int:
    """Intervalo da atualização de ações e cripto, em minutos (padrão 5).

    Um valor gravado fora da faixa (banco editado à mão) cai no padrão.
    """
    valor = RepositorioConfiguracoes(sessao).valor(CHAVE_INTERVALO, INTERVALO_PADRAO_MIN)
    return valor if _intervalo_valido(valor) and isinstance(valor, int) else INTERVALO_PADRAO_MIN


def obter_configuracoes(sessao: Session) -> Configuracoes:
    return Configuracoes(intervalo_atualizacao_min=obter_intervalo(sessao))


def alterar_configuracoes(sessao: Session, intervalo_atualizacao_min: int) -> Configuracoes:
    exigir(
        _intervalo_valido(intervalo_atualizacao_min),
        "intervalo_atualizacao_min",
        f"O intervalo deve ser um número inteiro de {INTERVALO_MINIMO_MIN} a "
        f"{INTERVALO_MAXIMO_MIN} minutos.",
    )
    RepositorioConfiguracoes(sessao).gravar(CHAVE_INTERVALO, intervalo_atualizacao_min)
    return obter_configuracoes(sessao)
