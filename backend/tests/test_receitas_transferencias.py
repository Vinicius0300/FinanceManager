"""Parte 8: receitas e despesas por instituição e transferências entre instituições.

Os testes passam pela API (como o front usa) e conferem o caixa pelo extrato. Todas as
contas estão feitas à mão no comentário de cada teste. Datas em novembro de 2026.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.migracoes import configuracao_alembic
from app.domain.enums import TipoInstituicao, TipoLancamento, TipoMovimento
from app.main import create_app
from app.providers.registry import RegistroProviders
from app.repositories import modelos as m
from tests.conftest import TOKEN_TESTE

Json = dict[str, Any]


def dois(valor: str) -> str:
    """Valor da API (sem zeros à direita) com 2 casas, para comparar com o esperado."""
    return f"{Decimal(valor):.2f}"


FIM_DO_MES = "2026-11-30"


@pytest.fixture
def app_api() -> FastAPI:
    settings = Settings(token=TOKEN_TESTE, dev=True, atualizacao_automatica=False)
    return create_app(settings, providers=RegistroProviders())


@pytest.fixture
def api(app_api: FastAPI) -> Iterator[TestClient]:
    with TestClient(app_api, headers={"Authorization": f"Bearer {TOKEN_TESTE}"}) as cliente:
        yield cliente


def instituicao(api: TestClient, nome: str) -> int:
    resposta = api.post("/api/instituicoes", json={"nome": nome, "tipo": "banco"})
    assert resposta.status_code == 201, resposta.text
    identificador: int = resposta.json()["id"]
    return identificador


def deposito(api: TestClient, inst: int, data: str, valor: str, moeda: str = "BRL") -> None:
    resposta = api.post(
        "/api/movimentos",
        json={
            "instituicao_id": inst,
            "tipo": "deposito",
            "data": data,
            "valor": valor,
            "moeda": moeda,
        },
    )
    assert resposta.status_code == 201, resposta.text


def lancar(api: TestClient, tipo: str, data: str, valor: str, inst: int, **campos: Any) -> Any:
    corpo = {
        "tipo": tipo,
        "data": data,
        "descricao": campos.pop("descricao", tipo),
        "valor": valor,
        "instituicao_id": inst,
        **campos,
    }
    return api.post("/api/lancamentos", json=corpo)


def criado(resposta: Any) -> Json:
    assert resposta.status_code == 201, resposta.text
    corpo: Json = resposta.json()
    return corpo


def transferir(api: TestClient, origem: int, destino: int, valor: str, **campos: Any) -> Any:
    corpo = {
        "data": campos.pop("data", "2026-11-15"),
        "origem_id": origem,
        "destino_id": destino,
        "valor": valor,
        **campos,
    }
    return api.post("/api/transferencias", json=corpo)


def saldo(api: TestClient, inst: int, moeda: str = "BRL", fim: str = FIM_DO_MES) -> str:
    resposta = api.get(f"/api/instituicoes/{inst}/extrato", params={"moeda": moeda, "fim": fim})
    assert resposta.status_code == 200, resposta.text
    return dois(resposta.json()["saldo_final"])


def extrato(api: TestClient, inst: int, moeda: str = "BRL") -> list[Json]:
    resposta = api.get(f"/api/instituicoes/{inst}/extrato", params={"moeda": moeda, "limite": 500})
    itens: list[Json] = resposta.json()["itens"]
    return itens


def tipos_no_extrato(api: TestClient, inst: int, moeda: str = "BRL") -> list[str]:
    return sorted(x["tipo"] for x in extrato(api, inst, moeda))


def falta(resposta: Any) -> str:
    detalhes = {d["campo"]: d["mensagem"] for d in resposta.json()["detalhes"]}
    return dois(detalhes["valor_faltante"])


# ---------------------------------------------------------------- Receitas e despesas


def test_receita_credita_e_despesa_debita_a_conta_brl(api: TestClient) -> None:
    # Conta BRL nasce no primeiro movimento: salário 5.000 − mercado 800 = 4.200.
    nubank = instituicao(api, "Nubank")
    criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    criado(lancar(api, "despesa", "2026-11-06", "800", nubank))
    assert saldo(api, nubank) == "4200.00"
    assert tipos_no_extrato(api, nubank) == ["credito_receita", "debito_despesa"]


def test_movimento_de_lancamento_e_so_leitura_no_caixa(api: TestClient) -> None:
    nubank = instituicao(api, "Nubank")
    criado(lancar(api, "receita", "2026-11-05", "5000", nubank, descricao="Salário"))
    movimento = extrato(api, nubank)[0]
    assert movimento["lancamento_id"] is not None
    assert movimento["descricao"] == "Salário"
    resposta = api.delete(f"/api/movimentos/{movimento['id']}")
    assert resposta.status_code == 422
    assert "Receitas e Despesas" in resposta.json()["mensagem"]


def test_despesa_alem_do_saldo_avisa_sem_gravar_e_com_aceite_zera_o_caixa(api: TestClient) -> None:
    # Caixa 1.000 e despesa 1.500 → falta 500. Aceito: despesa 1.500 + ajuste 500 → caixa 0.
    nubank = instituicao(api, "Nubank")
    deposito(api, nubank, "2026-11-01", "1000")
    aviso = lancar(api, "despesa", "2026-11-10", "1500", nubank)
    assert aviso.status_code == 409
    assert aviso.json()["codigo"] == "saldo_insuficiente"
    assert falta(aviso) == "500.00"
    assert "Nubank" in aviso.json()["mensagem"]
    assert api.get("/api/lancamentos").json()["total"] == 0
    assert saldo(api, nubank) == "1000.00"

    despesa = criado(lancar(api, "despesa", "2026-11-10", "1500", nubank, aceitar_ajuste=True))
    assert saldo(api, nubank) == "0.00"
    ajustes = [x for x in extrato(api, nubank) if x["tipo"] == "ajuste_saldo"]
    assert [(dois(x["valor"]), x["lancamento_id"]) for x in ajustes] == [
        ("500.00", despesa["lancamento_id"])
    ]

    # Excluir a despesa leva o ajuste junto: o caixa volta a 1.000.
    assert api.delete(f"/api/lancamentos/{despesa['lancamento_id']}").status_code == 204
    assert saldo(api, nubank) == "1000.00"
    assert tipos_no_extrato(api, nubank) == ["deposito"]


def test_editar_despesa_recalcula_o_ajuste(api: TestClient) -> None:
    # Caixa 1.000, despesa 1.500 com ajuste 500. Reduzida a 1.200: falta 200 → aviso de 200
    # (o ajuste antigo é refeito). Aceito: ajuste 200, caixa 0. Reduzida a 800: sem ajuste,
    # caixa 1.000 − 800 = 200.
    nubank = instituicao(api, "Nubank")
    deposito(api, nubank, "2026-11-01", "1000")
    despesa = criado(lancar(api, "despesa", "2026-11-10", "1500", nubank, aceitar_ajuste=True))
    url = f"/api/lancamentos/{despesa['lancamento_id']}"
    corpo = {"tipo": "despesa", "data": "2026-11-10", "descricao": "x", "instituicao_id": nubank}

    aviso = api.put(url, json={**corpo, "valor": "1200"})
    assert aviso.status_code == 409
    assert falta(aviso) == "200.00"
    assert saldo(api, nubank) == "0.00"  # nada mudou: a despesa de 1.500 e o ajuste de 500

    assert api.put(url, json={**corpo, "valor": "1200", "aceitar_ajuste": True}).status_code == 200
    assert [dois(x["valor"]) for x in extrato(api, nubank) if x["tipo"] == "ajuste_saldo"] == [
        "200.00"
    ]
    assert saldo(api, nubank) == "0.00"

    assert api.put(url, json={**corpo, "valor": "800"}).status_code == 200
    assert tipos_no_extrato(api, nubank) == ["debito_despesa", "deposito"]
    assert saldo(api, nubank) == "200.00"


def test_salario_antes_do_aluguel_nao_pede_ajuste(api: TestClient) -> None:
    # Ex. 1: caixa 1.000 em 01/11; salário 5.000 (01/11), aluguel 2.000 (02/11) → 4.000.
    nubank = instituicao(api, "Nubank")
    deposito(api, nubank, "2026-11-01", "1000")
    criado(lancar(api, "receita", "2026-11-01", "5000", nubank))
    criado(lancar(api, "despesa", "2026-11-02", "2000", nubank))
    assert saldo(api, nubank) == "4000.00"


def test_aluguel_antes_do_salario_pede_ajuste_de_mil(api: TestClient) -> None:
    # Ex. 2: mesmo caso, aluguel lançado primeiro → 1.000 − 2.000 = −1.000: aviso de 1.000.
    nubank = instituicao(api, "Nubank")
    deposito(api, nubank, "2026-11-01", "1000")
    aviso = lancar(api, "despesa", "2026-11-02", "2000", nubank)
    assert aviso.status_code == 409
    assert falta(aviso) == "1000.00"


@pytest.mark.parametrize("salario_primeiro", [True, False])
def test_receita_depois_da_despesa_no_calendario_pede_ajuste_em_qualquer_ordem(
    api: TestClient, salario_primeiro: bool
) -> None:
    # Ex. 3: caixa 1.000 (01/11), aluguel 2.000 (02/11), salário 5.000 (05/11): de 02 a
    # 04/11 o caixa seria −1.000 → aviso de 1.000 nas duas ordens. Aceito: 0 de 02 a 04/11
    # e 5.000 a partir de 05/11.
    nubank = instituicao(api, "Nubank")
    deposito(api, nubank, "2026-11-01", "1000")
    if salario_primeiro:
        criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    aviso = lancar(api, "despesa", "2026-11-02", "2000", nubank)
    assert aviso.status_code == 409
    assert falta(aviso) == "1000.00"
    criado(lancar(api, "despesa", "2026-11-02", "2000", nubank, aceitar_ajuste=True))
    if not salario_primeiro:
        criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    assert saldo(api, nubank, fim="2026-11-04") == "0.00"
    assert saldo(api, nubank, fim="2026-11-05") == "5000.00"


def test_excluir_receita_que_deixaria_o_caixa_negativo_e_recusado(api: TestClient) -> None:
    # Nubank com 0, salário 5.000 (05/11), aluguel 2.000 (10/11): sem o salário o caixa
    # ficaria −2.000 a partir de 10/11 → 422, nada muda.
    nubank = instituicao(api, "Nubank")
    salario = criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    criado(lancar(api, "despesa", "2026-11-10", "2000", nubank))
    resposta = api.delete(f"/api/lancamentos/{salario['lancamento_id']}")
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "saldo_insuficiente"
    mensagem = resposta.json()["mensagem"]
    assert "Nubank" in mensagem
    assert "10/11/2026" in mensagem
    assert "2.000,00" in mensagem
    assert saldo(api, nubank) == "3000.00"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("valor", "1000"),  # reduzir: 1.000 − 2.000 = −1.000
        ("data", "2026-11-12"),  # adiar para depois do aluguel
        ("tipo", "despesa"),  # virar despesa
    ],
)
def test_alterar_receita_que_deixaria_o_caixa_negativo_e_recusado(
    api: TestClient, campo: str, valor: str
) -> None:
    nubank = instituicao(api, "Nubank")
    salario = criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    criado(lancar(api, "despesa", "2026-11-10", "2000", nubank))
    corpo = {
        "tipo": "receita",
        "data": "2026-11-05",
        "descricao": "Salário",
        "valor": "5000",
        "instituicao_id": nubank,
        "aceitar_ajuste": True,
        campo: valor,
    }
    resposta = api.put(f"/api/lancamentos/{salario['lancamento_id']}", json=corpo)
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "saldo_insuficiente"
    assert saldo(api, nubank) == "3000.00"


def test_trocar_a_instituicao_de_uma_receita_e_recusado_se_a_antiga_ficar_negativa(
    api: TestClient,
) -> None:
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    salario = criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    criado(lancar(api, "despesa", "2026-11-10", "2000", nubank))
    corpo = {
        "tipo": "receita",
        "data": "2026-11-05",
        "descricao": "Salário",
        "valor": "5000",
        "instituicao_id": itau,
    }
    resposta = api.put(f"/api/lancamentos/{salario['lancamento_id']}", json=corpo)
    assert resposta.status_code == 422
    assert "Nubank" in resposta.json()["mensagem"]


def test_trocar_a_instituicao_de_uma_despesa_avisa_na_conta_nova(api: TestClient) -> None:
    # Nubank 1.000 e Itaú 300. Despesa de 800 no Nubank (Nubank 200). Levada para o Itaú:
    # 300 − 800 = −500 → aviso de 500 no Itaú. Aceito: Nubank volta a 1.000, Itaú 0.
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1000")
    deposito(api, itau, "2026-11-01", "300")
    despesa = criado(lancar(api, "despesa", "2026-11-10", "800", nubank))
    url = f"/api/lancamentos/{despesa['lancamento_id']}"
    corpo = {
        "tipo": "despesa",
        "data": "2026-11-10",
        "descricao": "x",
        "valor": "800",
        "instituicao_id": itau,
    }
    aviso = api.put(url, json=corpo)
    assert aviso.status_code == 409
    assert falta(aviso) == "500.00"
    assert "Itaú" in aviso.json()["mensagem"]
    editado = api.put(url, json={**corpo, "aceitar_ajuste": True})
    assert editado.status_code == 200
    assert editado.json()["instituicao_nome"] == "Itaú"
    assert (saldo(api, nubank), saldo(api, itau)) == ("1000.00", "0.00")


def test_antecipar_uma_despesa_avisa_se_faltar_saldo_na_data_nova(api: TestClient) -> None:
    # Caixa 0; salário 5.000 em 05/11; despesa 2.000 em 10/11 (caixa 3.000). Antecipada para
    # 03/11 (antes do salário) → falta 2.000 de 03 a 04/11: aviso de 2.000.
    nubank = instituicao(api, "Nubank")
    criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    despesa = criado(lancar(api, "despesa", "2026-11-10", "2000", nubank))
    corpo = {
        "tipo": "despesa",
        "data": "2026-11-03",
        "descricao": "x",
        "valor": "2000",
        "instituicao_id": nubank,
    }
    aviso = api.put(f"/api/lancamentos/{despesa['lancamento_id']}", json=corpo)
    assert aviso.status_code == 409
    assert falta(aviso) == "2000.00"
    assert saldo(api, nubank) == "3000.00"


# ---------------------------------------------------------------- Transferências


def test_transferencia_com_tarifa(api: TestClient) -> None:
    # Nubank 1.500 → Itaú 1.000 com tarifa 10: Nubank 1.500 − 1.000 − 10 = 490; Itaú 1.000.
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1500")
    transferencia = criado(transferir(api, nubank, itau, "1000", tarifa="10"))
    assert transferencia["origem_nome"] == "Nubank"
    assert transferencia["destino_nome"] == "Itaú"
    assert transferencia["tarifa_lancamento_id"] is not None
    assert (saldo(api, nubank), saldo(api, itau)) == ("490.00", "1000.00")

    saida = [x for x in extrato(api, nubank) if x["tipo"] == "transferencia_saida"]
    assert [(dois(x["valor"]), x["contraparte"]) for x in saida] == [("1000.00", "Itaú")]
    despesa = [x for x in extrato(api, nubank) if x["tipo"] == "debito_despesa"]
    assert [dois(x["valor"]) for x in despesa] == ["10.00"]
    entrada = extrato(api, itau)
    assert [(x["tipo"], dois(x["valor"]), x["contraparte"]) for x in entrada] == [
        ("transferencia_entrada", "1000.00", "Nubank")
    ]

    tarifa = api.get(f"/api/lancamentos/{transferencia['tarifa_lancamento_id']}").json()
    assert tarifa["tag"] == "tarifa"
    assert tarifa["editavel"] is False
    assert tarifa["descricao"] == "Tarifa da transferência para Itaú"


def test_transferencia_sem_tarifa_nao_cria_despesa(api: TestClient) -> None:
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1500")
    transferencia = criado(transferir(api, nubank, itau, "1000"))
    assert transferencia["tarifa_lancamento_id"] is None
    assert (saldo(api, nubank), saldo(api, itau)) == ("500.00", "1000.00")
    assert tipos_no_extrato(api, nubank) == ["deposito", "transferencia_saida"]


def test_transferencia_sem_saldo_para_valor_mais_tarifa_e_recusada(api: TestClient) -> None:
    # 1.005 no Nubank para 1.000 + 10 → faltam 5, recusa (422) sem ajuste.
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1005")
    resposta = transferir(api, nubank, itau, "1000", tarifa="10")
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "saldo_insuficiente"
    assert "5,00" in resposta.json()["mensagem"]
    assert api.get("/api/transferencias").json()["total"] == 0
    assert saldo(api, nubank) == "1005.00"


def test_excluir_transferencia_que_deixaria_o_destino_negativo_e_recusado(
    api: TestClient,
) -> None:
    # Itaú recebe 1.000 e gasta 600 em 20/11: sem a transferência ficaria −600.
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1500")
    transferencia = criado(transferir(api, nubank, itau, "1000", tarifa="10"))
    criado(lancar(api, "despesa", "2026-11-20", "600", itau))
    resposta = api.delete(f"/api/transferencias/{transferencia['id']}")
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "saldo_insuficiente"
    assert "Itaú" in resposta.json()["mensagem"]
    assert (saldo(api, nubank), saldo(api, itau)) == ("490.00", "400.00")


def test_excluir_transferencia_desfaz_movimentos_e_tarifa(api: TestClient) -> None:
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1500")
    transferencia = criado(transferir(api, nubank, itau, "1000", tarifa="10"))
    assert api.delete(f"/api/transferencias/{transferencia['id']}").status_code == 204
    assert (saldo(api, nubank), saldo(api, itau)) == ("1500.00", "0.00")
    assert api.get("/api/lancamentos").json()["total"] == 0


def test_editar_transferencia_refaz_movimentos_e_tarifa(api: TestClient) -> None:
    # 1.000 + 10 → 1.200 sem tarifa: Nubank 1.500 − 1.200 = 300, Itaú 1.200, sem despesa.
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1500")
    transferencia = criado(transferir(api, nubank, itau, "1000", tarifa="10"))
    corpo = {"data": "2026-11-16", "origem_id": nubank, "destino_id": itau, "valor": "1200"}
    resposta = api.put(f"/api/transferencias/{transferencia['id']}", json=corpo)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["tarifa_lancamento_id"] is None
    assert (saldo(api, nubank), saldo(api, itau)) == ("300.00", "1200.00")
    assert api.get("/api/lancamentos").json()["total"] == 2  # só as duas pontas


def test_validacoes_da_transferencia(api: TestClient) -> None:
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1500")
    deposito(api, nubank, "2026-11-01", "500", moeda="USD")
    mesma = transferir(api, nubank, nubank, "10")
    assert mesma.status_code == 422
    assert "diferente da origem" in mesma.json()["mensagem"]
    assert transferir(api, nubank, itau, "0").status_code == 422
    assert transferir(api, nubank, itau, "10", tarifa="-1").status_code == 422
    assert transferir(api, nubank, 999, "10").status_code == 404
    usd = transferir(api, nubank, itau, "100", moeda="USD", tarifa="5")
    assert usd.status_code == 422
    assert "lance a tarifa como saque" in usd.json()["mensagem"]
    receita = criado(api.post("/api/categorias", json={"nome": "Salário", "tipo": "receita"}))
    errada = transferir(api, nubank, itau, "10", tarifa="1", categoria_tarifa_id=receita["id"])
    assert errada.status_code == 422


def test_transferencia_em_usd_fica_so_no_caixa(api: TestClient) -> None:
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "500", moeda="USD")
    criado(transferir(api, nubank, itau, "200", moeda="USD"))
    assert (saldo(api, nubank, "USD"), saldo(api, itau, "USD")) == ("300.00", "200.00")
    assert api.get("/api/lancamentos").json()["total"] == 0
    assert api.get("/api/resumo-mensal/instituicoes", params={"ano": 2026, "mes": 11}).json() == []


def test_tarifa_nao_muda_por_lancamentos(api: TestClient) -> None:
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    deposito(api, nubank, "2026-11-01", "1500")
    tarifa_id = criado(transferir(api, nubank, itau, "1000", tarifa="10"))["tarifa_lancamento_id"]
    corpo = {
        "tipo": "despesa",
        "data": "2026-11-15",
        "descricao": "x",
        "valor": "5",
        "instituicao_id": nubank,
    }
    for resposta in (
        api.put(f"/api/lancamentos/{tarifa_id}", json=corpo),
        api.delete(f"/api/lancamentos/{tarifa_id}"),
    ):
        assert resposta.status_code == 422
        assert "Movimentações → Caixa" in resposta.json()["mensagem"]
    movimento = next(x for x in extrato(api, nubank) if x["tipo"] == "transferencia_saida")
    bloqueado = api.delete(f"/api/movimentos/{movimento['id']}")
    assert bloqueado.status_code == 422
    assert "transferência" in bloqueado.json()["mensagem"]


# ---------------------------------------------------------------- Listagem e resumos


def roteiro(api: TestClient) -> tuple[int, int]:
    """Roteiro de validação do Prompt 8, até relançar a despesa do Itaú com ajuste.

    Nubank: 1.000 (01/11) + 5.000 (05/11) − 2.000 (10/11) − 1.000 − 10 (15/11) = 2.990.
    Itaú: +1.000 (15/11) − 3.500 (20/11) + ajuste 2.500 = 0.
    """
    nubank, itau = instituicao(api, "Nubank"), instituicao(api, "Itaú")
    mercado = criado(api.post("/api/categorias", json={"nome": "Moradia", "tipo": "despesa"}))
    deposito(api, nubank, "2026-11-01", "1000")
    criado(lancar(api, "receita", "2026-11-05", "5000", nubank, descricao="Salário"))
    criado(
        lancar(
            api,
            "despesa",
            "2026-11-10",
            "2000",
            nubank,
            descricao="Aluguel",
            categoria_id=mercado["id"],
        )
    )
    criado(transferir(api, nubank, itau, "1000", tarifa="10"))
    assert (saldo(api, nubank), saldo(api, itau)) == ("2990.00", "1000.00")
    aviso = lancar(api, "despesa", "2026-11-20", "3500", itau, descricao="Reforma")
    assert aviso.status_code == 409
    assert falta(aviso) == "2500.00"
    criado(
        lancar(api, "despesa", "2026-11-20", "3500", itau, descricao="Reforma", aceitar_ajuste=True)
    )
    assert saldo(api, itau) == "0.00"
    return nubank, itau


def test_roteiro_totais_e_resumo_por_instituicao(api: TestClient) -> None:
    nubank, itau = roteiro(api)
    mes = {"ano": 2026, "mes": 11}

    # Cartões (ponto B1): recebido 5.000; gasto 2.000 + 10 + 3.500 = 5.510; saldo −510.
    resumo = api.get("/api/resumo-mensal", params=mes).json()
    assert (
        dois(resumo["total_receitas"]),
        dois(resumo["total_despesas"]),
        dois(resumo["saldo"]),
    ) == ("5000.00", "5510.00", "-510.00")
    # Rosca: transferência fora; Moradia 2.000 e "Sem categoria" (tarifa + reforma) 3.510.
    despesas = {
        c["categoria_nome"]: dois(c["total"])
        for c in resumo["por_categoria"]
        if c["tipo"] == "despesa"
    }
    assert despesas == {"Moradia": "2000.00", "Sem categoria": "3510.00"}

    # Filtro por instituição: Itaú só tem a reforma (a entrada da transferência fica fora).
    so_itau = api.get("/api/resumo-mensal", params={**mes, "instituicao_id": itau}).json()
    assert (dois(so_itau["total_receitas"]), dois(so_itau["total_despesas"])) == ("0.00", "3500.00")
    so_nubank = api.get("/api/resumo-mensal", params={**mes, "instituicao_id": nubank}).json()
    assert (dois(so_nubank["total_receitas"]), dois(so_nubank["total_despesas"])) == (
        "5000.00",
        "2010.00",
    )

    # Nubank 5.000 − 2.010 + 0 − 1.000 = 1.990; Itaú 0 − 3.500 + 1.000 − 0 = −2.500 (o ajuste
    # não é receita). Ordem alfabética.
    por_instituicao = api.get("/api/resumo-mensal/instituicoes", params=mes).json()
    assert [
        (
            x["instituicao_nome"],
            *(dois(x[c]) for c in ("receitas", "despesas", "entrou", "saiu", "saldo")),
        )
        for x in por_instituicao
    ] == [
        ("Itaú", "0.00", "3500.00", "1000.00", "0.00", "-2500.00"),
        ("Nubank", "5000.00", "2010.00", "0.00", "1000.00", "1990.00"),
    ]


def test_roteiro_excluir_o_salario_e_recusado_com_os_2010_que_faltam(api: TestClient) -> None:
    # Sem o salário: 1.000 − 2.000 = −1.000 em 10/11 e −1.000 − 1.010 = −2.010 em 15/11.
    nubank, _ = roteiro(api)
    salario = next(
        x
        for x in api.get("/api/lancamentos", params={"instituicao_id": nubank}).json()["itens"]
        if x["descricao"] == "Salário"
    )
    resposta = api.delete(f"/api/lancamentos/{salario['lancamento_id']}")
    assert resposta.status_code == 422
    assert "2.010,00" in resposta.json()["mensagem"]


def test_listagem_combinada_tags_chaves_ordem_e_paginacao(api: TestClient) -> None:
    roteiro(api)
    itens = api.get("/api/lancamentos", params={"limite": 500}).json()["itens"]
    # Reforma (20/11), quatro linhas de 15/11 (tarifa e as duas pontas), aluguel, salário.
    assert next((x["data"][-2:], x["tag"], x["tipo"]) for x in itens) == (
        "20",
        "lancamento",
        "despesa",
    )
    assert [x["data"][-2:] for x in itens] == ["20", "15", "15", "15", "10", "05"]
    assert len({x["chave"] for x in itens}) == len(itens)
    do_dia_15 = {x["tag"]: x for x in itens if x["data"].endswith("15")}
    assert set(do_dia_15) == {"tarifa", "transferencia_saida", "transferencia_entrada"}
    saida, entrada = do_dia_15["transferencia_saida"], do_dia_15["transferencia_entrada"]
    assert saida["chave"].endswith("-saida")
    assert saida["instituicao_nome"] == "Nubank"
    assert entrada["chave"].endswith("-entrada")
    assert entrada["instituicao_nome"] == "Itaú"
    assert saida["lancamento_id"] is None
    assert saida["transferencia_id"] is not None
    assert not saida["editavel"]
    assert not do_dia_15["tarifa"]["editavel"]
    assert all(x["editavel"] for x in itens if x["tag"] == "lancamento")

    # Paginação sobre a lista combinada: 6 linhas, páginas de 4.
    primeira = api.get("/api/lancamentos", params={"limite": 4}).json()
    segunda = api.get("/api/lancamentos", params={"limite": 4, "deslocamento": 4}).json()
    assert (primeira["total"], len(primeira["itens"]), len(segunda["itens"])) == (6, 4, 2)
    assert [x["chave"] for x in primeira["itens"] + segunda["itens"]] == [x["chave"] for x in itens]


def test_listagem_filtra_por_instituicao_tipo_e_categoria(api: TestClient) -> None:
    nubank, itau = roteiro(api)
    do_itau = api.get("/api/lancamentos", params={"instituicao_id": itau}).json()["itens"]
    assert sorted(x["tag"] for x in do_itau) == ["lancamento", "transferencia_entrada"]
    receitas = api.get("/api/lancamentos", params={"tipo": "receita"}).json()["itens"]
    assert sorted(x["tag"] for x in receitas) == ["lancamento", "transferencia_entrada"]
    moradia = next(c for c in api.get("/api/categorias").json() if c["nome"] == "Moradia")
    por_categoria = api.get("/api/lancamentos", params={"categoria_id": moradia["id"]}).json()
    assert [x["descricao"] for x in por_categoria["itens"]] == ["Aluguel"]
    assert nubank != itau


# ---------------------------------------------------------------- Instituições


def test_instituicao_com_lancamento_ou_transferencia_nao_pode_ser_excluida(
    api: TestClient,
) -> None:
    nubank, itau, inter = (instituicao(api, n) for n in ("Nubank", "Itaú", "Inter"))
    criado(lancar(api, "receita", "2026-11-05", "5000", nubank))
    resposta = api.delete(f"/api/instituicoes/{nubank}")
    assert resposta.status_code == 422
    assert "receitas ou despesas" in resposta.json()["mensagem"]

    deposito(api, inter, "2026-11-01", "100")
    criado(transferir(api, inter, itau, "100"))
    resposta = api.delete(f"/api/instituicoes/{itau}")
    assert resposta.status_code == 422
    assert "transferências" in resposta.json()["mensagem"]

    vazia = instituicao(api, "C6")
    deposito(api, vazia, "2026-11-01", "100")
    resposta = api.delete(f"/api/instituicoes/{vazia}")
    assert resposta.status_code == 422
    assert "depósitos, saques" in resposta.json()["mensagem"]


def test_lancamento_exige_instituicao(api: TestClient) -> None:
    corpo = {"tipo": "receita", "data": "2026-11-05", "descricao": "x", "valor": "1"}
    assert api.post("/api/lancamentos", json=corpo).status_code == 422
    assert api.post("/api/lancamentos", json={**corpo, "instituicao_id": 999}).status_code == 404


# ---------------------------------------------------------------- Banco


def _base(sessao: Session) -> tuple[m.ContaCorrente, m.Lancamento, m.Transferencia]:
    a = m.Instituicao(nome="A", tipo=TipoInstituicao.BANCO)
    b = m.Instituicao(nome="B", tipo=TipoInstituicao.BANCO)
    sessao.add_all([a, b])
    sessao.flush()
    conta = m.ContaCorrente(instituicao_id=a.id, moeda="BRL")
    lancamento = m.Lancamento(
        tipo=TipoLancamento.DESPESA,
        data=date(2026, 11, 1),
        descricao="x",
        valor=Decimal(1),
        instituicao_id=a.id,
    )
    transferencia = m.Transferencia(
        data=date(2026, 11, 1),
        origem_id=a.id,
        destino_id=b.id,
        moeda="BRL",
        valor=Decimal(1),
        tarifa=Decimal(0),
    )
    sessao.add_all([conta, lancamento, transferencia])
    sessao.flush()
    return conta, lancamento, transferencia


@pytest.mark.parametrize(
    ("tipo", "vinculo"),
    [
        (TipoMovimento.DEBITO_DESPESA, None),
        (TipoMovimento.CREDITO_RECEITA, "transferencia"),
        (TipoMovimento.TRANSFERENCIA_SAIDA, "lancamento"),
        (TipoMovimento.TRANSFERENCIA_ENTRADA, None),
        (TipoMovimento.DEPOSITO, "lancamento"),
        (TipoMovimento.AJUSTE_SALDO, "transferencia"),
    ],
)
def test_constraint_de_vinculo_recusa_combinacoes_erradas(
    sessao: Session, tipo: TipoMovimento, vinculo: str | None
) -> None:
    conta, lancamento, transferencia = _base(sessao)
    sessao.add(
        m.MovimentoConta(
            conta_id=conta.id,
            tipo=tipo,
            data=date(2026, 11, 1),
            valor=Decimal(1),
            lancamento_id=lancamento.id if vinculo == "lancamento" else None,
            transferencia_id=transferencia.id if vinculo == "transferencia" else None,
        )
    )
    with pytest.raises(IntegrityError):
        sessao.flush()


def test_check_da_transferencia(sessao: Session) -> None:
    _, _, base = _base(sessao)
    for campos in (
        {"destino_id": base.origem_id},  # origem = destino
        {"moeda": "USD", "tarifa": Decimal(1)},  # tarifa fora do real
    ):
        with sessao.begin_nested():
            sessao.add(
                m.Transferencia(
                    **{
                        "data": date(2026, 11, 2),
                        "origem_id": base.origem_id,
                        "destino_id": base.destino_id,
                        "moeda": "BRL",
                        "valor": Decimal(1),
                        "tarifa": Decimal(0),
                        **campos,
                    }
                )
            )
            with pytest.raises(IntegrityError):
                sessao.flush()


def test_migracao_0005_falha_com_lancamentos_sem_instituicao(tmp_path: Path) -> None:
    banco = tmp_path / "financas.db"
    configuracao = configuracao_alembic(banco)
    command.upgrade(configuracao, "0004_listas_simbolos")
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute(
            "INSERT INTO lancamentos (tipo, data, descricao, valor, criado_em) "
            "VALUES ('despesa', '2026-11-01', 'Feira', '10', '2026-11-01')"
        )
        conexao.commit()
    with pytest.raises(Exception, match="lançamento\\(s\\) de Receitas e Despesas sem instituição"):
        command.upgrade(configuracao, "head")


def test_migracao_0005_preserva_os_movimentos_e_volta(tmp_path: Path) -> None:
    banco = tmp_path / "financas.db"
    configuracao = configuracao_alembic(banco)
    command.upgrade(configuracao, "0004_listas_simbolos")
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.executescript(
            """
            INSERT INTO instituicoes (id, nome, tipo, criado_em)
                VALUES (1, 'Rico', 'corretora', '2026-11-01');
            INSERT INTO contas_correntes (id, instituicao_id, moeda, criado_em)
                VALUES (1, 1, 'BRL', '2026-11-01');
            INSERT INTO movimentos_conta (id, conta_id, tipo, data, valor, criado_em)
                VALUES (1, 1, 'deposito', '2026-11-01', '1000', '2026-11-01');
            """
        )
        conexao.commit()
    command.upgrade(configuracao, "head")
    with closing(sqlite3.connect(banco)) as conexao:
        linhas = conexao.execute(
            "SELECT id, tipo, valor, lancamento_id, transferencia_id FROM movimentos_conta"
        ).fetchall()
    assert linhas == [(1, "deposito", "1000", None, None)]
    command.downgrade(configuracao, "0004_listas_simbolos")
    with closing(sqlite3.connect(banco)) as conexao:
        assert conexao.execute("SELECT id, valor FROM movimentos_conta").fetchall() == [(1, "1000")]
