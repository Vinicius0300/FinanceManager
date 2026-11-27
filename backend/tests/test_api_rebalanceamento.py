"""API do Rebalanceamento: metas (GET/PUT), validação em pt-BR e plano (Parte 10).

Cenário montado pela API (relógio fixo em 29/10/2026), conferido à mão:
- depósito de 20.000 na RICO em 01/10;
- PETR4 100 × 40 (custo 4.000), cotação de hoje 50 → 5.000;
- VALE3 50 × 60 (custo 3.000), cotação de hoje 60 → 3.000;
- HGLG11 20 × 100 (custo 2.000), última cotação 100 em 20/10 (9 dias, defasada) → 2.000.
T = 10.000 (Ações BR 8.000 = 80%, FII 2.000 = 20%); caixa = 20.000 − 9.000 = 11.000.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_api import HOJE, api, app_api, criar, yahoo  # noqa: F401 - fixtures reutilizadas

Json = dict[str, Any]


def _comprar(api: TestClient, inst: int, ativo: int, quantidade: str, preco: str) -> None:  # noqa: F811
    criar(
        api,
        "/api/transacoes",
        {
            "ativo_id": ativo,
            "instituicao_id": inst,
            "tipo": "compra",
            "data": "2026-10-02",
            "quantidade": quantidade,
            "preco_unitario": preco,
        },
    )


def _cenario(api: TestClient) -> dict[str, int]:  # noqa: F811
    rico = criar(api, "/api/instituicoes", {"nome": "RICO", "tipo": "corretora"})["id"]
    criar(
        api,
        "/api/movimentos",
        {"instituicao_id": rico, "tipo": "deposito", "data": "2026-10-01", "valor": "20000"},
    )
    petr = criar(api, "/api/ativos", {"tipo": "acao_br", "nome": "Petrobras", "simbolo": "PETR4"})
    vale = criar(api, "/api/ativos", {"tipo": "acao_br", "nome": "Vale", "simbolo": "VALE3"})
    hglg = criar(
        api, "/api/ativos", {"tipo": "fundo_listado", "nome": "CSHG Log", "simbolo": "HGLG11"}
    )
    _comprar(api, rico, petr["id"], "100", "40")
    _comprar(api, rico, vale["id"], "50", "60")
    _comprar(api, rico, hglg["id"], "20", "100")
    criar(api, f"/api/ativos/{petr['id']}/precos", {"data": HOJE, "valor": "50"})
    criar(api, f"/api/ativos/{vale['id']}/precos", {"data": HOJE, "valor": "60"})
    criar(api, f"/api/ativos/{hglg['id']}/precos", {"data": "2026-10-20", "valor": "100"})
    return {"petr": petr["id"], "vale": vale["id"], "hglg": hglg["id"]}


def _metas(ids: dict[str, int], **extra: Any) -> Json:
    corpo: Json = {
        "classes": [
            {"tipo_ativo": "acao_br", "percentual": "60"},
            {"tipo_ativo": "fundo_listado", "percentual": "40"},
        ],
        "ativos": [
            {"tipo_ativo": "acao_br", "ativo_id": ids["petr"], "peso": "50"},
            {"tipo_ativo": "acao_br", "ativo_id": ids["vale"], "peso": "50"},
        ],
        "tolerancia_pp": 5,
    }
    corpo.update(extra)
    return corpo


def _gravar(api: TestClient, corpo: Json, esperado: int = 200) -> Json:  # noqa: F811
    resposta = api.put("/api/rebalanceamento/metas", json=corpo)
    assert resposta.status_code == esperado, resposta.text
    dados: Json = resposta.json()
    return dados


def _classes(plano: Json) -> dict[str, Json]:
    return {c["tipo_ativo"]: c for c in plano["classes"]}


# ---------------------------------------------------------------- metas


def test_metas_comecam_vazias_e_put_substitui_tudo(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)
    assert api.get("/api/rebalanceamento/metas").json() == {
        "classes": [],
        "ativos": [],
        "tolerancia_pp": 5,
    }
    gravadas = _gravar(api, _metas(ids))
    assert gravadas["classes"] == [
        {"tipo_ativo": "acao_br", "percentual": "60.00"},
        {"tipo_ativo": "fundo_listado", "percentual": "40.00"},
    ]
    assert [a["ativo_id"] for a in gravadas["ativos"]] == sorted([ids["petr"], ids["vale"]])
    assert api.get("/api/rebalanceamento/metas").json() == gravadas

    # O PUT substitui tudo: sem pesos, outra divisão e outra tolerância.
    novas = _gravar(
        api,
        {
            "classes": [
                {"tipo_ativo": "acao_br", "percentual": "70.5"},
                {"tipo_ativo": "fundo_listado", "percentual": "29.5"},
            ],
            "ativos": [],
            "tolerancia_pp": 8,
        },
    )
    assert novas == {
        "classes": [
            {"tipo_ativo": "acao_br", "percentual": "70.50"},
            {"tipo_ativo": "fundo_listado", "percentual": "29.50"},
        ],
        "ativos": [],
        "tolerancia_pp": 8,
    }
    # Lista vazia de classes apaga as metas (a tolerância continua gravada).
    assert _gravar(api, {"classes": [], "ativos": [], "tolerancia_pp": 8}) == {
        "classes": [],
        "ativos": [],
        "tolerancia_pp": 8,
    }


def _detalhes(resposta: Any) -> dict[str, str]:
    assert resposta.status_code == 422, resposta.text
    corpo = resposta.json()
    assert corpo["codigo"] == "validacao"
    return {d["campo"]: d["mensagem"] for d in corpo["detalhes"]}


def test_metas_invalidas_respondem_422_por_campo(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)

    def put(corpo: Json) -> Any:
        return api.put("/api/rebalanceamento/metas", json=corpo)

    soma = put(_metas(ids, classes=[{"tipo_ativo": "acao_br", "percentual": "97"}]))
    assert _detalhes(soma) == {
        "classes": "As metas das classes devem somar 100% (soma atual: 97%)."
    }

    desconhecido = put(
        _metas(ids, classes=[{"tipo_ativo": "imovel", "percentual": "100"}], ativos=[])
    )
    assert _detalhes(desconhecido) == {"classes.imovel": "Tipo de ativo desconhecido."}

    outra_classe = put(
        _metas(
            ids,
            ativos=[{"tipo_ativo": "fundo_listado", "ativo_id": ids["petr"], "peso": "100"}],
        )
    )
    assert set(_detalhes(outra_classe)) == {f"ativos.{ids['petr']}"}  # texto: teste abaixo

    casas = put(
        _metas(
            ids,
            classes=[
                {"tipo_ativo": "acao_br", "percentual": "60.005"},
                {"tipo_ativo": "fundo_listado", "percentual": "39.995"},
            ],
        )
    )
    assert _detalhes(casas) == {
        "classes.acao_br": "Use no máximo 2 casas decimais.",
        "classes.fundo_listado": "Use no máximo 2 casas decimais.",
    }

    pesos = put(
        _metas(ids, ativos=[{"tipo_ativo": "acao_br", "ativo_id": ids["petr"], "peso": "80"}])
    )
    assert set(_detalhes(pesos)) == {"pesos.acao_br"}

    fora = put(_metas(ids, tolerancia_pp=0))
    assert set(_detalhes(fora)) == {"tolerancia_pp"}

    inexistente = put(
        _metas(ids, ativos=[{"tipo_ativo": "acao_br", "ativo_id": 9999, "peso": "100"}])
    )
    assert _detalhes(inexistente) == {"ativos.9999": "Ativo não encontrado."}

    sem_meta = put(
        {
            "classes": [{"tipo_ativo": "fundo_listado", "percentual": "100"}],
            "ativos": [{"tipo_ativo": "acao_br", "ativo_id": ids["petr"], "peso": "100"}],
            "tolerancia_pp": 5,
        }
    )
    assert set(_detalhes(sem_meta)) == {f"ativos.{ids['petr']}"}

    acima = put(_metas(ids, classes=[{"tipo_ativo": "acao_br", "percentual": "101"}]))
    assert _detalhes(acima) == {"classes.acao_br": "A meta deve estar entre 0 e 100%."}

    flutuante = put(_metas(ids, classes=[{"tipo_ativo": "acao_br", "percentual": 100.0}]))
    assert flutuante.status_code == 422
    # Nada foi gravado em nenhuma tentativa.
    assert api.get("/api/rebalanceamento/metas").json()["classes"] == []


def test_mensagens_usam_o_nome_do_tipo(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)
    tipos = {t["slug"]: t["nome"] for t in api.get("/api/tipos-ativo").json()}
    resposta = api.put(
        "/api/rebalanceamento/metas",
        json=_metas(ids, ativos=[{"tipo_ativo": "acao_br", "ativo_id": ids["petr"], "peso": "80"}]),
    )
    assert _detalhes(resposta)["pesos.acao_br"] == (
        f"Os pesos dos ativos de {tipos['acao_br']} devem somar 100% (soma atual: 80%)."
    )
    resposta = api.put(
        "/api/rebalanceamento/metas",
        json=_metas(
            ids,
            ativos=[{"tipo_ativo": "fundo_listado", "ativo_id": ids["petr"], "peso": "100"}],
        ),
    )
    assert _detalhes(resposta)[f"ativos.{ids['petr']}"] == (
        f"O ativo PETR4 não é da classe {tipos['fundo_listado']}."
    )


# ---------------------------------------------------------------- plano


def test_plano_sem_metas_mostra_o_atual_e_o_aporte_padrao_e_o_caixa(api: TestClient) -> None:  # noqa: F811
    _cenario(api)
    plano = api.get("/api/rebalanceamento/plano").json()
    assert plano["tem_metas"] is False
    assert (plano["patrimonio_considerado"], plano["caixa_disponivel"], plano["aporte"]) == (
        "10000.00",
        "11000.00",
        "11000.00",
    )
    assert plano["desvio_total_pp"] is None
    assert plano["classes_fora_da_banda"] == 0
    classes = _classes(plano)
    assert (
        classes["acao_br"]["percentual_atual"],
        classes["fundo_listado"]["percentual_atual"],
    ) == (
        "80.00",
        "20.00",
    )
    assert all(c["meta"] is None and c["sugestao"] is None for c in plano["classes"])
    assert all(c["acao"] == "manter" for c in plano["classes"])


def test_plano_so_com_aportes_desce_ate_o_ativo(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)
    _gravar(api, _metas(ids))
    plano = api.get("/api/rebalanceamento/plano").json()
    # A = caixa = 11.000; N = 21.000. Ações BR 12.600 − 8.000 = 4.600; FII 8.400 − 2.000 =
    # 6.400 (Σ = A). Dentro de Ações BR (N_c = 12.600, pesos 50/50): PETR4 6.300 − 5.000 =
    # 1.300; VALE3 6.300 − 3.000 = 3.300.
    assert plano["modo"] == "aportes"
    assert plano["aporte"] == "11000.00"
    classes = _classes(plano)
    assert (classes["acao_br"]["sugestao"], classes["fundo_listado"]["sugestao"]) == (
        "4600.00",
        "6400.00",
    )
    assert classes["acao_br"]["acao"] == "aportar"
    # Desvios: Ações 80 − 60 = +20; FII 20 − 40 = −20; os dois fora da banda de 5 p.p.
    assert (classes["acao_br"]["desvio_pp"], classes["fundo_listado"]["desvio_pp"]) == (
        "20.00",
        "-20.00",
    )
    assert plano["classes_fora_da_banda"] == 2
    assert plano["desvio_total_pp"] == "20.00"
    acoes = {a["simbolo"]: a for a in classes["acao_br"]["ativos"]}
    assert classes["acao_br"]["usa_pesos"] is True
    assert (acoes["PETR4"]["sugestao"], acoes["VALE3"]["sugestao"]) == ("1300.00", "3300.00")
    assert acoes["PETR4"]["peso"] == "50.00"
    # FII sem pesos: o ativo aparece, sem sugestão, com o aviso da cotação defasada.
    hglg = classes["fundo_listado"]["ativos"][0]
    assert classes["fundo_listado"]["usa_pesos"] is False
    assert hglg["sugestao"] is None
    assert hglg["peso"] is None
    assert hglg["defasado"] is True
    assert hglg["aviso"] == "Cotação de 9 dias atrás."


def test_plano_completo_com_venda_e_lucro_estimado(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)
    _gravar(api, _metas(ids))
    plano = api.get("/api/rebalanceamento/plano", params={"aporte": "0", "modo": "completo"}).json()
    # N = T = 10.000: Ações 6.000 − 8.000 = −2.000; FII 4.000 − 2.000 = +2.000.
    # Dentro de Ações (N_c = 6.000): PETR4 3.000 − 5.000 = −2.000; VALE3 3.000 − 3.000 = 0.
    # Venda de PETR4: 2.000 ÷ 50 = 40 ações; lucro 2.000 − 40 × 40 = 400.
    classes = _classes(plano)
    assert (classes["acao_br"]["sugestao"], classes["fundo_listado"]["sugestao"]) == (
        "-2000.00",
        "2000.00",
    )
    assert classes["acao_br"]["acao"] == "vender"
    acoes = {a["simbolo"]: a for a in classes["acao_br"]["ativos"]}
    assert acoes["PETR4"] | {"ativo_id": 0} == {
        "ativo_id": 0,
        "simbolo": "PETR4",
        "nome": "Petrobras",
        "valor_atual": "5000.00",
        "peso": "50.00",
        "sugestao": "-2000.00",
        "acao": "vender",
        "quantidade_estimada": "40",
        "lucro_estimado": "400.00",
        "defasado": False,
        "aviso": None,
    }
    assert acoes["VALE3"]["acao"] == "manter"
    assert acoes["VALE3"]["lucro_estimado"] is None


def test_aporte_informado_e_validado(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)
    _gravar(api, _metas(ids))
    plano = api.get("/api/rebalanceamento/plano", params={"aporte": "5000.5"}).json()
    assert plano["aporte"] == "5000.50"
    assert plano["caixa_disponivel"] == "11000.00"
    soma = sum(int(c["sugestao"].replace(".", "")) for c in plano["classes"])
    assert soma == 500050  # fecha exatamente o aporte, em centavos
    negativo = api.get("/api/rebalanceamento/plano", params={"aporte": "-1"})
    assert _detalhes(negativo) == {"aporte": "O aporte não pode ser negativo."}
    casas = api.get("/api/rebalanceamento/plano", params={"aporte": "10.001"})
    assert _detalhes(casas) == {"aporte": "Use no máximo 2 casas decimais."}
    modo = api.get("/api/rebalanceamento/plano", params={"modo": "tudo"})
    assert modo.status_code == 422


def test_tolerancia_muda_as_classes_fora_da_banda(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)
    _gravar(api, _metas(ids, tolerancia_pp=20))
    plano = api.get("/api/rebalanceamento/plano", params={"aporte": "0"}).json()
    assert plano["tolerancia_pp"] == 20
    assert plano["classes_fora_da_banda"] == 0  # |±20| não é > 20


def test_excluir_ativo_apaga_o_peso_e_o_plano_avisa(api: TestClient) -> None:  # noqa: F811
    ids = _cenario(api)
    itub = criar(api, "/api/ativos", {"tipo": "acao_br", "nome": "Itaú", "simbolo": "ITUB4"})["id"]
    pesos = [
        {"tipo_ativo": "acao_br", "ativo_id": ids["petr"], "peso": "40"},
        {"tipo_ativo": "acao_br", "ativo_id": ids["vale"], "peso": "40"},
        {"tipo_ativo": "acao_br", "ativo_id": itub, "peso": "20"},
    ]
    _gravar(api, _metas(ids, ativos=pesos))
    # ITUB4 sem posição aparece no plano com o peso e valor atual 0.
    plano = api.get("/api/rebalanceamento/plano").json()
    itens = {a["simbolo"]: a for a in _classes(plano)["acao_br"]["ativos"]}
    assert itens["ITUB4"]["valor_atual"] == "0.00"
    assert itens["ITUB4"]["peso"] == "20.00"

    assert api.delete(f"/api/ativos/{itub}").status_code == 204
    metas = api.get("/api/rebalanceamento/metas").json()
    assert {a["ativo_id"] for a in metas["ativos"]} == {ids["petr"], ids["vale"]}
    plano = api.get("/api/rebalanceamento/plano").json()
    acoes = _classes(plano)["acao_br"]
    assert acoes["usa_pesos"] is False
    assert all(a["sugestao"] is None for a in acoes["ativos"])
    assert len(plano["avisos"]) == 1
    assert "não somam mais 100%" in plano["avisos"][0]


def test_rotas_do_rebalanceamento_exigem_token(app_api: FastAPI) -> None:  # noqa: F811
    with TestClient(app_api) as sem_token:
        for metodo, caminho in (
            ("get", "/api/rebalanceamento/metas"),
            ("put", "/api/rebalanceamento/metas"),
            ("get", "/api/rebalanceamento/plano"),
        ):
            resposta = sem_token.request(metodo, caminho, json={})
            assert resposta.status_code == 401
            assert resposta.json()["codigo"] == "nao_autorizado"
