"""Erros de domínio: mensagens em pt-BR, sem conhecimento de HTTP.

A camada de API converte esses erros no formato padrão ``{codigo, mensagem, detalhes}``
(ver ``app/core/errors.py``): não encontrado → 404, conflito → 409, demais → 422.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DetalheCampo:
    campo: str
    mensagem: str


class DominioError(Exception):
    """Violação de regra de negócio, com código estável e mensagem para o usuário."""

    codigo = "regra_de_negocio"

    def __init__(self, mensagem: str, detalhes: list[DetalheCampo] | None = None) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or []


class ValidacaoError(DominioError):
    codigo = "validacao"


class NaoEncontradoError(DominioError):
    codigo = "nao_encontrado"


class ConflitoError(DominioError):
    codigo = "conflito"


class PosicaoInsuficienteError(DominioError):
    """Venda maior que a posição ou resgate maior que o saldo do investimento."""

    codigo = "posicao_insuficiente"


class SaldoInsuficienteError(DominioError):
    """Operação deixaria a conta corrente de uma instituição negativa."""

    codigo = "saldo_insuficiente"


class CambioAusenteError(DominioError):
    codigo = "cambio_ausente"


class IndicadorAusenteError(DominioError):
    codigo = "indicador_ausente"


class OperacaoNaoPermitidaError(DominioError):
    codigo = "operacao_nao_permitida"


def exigir(condicao: bool, campo: str, mensagem: str) -> None:
    """Levanta ``ValidacaoError`` (com o campo nos detalhes) se a condição for falsa."""
    if not condicao:
        raise ValidacaoError(mensagem, [DetalheCampo(campo, mensagem)])
