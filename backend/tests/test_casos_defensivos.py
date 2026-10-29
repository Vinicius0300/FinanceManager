"""Ramos defensivos: entradas que as camadas superiores já impedem, mas que não podem passar."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import sqlite

from app.asset_types.base import HandlerTipoAtivo, ModoPosicao, ler_decimal
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.carteira import Avaliacao, PosicaoAvaliada
from app.domain.enums import TipoTransacao
from app.domain.posicao import ValoresPosicao
from app.repositories import modelos as m
from app.repositories.tipos import DataHoraUTC, DecimalTexto
from app.services.posicoes import operacao_cotas, operacao_montante

DIALETO = sqlite.dialect()


def test_tipos_de_coluna_com_nulos_e_valores_inesperados() -> None:
    decimal = DecimalTexto()
    assert decimal.process_bind_param(None, DIALETO) is None
    assert decimal.process_result_value(None, DIALETO) is None
    with pytest.raises(TypeError, match="tipo inesperado"):
        decimal.process_result_value(1.5, DIALETO)
    data_hora = DataHoraUTC()
    assert data_hora.process_bind_param(None, DIALETO) is None
    assert data_hora.process_result_value(None, DIALETO) is None


def test_metadado_com_tipo_inesperado() -> None:
    with pytest.raises(TypeError, match="Metadado taxa"):
        ler_decimal({"taxa": 1.5}, "taxa")


def _transacao(tipo: TipoTransacao, **campos: object) -> m.Transacao:
    return m.Transacao(
        tipo=tipo,
        data=date(2025, 1, 1),
        taxas=Decimal(0),
        cambio=Decimal(1),
        imposto_retido=Decimal(0),
        **campos,
    )


def test_conversao_de_transacoes_rejeita_tipo_ou_campo_errado() -> None:
    with pytest.raises(ValueError, match="não pertence a posição em cotas"):
        operacao_cotas(_transacao(TipoTransacao.APORTE, valor=Decimal(1)))
    with pytest.raises(ValueError, match="não pertence a posição por montante"):
        operacao_montante(
            _transacao(TipoTransacao.COMPRA, quantidade=Decimal(1), preco_unitario=Decimal(1))
        )
    with pytest.raises(ValueError, match="sem um campo obrigatório"):
        operacao_cotas(_transacao(TipoTransacao.COMPRA, preco_unitario=Decimal(1)))


def test_registro_exige_um_dos_modos_de_posicao() -> None:
    class SemModo(HandlerTipoAtivo):
        slug = "sem_modo"
        nome = "Sem modo"
        descricao = "Handler que não herda de HandlerCotado nem de HandlerMontante."
        modo = ModoPosicao.COTAS
        moedas_aceitas = ("BRL",)
        tipos_transacao = frozenset({TipoTransacao.COMPRA})

    with pytest.raises(ValueError, match="deve herdar de HandlerCotado ou HandlerMontante"):
        RegistroTiposAtivo().registrar(SemModo())
    assert SemModo().indicadores_necessarios({}) == frozenset()


def test_metricas_ficam_vazias_sem_valor_avaliado() -> None:
    posicao = PosicaoAvaliada(
        ativo_id=1,
        tipo_ativo="acao_br",
        moeda="BRL",
        instituicao_id=1,
        quantidade=Decimal(1),
        valores=ValoresPosicao(),
        valores_brl=ValoresPosicao(),
        avaliacao=Avaliacao(valor=None, valor_brl=None, erro="falha"),
    )
    assert posicao.metricas is None
    assert posicao.metricas_brl is None


def test_erros_http_e_de_validacao_da_api(
    cliente: TestClient, cabecalho_auth: dict[str, str]
) -> None:
    inexistente = cliente.get("/nao-existe", headers=cabecalho_auth)
    assert inexistente.status_code == 404
    assert inexistente.json() == {"codigo": "http_404", "mensagem": "Recurso não encontrado."}
