"""Situação da cotação de cada ativo (chip e painel de status da barra superior).

Relógio fixo: "hoje" é 29/10/2026. Tolerância de defasagem: 4 dias (cripto: 1 dia).
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import TipoIndicador, TipoTransacao
from app.domain.situacao_cotacao import SituacaoCotacao, classificar_situacao
from app.repositories import modelos as m
from app.repositories.mercado import RepositorioEstadosColeta
from app.services.coleta import chave_ativo
from app.services.status_cotacoes import AVISO_MANUAL, status_ativo, status_ativos
from tests.fabricas import acao_br, cdb, deposito, indicador, instituicao, montante, preco

HOJE = date(2026, 10, 29)

# ---------------------------------------------------------------- domínio (função pura)


@pytest.mark.parametrize(
    ("ultimo_erro", "sem_fonte", "defasado", "esperado"),
    [
        (None, False, False, SituacaoCotacao.EM_DIA),
        (None, False, True, SituacaoCotacao.DEFASADO),
        ("HTTP 503", False, False, SituacaoCotacao.COM_ERRO),
        ("HTTP 503", False, True, SituacaoCotacao.COM_ERRO),  # erro vence defasado
        (None, True, True, SituacaoCotacao.MANUAL),  # manual antigo não conta como defasado
        (None, True, False, SituacaoCotacao.MANUAL),
        ("Fonte fora do ar", True, True, SituacaoCotacao.COM_ERRO),  # erro vence manual
        ("", False, True, SituacaoCotacao.DEFASADO),  # erro vazio não é erro
    ],
)
def test_prioridade_erro_manual_defasado_em_dia(
    ultimo_erro: str | None, sem_fonte: bool, defasado: bool, esperado: SituacaoCotacao
) -> None:
    situacao = classificar_situacao(
        ultimo_erro=ultimo_erro, sem_fonte_automatica=sem_fonte, defasado=defasado
    )
    assert situacao is esperado


# ---------------------------------------------------------------- serviço


def _erro(sessao: Session, ativo: m.Ativo, mensagem: str) -> None:
    estado = RepositorioEstadosColeta(sessao).obter_ou_criar(chave_ativo(ativo.id), ativo.id)
    estado.ultima_tentativa = datetime(2026, 10, 29, 17, tzinfo=UTC)
    estado.ultimo_erro = mensagem


def _por_id(sessao: Session) -> dict[int, SituacaoCotacao]:
    return {s.ativo_id: s.situacao for s in status_ativos(sessao, HOJE)}


def test_situacao_de_cada_ativo(sessao: Session) -> None:
    em_dia = acao_br(sessao, "PETR4")
    preco(sessao, em_dia, date(2026, 10, 28), "38.45")  # 1 dia: dentro dos 4

    defasado = acao_br(sessao, "IVVB11")
    preco(sessao, defasado, date(2026, 10, 24), "389.12")  # 5 dias: acima dos 4

    sem_preco = acao_br(sessao, "VALE3")  # sem cotação: usa o PM (defasado)

    com_erro = acao_br(sessao, "MXRF11")
    preco(sessao, com_erro, date(2026, 10, 28), "9.87")
    _erro(sessao, com_erro, "Ticker não encontrado na fonte.")

    manual = acao_br(sessao, "CPA3")
    manual.provider = None  # sem fonte automática (ex.: papel fora da lista)
    preco(sessao, manual, date(2026, 3, 1), "12")  # 8 meses: idade não importa
    sessao.flush()

    assert _por_id(sessao) == {
        em_dia.id: SituacaoCotacao.EM_DIA,
        defasado.id: SituacaoCotacao.DEFASADO,
        sem_preco.id: SituacaoCotacao.DEFASADO,
        com_erro.id: SituacaoCotacao.COM_ERRO,
        manual.id: SituacaoCotacao.MANUAL,
    }

    item = status_ativo(sessao, manual.id, HOJE)
    # ``defasado`` continua dizendo a idade do preço; o aviso explica a situação manual.
    assert (item.defasado, item.aviso, item.data) == (True, AVISO_MANUAL, date(2026, 3, 1))
    assert (item.simbolo, item.moeda) == ("CPA3", "BRL")


def test_renda_fixa_segue_o_indicador_e_nunca_e_manual(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "5000", date(2026, 1, 5))
    titulo = cdb(sessao, "cdi", aplicacao=date(2026, 1, 5))
    montante(sessao, titulo, rico, TipoTransacao.APORTE, date(2026, 1, 5), "1000")
    # Sem CDI recente: defasado pelo indicador.
    assert _por_id(sessao)[titulo.id] is SituacaoCotacao.DEFASADO
    indicador(sessao, TipoIndicador.CDI, date(2026, 10, 28), "13.65")
    assert _por_id(sessao)[titulo.id] is SituacaoCotacao.EM_DIA
