"""O fator de renda fixa é criado uma vez só (bloco 2 do review).

Antes, ``avaliar_carteira`` criava o fator duas vezes por posição (uma em ``estado_montante`` e
outra para avaliar) e histórico, série de patrimônio e reprocessamento criavam um por posição.
Cenário: um CDB com aportes em duas instituições (duas posições do mesmo ativo).
"""

from collections.abc import Callable
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.asset_types.base import Metadados
from app.asset_types.renda_fixa import RendaFixa
from app.domain.enums import TipoIndicador, TipoInstituicao, TipoTransacao
from app.domain.indicadores import Indicadores
from app.domain.montante import FatorAcumulado
from app.domain.numeros import arredondar_moeda
from app.repositories import modelos as m
from app.services import historico
from app.services.carteira import avaliar_carteira
from app.services.historico import FiltroHistorico
from app.services.patrimonio import serie_patrimonio
from tests.fabricas import D, cdb, deposito, indicador, instituicao, montante

DATA_REF = date(2025, 9, 1)


class Contador:
    def __init__(self) -> None:
        self.chamadas = 0


@pytest.fixture
def contador(monkeypatch: pytest.MonkeyPatch) -> Contador:
    """Conta as chamadas de ``RendaFixa.criar_fator`` sem mudar o resultado."""
    contagem = Contador()
    original: Callable[[RendaFixa, Metadados, Indicadores], FatorAcumulado] = RendaFixa.criar_fator

    def contado(self: RendaFixa, metadados: Metadados, indicadores: Indicadores) -> FatorAcumulado:
        contagem.chamadas += 1
        return original(self, metadados, indicadores)

    monkeypatch.setattr(RendaFixa, "criar_fator", contado)
    return contagem


def cenario(sessao: Session) -> m.Ativo:
    banco = instituicao(sessao, "Banco X", TipoInstituicao.BANCO)
    outro = instituicao(sessao, "Banco Y", TipoInstituicao.BANCO)
    titulo = cdb(sessao)
    indicador(sessao, TipoIndicador.CDI, date(2025, 7, 1), "14.90")
    deposito(sessao, banco, "10000", date(2025, 8, 1))
    deposito(sessao, outro, "5000", date(2025, 8, 1))
    montante(sessao, titulo, banco, TipoTransacao.APORTE, date(2025, 8, 1), "10000")
    montante(sessao, titulo, outro, TipoTransacao.APORTE, date(2025, 8, 1), "5000")
    return titulo


def test_reprocessar_cria_um_fator_por_ativo(sessao: Session, contador: Contador) -> None:
    titulo = cenario(sessao)
    banco = instituicao(sessao, "Banco Z", TipoInstituicao.BANCO)
    deposito(sessao, banco, "100", date(2025, 8, 4))
    contador.chamadas = 0
    montante(sessao, titulo, banco, TipoTransacao.APORTE, date(2025, 8, 4), "100")
    # O ativo passa a ter 3 posições, mas o reprocessamento cria o fator uma vez.
    assert contador.chamadas == 1


def test_carteira_cria_o_fator_uma_vez_por_posicao(sessao: Session, contador: Contador) -> None:
    cenario(sessao)
    contador.chamadas = 0
    geral = avaliar_carteira(sessao, DATA_REF).geral()
    # 2 posições → 2 fatores (antes eram 4: estado_montante e avaliação criavam um cada).
    assert contador.chamadas == 2
    # Resultado inalterado: 15.000 × 1,149^(21/252) = 15.174,62
    # (10.116,42 + 5.058,21 somados sem arredondar antes).
    assert arredondar_moeda(geral.investimentos_brl) == D("15174.62")


def test_historico_e_serie_criam_um_fator_por_ativo(sessao: Session, contador: Contador) -> None:
    cenario(sessao)
    contador.chamadas = 0
    historico.consultar(sessao, FiltroHistorico())
    assert contador.chamadas == 1
    contador.chamadas = 0
    serie = serie_patrimonio(sessao, DATA_REF, DATA_REF)
    assert contador.chamadas == 1
    assert arredondar_moeda(serie.pontos[0].investimentos) == D("15174.62")
