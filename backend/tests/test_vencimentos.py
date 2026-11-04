"""Próximos vencimentos (Parte 5A): seleção e ordem no service e a rota de leitura.

Cenário (referência 29/10/2026):
- RICO: CDB que venceu ontem (28/10/2026) → fora; CDB que vence hoje → dentro;
  Tesouro IPCA+ 15/05/2029 → dentro; CDB Banco X 02/01/2030 → dentro;
  Tesouro Selic vendido inteiro → fora (posição zerada); ação → fora (não vence).
- Nubank: CDB Banco Y 02/01/2030 → dentro (empata com o Banco X: desempate pelo nome).

Ordem esperada na Análise Geral: hoje, IPCA+ 2029, Banco X 2030, Banco Y 2030.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import TipoIndicador, TipoTransacao
from app.domain.erros import NaoEncontradoError
from app.repositories import modelos as m
from app.services.cadastros import NovoAtivo, criar_ativo
from app.services.portfolio import Vencimento, listar_vencimentos
from tests.fabricas import (
    acao_br,
    cdb,
    compra,
    deposito,
    indicador,
    instituicao,
    montante,
    venda,
)
from tests.test_api import api, app_api, criar, yahoo  # noqa: F401 - fixtures reutilizadas

HOJE = date(2026, 10, 29)


def tesouro(sessao: Session, titulo: str, vencimento: date, nome: str) -> m.Ativo:
    return criar_ativo(
        sessao,
        NovoAtivo(
            tipo="tesouro_direto",
            nome=nome,
            metadados={"titulo": titulo, "vencimento": vencimento.isoformat()},
        ),
    )


def cenario(sessao: Session) -> tuple[m.Instituicao, m.Instituicao]:
    rico = instituicao(sessao, "RICO")
    nubank = instituicao(sessao, "Nubank")
    deposito(sessao, rico, "10000", date(2025, 8, 1))
    deposito(sessao, nubank, "10000", date(2025, 8, 1))
    # Sem CDI a renda fixa não é avaliada (e não aparece como posição aberta).
    indicador(sessao, TipoIndicador.CDI, date(2025, 7, 31), "14.9")
    aporte = TipoTransacao.APORTE
    ontem = cdb(sessao, vencimento=date(2026, 10, 28), nome="CDB Venceu Ontem")
    hoje = cdb(sessao, vencimento=HOJE, nome="CDB Vence Hoje")
    banco_x = cdb(sessao, nome="CDB Banco X")
    banco_y = cdb(sessao, nome="CDB Banco Y")
    montante(sessao, ontem, rico, aporte, date(2025, 8, 1), "1000")
    montante(sessao, hoje, rico, aporte, date(2025, 8, 1), "1000")
    montante(sessao, banco_x, rico, aporte, date(2025, 8, 1), "1000")
    montante(sessao, banco_y, nubank, aporte, date(2025, 8, 1), "1000")
    ipca = tesouro(sessao, "ipca", date(2029, 5, 15), "Tesouro IPCA+ 2029")
    selic = tesouro(sessao, "selic", date(2031, 3, 1), "Tesouro Selic 2031")
    compra(sessao, ipca, rico, date(2025, 9, 1), "1", "3000")
    compra(sessao, selic, rico, date(2025, 9, 1), "1", "15000", aceitar_ajuste=True)
    venda(sessao, selic, rico, date(2025, 10, 1), "1", "15100")
    compra(sessao, acao_br(sessao), rico, date(2025, 9, 1), "10", "40")
    return rico, nubank


def nomes(vencimentos: list[Vencimento]) -> list[tuple[str, date]]:
    return [(v.item.ativo.nome, v.vencimento) for v in vencimentos]


def test_vencimentos_na_analise_geral(sessao: Session) -> None:
    cenario(sessao)
    assert nomes(listar_vencimentos(sessao, HOJE)) == [
        ("CDB Vence Hoje", HOJE),
        ("Tesouro IPCA+ 2029", date(2029, 5, 15)),
        ("CDB Banco X", date(2030, 1, 2)),
        ("CDB Banco Y", date(2030, 1, 2)),
    ]


def test_vencimentos_com_limite_e_por_instituicao(sessao: Session) -> None:
    rico, nubank = cenario(sessao)
    assert [n for n, _ in nomes(listar_vencimentos(sessao, HOJE, limite=2))] == [
        "CDB Vence Hoje",
        "Tesouro IPCA+ 2029",
    ]
    assert nomes(listar_vencimentos(sessao, HOJE, nubank.id)) == [("CDB Banco Y", date(2030, 1, 2))]
    assert len(listar_vencimentos(sessao, HOJE, rico.id)) == 3
    with pytest.raises(NaoEncontradoError):
        listar_vencimentos(sessao, HOJE, 999)


def test_vencimentos_sem_titulos(sessao: Session) -> None:
    rico = instituicao(sessao)
    deposito(sessao, rico, "1000", date(2025, 8, 1))
    assert listar_vencimentos(sessao, HOJE) == []


def test_rota_de_vencimentos(api: TestClient) -> None:  # noqa: F811
    rico = criar(api, "/api/instituicoes", {"nome": "RICO", "tipo": "corretora"})
    criar(
        api,
        "/api/movimentos",
        {"instituicao_id": rico["id"], "tipo": "deposito", "data": "2026-01-02", "valor": "5000"},
    )
    titulo = criar(
        api,
        "/api/ativos",
        {
            "tipo": "tesouro_direto",
            "nome": "Tesouro IPCA+ 2029",
            "metadados": {"titulo": "ipca", "vencimento": "2029-05-15"},
        },
    )
    criar(
        api,
        "/api/transacoes",
        {
            "ativo_id": titulo["id"],
            "instituicao_id": rico["id"],
            "tipo": "compra",
            "data": "2026-01-05",
            "quantidade": "1",
            "preco_unitario": "3000",
        },
    )
    criar(api, f"/api/ativos/{titulo['id']}/precos", {"data": "2026-10-29", "valor": "3210.555"})

    resposta = api.get("/api/portfolio/vencimentos")
    assert resposta.status_code == 200
    assert resposta.json() == [
        {
            "ativo_id": titulo["id"],
            "nome": "Tesouro IPCA+ 2029",
            "simbolo": None,
            "tipo": "tesouro_direto",
            "instituicao_id": None,
            "vencimento": "2029-05-15",
            "valor_brl": "3210.56",  # 1 × 3.210,555 arredondado na saída (2 casas)
            "defasado": False,
            "aviso": None,
        }
    ]
    por_rico = api.get("/api/portfolio/vencimentos", params={"instituicao_id": rico["id"]})
    assert por_rico.json()[0]["instituicao_id"] == rico["id"]
    assert api.get("/api/portfolio/vencimentos", params={"instituicao_id": 999}).status_code == 404
    assert api.get("/api/portfolio/vencimentos", params={"limite": 0}).status_code == 422
    # Referência depois do vencimento: nada a vencer.
    assert api.get("/api/portfolio/vencimentos", params={"data": "2029-05-16"}).json() == []
