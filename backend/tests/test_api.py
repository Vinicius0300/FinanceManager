"""API REST: fluxos completos pelo ``TestClient`` (sem rede; relógio fixo em 29/10/2026 14h).

Valores decimais trafegam como texto; erros seguem ``{codigo, mensagem, detalhes}`` em pt-BR.
"""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.registry import RegistroProviders
from tests.conftest import TOKEN_TESTE
from tests.test_coleta import CotacaoFalsa

SP = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 10, 29, 14, tzinfo=SP)
HOJE = "2026-10-29"
Json = dict[str, Any]


@pytest.fixture
def yahoo() -> CotacaoFalsa:
    falso = CotacaoFalsa("yfinance")
    falso.relogio = lambda: AGORA
    return falso


@pytest.fixture
def app_api(yahoo: CotacaoFalsa) -> FastAPI:
    providers = RegistroProviders()
    providers.registrar_cotacao(yahoo)
    settings = Settings(token=TOKEN_TESTE, dev=True, atualizacao_automatica=False)
    return create_app(settings, providers=providers, relogio=lambda: AGORA)


@pytest.fixture
def api(app_api: FastAPI) -> Iterator[TestClient]:
    with TestClient(app_api, headers={"Authorization": f"Bearer {TOKEN_TESTE}"}) as cliente:
        yield cliente


def criar(api: TestClient, caminho: str, corpo: Json, esperado: int = 201) -> Json:
    resposta = api.post(caminho, json=corpo)
    assert resposta.status_code == esperado, resposta.text
    dados: Json = resposta.json()
    return dados


def preparar(api: TestClient) -> tuple[int, int]:
    rico = criar(api, "/api/instituicoes", {"nome": "RICO", "tipo": "corretora"})
    criar(
        api,
        "/api/movimentos",
        {"instituicao_id": rico["id"], "tipo": "deposito", "data": "2026-10-01", "valor": "1000"},
    )
    petr = criar(api, "/api/ativos", {"tipo": "acao_br", "nome": "Petrobras", "simbolo": "petr4"})
    return rico["id"], petr["id"]


# ---------------------------------------------------------------- erros e autenticação


def test_todas_as_rotas_exigem_token(app_api: FastAPI) -> None:
    with TestClient(app_api) as sem_token:
        for caminho in ("/api/instituicoes", "/api/portfolio/resumo", "/api/eventos"):
            resposta = sem_token.get(caminho)
            assert resposta.status_code == 401
            assert resposta.json()["codigo"] == "nao_autorizado"
        assert sem_token.get("/health").status_code == 200


def test_validacao_em_pt_br_e_float_recusado(api: TestClient) -> None:
    resposta = api.post("/api/instituicoes", json={"tipo": "banco", "extra": 1})
    assert resposta.status_code == 422
    assert resposta.json() == {
        "codigo": "validacao",
        "mensagem": "Dados inválidos.",
        "detalhes": [
            {"campo": "nome", "mensagem": "Campo obrigatório."},
            {"campo": "extra", "mensagem": "Campo desconhecido."},
        ],
    }
    rico = criar(api, "/api/instituicoes", {"nome": "RICO", "tipo": "corretora"})
    corpo = {"instituicao_id": rico["id"], "tipo": "deposito", "data": "2026-10-01", "valor": 10.5}
    resposta = api.post("/api/movimentos", json=corpo)
    assert resposta.status_code == 422
    assert resposta.json()["detalhes"] == [
        {"campo": "valor", "mensagem": 'Informe o número como texto (ex.: "10.50").'}
    ]
    resposta = api.post("/api/movimentos", json={**corpo, "valor": "10,5", "data": "29/10/2026"})
    mensagens = {d["campo"]: d["mensagem"] for d in resposta.json()["detalhes"]}
    assert mensagens == {
        "data": "Data inválida. Use o formato AAAA-MM-DD.",
        "valor": "Número inválido (use ponto como separador decimal).",
    }
    resposta = api.get("/api/transacoes", params={"limite": 0})
    assert resposta.json()["detalhes"] == [
        {"campo": "limite", "mensagem": "Use um valor maior ou igual a 1."}
    ]


# ---------------------------------------------------------------- instituições e caixa


def test_crud_de_instituicoes_e_caixa(api: TestClient) -> None:
    rico = criar(api, "/api/instituicoes", {"nome": "RICO", "tipo": "corretora"})
    duplicada = api.post("/api/instituicoes", json={"nome": "rico", "tipo": "banco"})
    assert (duplicada.status_code, duplicada.json()["codigo"]) == (409, "conflito")
    editada = api.put(
        f"/api/instituicoes/{rico['id']}", json={"nome": "Rico CTVM", "tipo": "corretora"}
    )
    assert editada.json()["nome"] == "Rico CTVM"
    assert api.get("/api/instituicoes/999").status_code == 404

    deposito = criar(
        api,
        "/api/movimentos",
        {
            "instituicao_id": rico["id"],
            "tipo": "deposito",
            "data": "2026-10-01",
            "valor": "1000.50",
        },
    )
    criar(
        api,
        "/api/movimentos",
        {"instituicao_id": rico["id"], "tipo": "saque", "data": "2026-10-05", "valor": "200"},
    )
    saque_demais = api.post(
        "/api/movimentos",
        json={"instituicao_id": rico["id"], "tipo": "saque", "data": "2026-10-06", "valor": "900"},
    )
    assert saque_demais.status_code == 422
    assert saque_demais.json()["codigo"] == "saldo_insuficiente"
    contas = api.get("/api/contas").json()
    assert contas == [
        {
            "id": contas[0]["id"],
            "instituicao_id": rico["id"],
            "instituicao_nome": "Rico CTVM",
            "moeda": "BRL",
            "saldo": "800.50",
        }
    ]
    extrato = api.get(
        f"/api/instituicoes/{rico['id']}/extrato", params={"limite": 1, "deslocamento": 1}
    ).json()
    assert (extrato["total"], extrato["saldo_final"]) == (2, "800.50")
    assert [i["tipo"] for i in extrato["itens"]] == ["deposito"]  # o mais recente é o saque
    alterado = api.patch(f"/api/movimentos/{deposito['id']}", json={"valor": "1500"})
    assert alterado.json()["valor"] == "1500"
    sem_conta = api.get(f"/api/instituicoes/{rico['id']}/extrato", params={"moeda": "USD"})
    assert sem_conta.status_code == 404

    com_movimentos = api.delete(f"/api/instituicoes/{rico['id']}")
    assert com_movimentos.status_code == 422
    for movimento in api.get(f"/api/instituicoes/{rico['id']}/extrato").json()["itens"]:
        assert api.delete(f"/api/movimentos/{movimento['id']}").status_code == 204
    assert api.delete(f"/api/instituicoes/{rico['id']}").status_code == 204
    assert api.get("/api/instituicoes").json() == []


# ---------------------------------------------------------------- ativos


def test_tipos_de_ativo_e_crud_de_ativos(api: TestClient) -> None:
    tipos = {t["slug"]: t for t in api.get("/api/tipos-ativo").json()}
    assert set(tipos) == {
        "acao_br",
        "acao_us",
        "cripto",
        "etf_br",
        "etf_us",
        "fundo",
        "fundo_listado",
        "poupanca",
        "renda_fixa",
        "tesouro_direto",
    }
    assert tipos["tesouro_direto"]["aceita_taxas"] is False
    assert tipos["fundo_listado"]["lista_simbolos"] == "B3"
    assert tipos["cripto"]["busca_por_ticker"] is True
    assert tipos["renda_fixa"]["busca_por_ticker"] is False
    assert api.get("/api/tipos-ativo/fii").json()["codigo"] == "validacao"

    tesouro = criar(
        api,
        "/api/ativos",
        {
            "tipo": "tesouro_direto",
            "nome": "Tesouro IPCA+ 2035",
            "metadados": {"titulo": "ipca_juros", "vencimento": "2035-05-15"},
        },
    )
    assert (tesouro["provider"], tesouro["moeda"]) == ("tesouro", "BRL")
    invalido = api.post(
        "/api/ativos", json={"tipo": "tesouro_direto", "nome": "X", "metadados": {}}
    )
    assert {d["campo"] for d in invalido.json()["detalhes"]} == {"titulo", "vencimento"}

    editado = api.put(
        f"/api/ativos/{tesouro['id']}",
        json={
            "nome": "IPCA+ 2035",
            "metadados": {"titulo": "ipca_juros", "vencimento": "2035-05-15"},
        },
    )
    assert editado.json()["nome"] == "IPCA+ 2035"
    assert [a["id"] for a in api.get("/api/ativos", params={"tipo": "tesouro_direto"}).json()] == [
        tesouro["id"]
    ]
    assert api.delete(f"/api/ativos/{tesouro['id']}").status_code == 204
    assert api.get(f"/api/ativos/{tesouro['id']}").status_code == 404


def test_cadastro_de_ativo_cotado_dispara_a_coleta(api: TestClient, yahoo: CotacaoFalsa) -> None:
    yahoo.precos[1] = Decimal("52.2")
    petr = criar(api, "/api/ativos", {"tipo": "acao_br", "nome": "Petrobras", "simbolo": "PETR4"})
    assert petr["id"] == 1
    # A tarefa em segundo plano roda depois da resposta; o TestClient espera por ela.
    status = api.get(f"/api/ativos/{petr['id']}/status").json()
    for _ in range(50):
        if status["ultimo_sucesso"]:
            break
        status = api.get(f"/api/ativos/{petr['id']}/status").json()
    assert status["valor"] == "52.2"
    assert (status["origem"], status["provider_preco"], status["defasado"]) == (
        "automatico",
        "yfinance",
        False,
    )
    assert yahoo.chamadas_historico == [[(1, date(2025, 10, 29))]]


# ---------------------------------------------------------------- transações


def test_compra_maior_que_o_saldo_responde_409_e_confirmacao_grava_ajuste(
    api: TestClient,
) -> None:
    rico, petr = preparar(api)
    compra = {
        "ativo_id": petr,
        "instituicao_id": rico,
        "tipo": "compra",
        "data": "2026-10-10",
        "quantidade": "100",
        "preco_unitario": "12.345",
        "taxas": "1.00",
    }
    resposta = api.post("/api/transacoes", json=compra)
    assert resposta.status_code == 409
    erro = resposta.json()
    assert erro["codigo"] == "saldo_insuficiente"
    # 100 × 12,345 + 1,00 = 1.235,50; saldo 1.000,00 → faltam 235,50
    assert erro["mensagem"].startswith(
        "Saldo insuficiente em RICO (BRL) em 10/10/2026: faltam 235,50 BRL."
    )
    assert erro["detalhes"] == [
        {"campo": "instituicao_id", "mensagem": str(rico)},
        {"campo": "instituicao", "mensagem": "RICO"},
        {"campo": "moeda", "mensagem": "BRL"},
        {"campo": "data", "mensagem": "2026-10-10"},
        {"campo": "valor_faltante", "mensagem": "235.50"},
    ]
    assert api.get("/api/transacoes").json()["total"] == 0  # nada gravado

    gravada = criar(api, "/api/transacoes", {**compra, "aceitar_ajuste": True})
    assert sorted((m["tipo"], m["valor"]) for m in gravada["movimentos"]) == [
        ("ajuste_saldo", "235.50"),
        ("debito_compra", "1235.50"),
    ]
    assert api.get("/api/contas").json()[0]["saldo"] == "0.00"

    # Edição: menos quantidade dispensa o ajuste (refeito do zero).
    editada = api.put(f"/api/transacoes/{gravada['id']}", json={**compra, "quantidade": "50"})
    assert editada.status_code == 200, editada.text
    assert editada.json()["id"] == gravada["id"]
    assert [(m["tipo"], m["valor"]) for m in editada.json()["movimentos"]] == [
        ("debito_compra", "618.25")
    ]
    venda = criar(
        api,
        "/api/transacoes",
        {
            "ativo_id": petr,
            "instituicao_id": rico,
            "tipo": "venda",
            "data": "2026-10-20",
            "quantidade": "50",
            "preco_unitario": "13",
        },
    )
    reduzir = api.put(f"/api/transacoes/{gravada['id']}", json={**compra, "quantidade": "10"})
    assert reduzir.status_code == 422
    assert reduzir.json()["mensagem"].startswith("Não é possível alterar esta transação")
    trocar_ativo = api.put(f"/api/transacoes/{gravada['id']}", json={**compra, "ativo_id": 999})
    assert trocar_ativo.status_code == 422

    lista = api.get("/api/transacoes", params={"tipo": "compra", "ativo_id": petr}).json()
    assert [t["id"] for t in lista["itens"]] == [gravada["id"]]
    pagina = api.get("/api/transacoes", params={"limite": 1}).json()
    assert (pagina["total"], pagina["itens"][0]["id"]) == (2, venda["id"])
    assert api.delete(f"/api/transacoes/{gravada['id']}").status_code == 422  # sustenta a venda
    assert api.delete(f"/api/transacoes/{venda['id']}").status_code == 204
    assert api.get(f"/api/transacoes/{venda['id']}").status_code == 404


def test_eventos_corporativos(api: TestClient) -> None:
    rico, petr = preparar(api)
    criar(
        api,
        "/api/transacoes",
        {
            "ativo_id": petr,
            "instituicao_id": rico,
            "tipo": "compra",
            "data": "2026-10-02",
            "quantidade": "10",
            "preco_unitario": "10",
        },
    )
    corpo = {
        "ativo_id": petr,
        "tipo": "desdobramento",
        "data": "2026-10-05",
        "proporcao_de": 1,
        "proporcao_para": 2,
    }
    evento = criar(api, "/api/eventos-corporativos", corpo)
    assert api.post("/api/eventos-corporativos", json=corpo).status_code == 409
    editado = api.put(
        f"/api/eventos-corporativos/{evento['id']}", json={**corpo, "proporcao_para": 3}
    )
    assert editado.json()["proporcao_para"] == 3
    posicoes = api.get("/api/portfolio/posicoes").json()
    assert posicoes[0]["quantidade"] == "30"
    assert [e["id"] for e in api.get("/api/eventos-corporativos").json()] == [evento["id"]]
    assert api.delete(f"/api/eventos-corporativos/{evento['id']}").status_code == 204


# ---------------------------------------------------------------- preços, status e indicadores


def test_precos_manuais_historico_e_status(api: TestClient) -> None:
    _, petr = preparar(api)
    manual = criar(api, f"/api/ativos/{petr}/precos", {"data": HOJE, "valor": "50.5"})
    assert (manual["origem"], manual["provider"], manual["data"]) == ("manual", None, HOJE)
    ontem = criar(api, f"/api/ativos/{petr}/precos", {"data": "2026-10-28", "valor": "49"})
    assert ontem["data_hora"] == "2026-10-28T21:00:00Z"  # fechamento às 18h de Brasília
    futuro = api.post(f"/api/ativos/{petr}/precos", json={"data": "2026-10-30", "valor": "1"})
    assert futuro.status_code == 422
    historico = api.get(f"/api/ativos/{petr}/precos").json()
    assert [p["data"] for p in historico["itens"]] == [HOJE, "2026-10-28"]
    status = api.get("/api/cotacoes/status").json()
    assert status[0]["valor"] == "50.5"
    assert status[0]["origem"] == "manual"
    assert api.delete(f"/api/precos/{manual['id']}").status_code == 204

    poupanca = criar(api, "/api/ativos", {"tipo": "poupanca", "nome": "Poupança"})
    recusado = api.post(f"/api/ativos/{poupanca['id']}/precos", json={"data": HOJE, "valor": "1"})
    assert recusado.status_code == 422
    status_poupanca = api.get(f"/api/ativos/{poupanca['id']}/status").json()
    assert (status_poupanca["origem"], status_poupanca["defasado"]) == ("calculado", True)


def test_indicadores(api: TestClient) -> None:
    cdi = criar(api, "/api/indicadores", {"tipo": "cdi", "data": "2026-10-28", "valor": "13.65"})
    assert cdi["fonte"] == "manual"
    assert (
        api.post(
            "/api/indicadores", json={"tipo": "cdi", "data": "2026-10-28", "valor": "13.65"}
        ).status_code
        == 409
    )
    criar(
        api,
        "/api/indicadores",
        {"tipo": "cambio", "moeda": "USD", "data": "2026-10-28", "valor": "5.3655"},
    )
    assert (
        api.put(f"/api/indicadores/{cdi['id']}", json={"valor": "13.66"}).json()["valor"] == "13.66"
    )
    cambio = api.get("/api/indicadores", params={"tipo": "cambio", "moeda": "usd"}).json()
    assert [(i["valor"], i["moeda"]) for i in cambio] == [("5.3655", "USD")]
    assert api.delete(f"/api/indicadores/{cdi['id']}").status_code == 204
    assert len(api.get("/api/indicadores").json()) == 1


# ---------------------------------------------------------------- portfólio


def test_portfolio_geral_e_por_instituicao(api: TestClient) -> None:
    rico, petr = preparar(api)
    nubank = criar(api, "/api/instituicoes", {"nome": "Nubank", "tipo": "banco"})
    criar(
        api,
        "/api/movimentos",
        {"instituicao_id": nubank["id"], "tipo": "deposito", "data": "2026-10-01", "valor": "500"},
    )
    criar(
        api,
        "/api/transacoes",
        {
            "ativo_id": petr,
            "instituicao_id": rico,
            "tipo": "compra",
            "data": "2026-10-02",
            "quantidade": "10",
            "preco_unitario": "40",
        },
    )
    criar(api, f"/api/ativos/{petr}/precos", {"data": "2026-10-28", "valor": "50"})
    criar(api, f"/api/ativos/{petr}/precos", {"data": HOJE, "valor": "52.5"})

    resumo = api.get("/api/portfolio/resumo").json()
    # Geral: PETR4 10 × 52,50 = 525; caixa 600 (RICO) + 500 (Nubank)
    assert (resumo["investimentos_brl"], resumo["caixa_brl"], resumo["patrimonio_brl"]) == (
        "525.00",
        "1100.00",
        "1625.00",
    )
    # Variação do dia: 10 × (52,50 − 50) = 25 sobre 500 = 5%
    assert (resumo["variacao_dia_brl"], resumo["variacao_dia"]) == ("25.00", "0.05")
    # Rentabilidade: (525 − 400) / 400 = 31,25%
    assert resumo["rentabilidade"]["rentabilidade_total"] == "0.3125"
    por_rico = api.get("/api/portfolio/resumo", params={"instituicao_id": rico}).json()
    assert por_rico["patrimonio_brl"] == "1125.00"
    assert api.get("/api/portfolio/resumo", params={"instituicao_id": 999}).status_code == 404

    posicoes = api.get("/api/portfolio/posicoes").json()
    assert len(posicoes) == 1
    posicao = posicoes[0]
    assert (posicao["quantidade"], posicao["preco_medio"], posicao["preco_atual"]) == (
        "10",
        "40",
        "52.5",
    )
    assert posicao["participacao"] == "0.32307692"  # 525 / 1625
    assert posicao["variacao_dia"]["variacao"] == "0.05"
    alocacao = api.get("/api/portfolio/alocacao").json()
    assert [(f["grupo"], f["valor"]) for f in alocacao] == [
        ("caixa", "1100.00"),
        ("acao_br", "525.00"),
    ]
    assert len(api.get("/api/portfolio/maiores", params={"limite": 1}).json()) == 1
    variacao = api.get("/api/portfolio/variacao-dia").json()
    assert variacao["ativos"][0]["variacao"]["variacao_brl"] == "25.00"
    rentabilidade = api.get("/api/portfolio/rentabilidade").json()
    assert rentabilidade["ativos"][0]["metricas_brl"]["lucro_nao_realizado"] == "125.00"
    instituicoes = api.get("/api/portfolio/instituicoes").json()
    assert [(i["nome"], i["patrimonio_brl"]) for i in instituicoes] == [
        ("Nubank", "500.00"),
        ("RICO", "1125.00"),
    ]

    evolucao = api.get("/api/portfolio/evolucao", params={"inicio": "2026-10-27"}).json()
    assert [(p["data"], p["patrimonio"]) for p in evolucao["pontos"]] == [
        ("2026-10-27", "1500.00"),  # sem preço: custo (400) + caixa (1.100)
        ("2026-10-28", "1600.00"),
        ("2026-10-29", "1625.00"),
    ]
    longa = api.get("/api/portfolio/evolucao", params={"inicio": "2025-01-01"})
    assert longa.status_code == 422
    assert longa.json()["mensagem"] == "O período máximo da evolução é de 1 ano."
    padrao = api.get("/api/portfolio/evolucao", params={"instituicao_id": nubank["id"]}).json()
    assert padrao["pontos"][0]["data"] == "2025-10-29"
    assert padrao["pontos"][-1]["patrimonio"] == "500.00"


# ---------------------------------------------------------------- receitas e despesas


def test_categorias_lancamentos_e_resumo_mensal(api: TestClient) -> None:
    salario = criar(api, "/api/categorias", {"nome": "Salário", "tipo": "receita"})
    mercado = criar(api, "/api/categorias", {"nome": "Mercado", "tipo": "despesa"})
    assert (
        api.put(f"/api/categorias/{mercado['id']}", json={"nome": "Supermercado"}).json()["nome"]
        == "Supermercado"
    )
    criar(
        api,
        "/api/lancamentos",
        {
            "tipo": "receita",
            "data": "2026-10-05",
            "descricao": "Salário",
            "valor": "5000",
            "categoria_id": salario["id"],
        },
    )
    compra = criar(
        api,
        "/api/lancamentos",
        {
            "tipo": "despesa",
            "data": "2026-10-10",
            "descricao": "Compras",
            "valor": "750.40",
            "categoria_id": mercado["id"],
        },
    )
    errada = api.post(
        "/api/lancamentos",
        json={
            "tipo": "despesa",
            "data": "2026-10-10",
            "descricao": "X",
            "valor": "1",
            "categoria_id": salario["id"],
        },
    )
    assert errada.status_code == 422
    editado = api.put(
        f"/api/lancamentos/{compra['id']}",
        json={
            "tipo": "despesa",
            "data": "2026-10-11",
            "descricao": "Feira",
            "valor": "1000",
            "categoria_id": mercado["id"],
        },
    )
    assert (editado.json()["descricao"], editado.json()["categoria_nome"]) == (
        "Feira",
        "Supermercado",
    )
    resumo = api.get("/api/resumo-mensal", params={"ano": 2026, "mes": 10}).json()
    assert (resumo["total_receitas"], resumo["total_despesas"], resumo["saldo"]) == (
        "5000.00",
        "1000.00",
        "4000.00",
    )
    assert {c["categoria_nome"]: c["percentual"] for c in resumo["por_categoria"]} == {
        "Salário": "1",
        "Supermercado": "1",
    }
    assert api.get("/api/resumo-mensal", params={"ano": 2026, "mes": 13}).status_code == 422
    pagina = api.get("/api/lancamentos", params={"tipo": "despesa"}).json()
    assert pagina["total"] == 1
    assert api.delete(f"/api/categorias/{mercado['id']}").status_code == 422
    assert api.delete(f"/api/lancamentos/{compra['id']}").status_code == 204
    assert api.delete(f"/api/categorias/{mercado['id']}").status_code == 204
    assert [c["nome"] for c in api.get("/api/categorias", params={"tipo": "receita"}).json()] == [
        "Salário"
    ]


# ---------------------------------------------------------------- configurações e atualização


def test_configuracoes(api: TestClient) -> None:
    assert api.get("/api/configuracoes").json() == {"intervalo_atualizacao_min": 5}
    assert api.put("/api/configuracoes", json={"intervalo_atualizacao_min": 10}).json() == {
        "intervalo_atualizacao_min": 10
    }
    invalido = api.put("/api/configuracoes", json={"intervalo_atualizacao_min": 20})
    assert invalido.status_code == 422
    assert (
        invalido.json()["mensagem"] == "O intervalo deve ser um número inteiro de 1 a 15 minutos."
    )
    assert api.get("/api/configuracoes").json() == {"intervalo_atualizacao_min": 10}


def test_atualizacao_forcada(api: TestClient, app_api: FastAPI, yahoo: CotacaoFalsa) -> None:
    _, petr = preparar(api)
    yahoo.precos[petr] = Decimal("52.2")
    estado = api.get("/api/cotacoes/atualizacao").json()
    assert estado["ultimo_ciclo_inicio"] is None
    resposta = api.post("/api/cotacoes/atualizar")
    assert resposta.status_code == 202
    for _ in range(50):
        estado = api.get("/api/cotacoes/atualizacao").json()
        if estado["ultimo_ciclo_fim"]:
            break
    assert estado["precos_atualizados"] >= 1
    assert estado["em_andamento"] is False


def test_atualizacao_forcada_recusada_se_ja_houver_uma(api: TestClient, app_api: FastAPI) -> None:
    agendador = app_api.state.agendador

    async def ocupar() -> None:
        await agendador._trava.acquire()

    async def liberar() -> None:
        agendador._trava.release()

    api.portal.call(ocupar)  # type: ignore[union-attr]
    try:
        resposta = api.post("/api/cotacoes/atualizar")
        assert resposta.status_code == 409
        assert resposta.json() == {
            "codigo": "atualizacao_em_andamento",
            "mensagem": "Já existe uma atualização em andamento.",
        }
    finally:
        api.portal.call(liberar)  # type: ignore[union-attr]


# ---------------------------------------------------------------- backup


def test_backup_e_restauracao(api: TestClient) -> None:
    preparar(api)
    backup = criar(api, "/api/backups", {})
    assert backup["nome"].endswith("-manual.db")
    criar(api, "/api/instituicoes", {"nome": "Depois do backup", "tipo": "outro"})
    assert len(api.get("/api/instituicoes").json()) == 2

    assert api.post("/api/backups/restaurar", json={"nome": "../financas.db"}).status_code == 404
    assert api.post("/api/backups/restaurar", json={}).status_code == 422
    restaurado = api.post("/api/backups/restaurar", json={"nome": backup["nome"]})
    assert restaurado.status_code == 200, restaurado.text
    assert restaurado.json()["backup_seguranca"]["nome"].endswith("-pre-restauracao.db")
    assert [i["nome"] for i in api.get("/api/instituicoes").json()] == ["RICO"]
    nomes = {b["nome"] for b in api.get("/api/backups").json()}
    assert backup["nome"] in nomes
    assert any(n.endswith("-pre-restauracao.db") for n in nomes)


def test_restaurar_arquivo_que_nao_e_do_financas(api: TestClient, tmp_path: Any) -> None:
    import sqlite3

    estranho = tmp_path / "outro.db"
    with sqlite3.connect(estranho) as conexao:
        conexao.execute("CREATE TABLE x (a INTEGER)")
    resposta = api.post("/api/backups/restaurar", json={"caminho": str(estranho)})
    assert resposta.status_code == 422
    assert resposta.json()["mensagem"] == "O arquivo não é um backup do Finanças."
    texto = tmp_path / "texto.db"
    texto.write_text("não é sqlite", encoding="utf-8")
    resposta = api.post("/api/backups/restaurar", json={"caminho": str(texto)})
    assert resposta.json()["mensagem"] == "O arquivo escolhido não é um banco de dados válido."
    assert api.post("/api/backups/restaurar", json={"caminho": "relativo.db"}).status_code == 404
