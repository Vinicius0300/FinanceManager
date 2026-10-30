"""Poupança: rendimento mensal no aniversário (regra simplificada em ``domain/poupanca.py``)."""

from app.asset_types.base import HandlerMontante, Identidade, Metadados
from app.domain.enums import TipoIndicador
from app.domain.indicadores import Indicadores
from app.domain.montante import FatorAcumulado
from app.domain.poupanca import criar_fator_poupanca


class Poupanca(HandlerMontante):
    slug = "poupanca"
    nome = "Poupança"
    descricao = "Caderneta de poupança, com rendimento creditado no aniversário mensal."

    def mesma_identidade(self, a: Identidade, b: Identidade) -> bool:
        # Um único ativo "Poupança": a posição já é separada por instituição.
        return True

    def indicadores_necessarios(self, metadados: Metadados) -> frozenset[TipoIndicador]:
        return frozenset({TipoIndicador.SELIC})

    def criar_fator(self, metadados: Metadados, indicadores: Indicadores) -> FatorAcumulado:
        return criar_fator_poupanca(indicadores)
