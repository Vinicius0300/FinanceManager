"""Movimentação única (Parte 4.1): deduplicação por tipo e criação atômica do ativo.

Relógio fixo da API em 29/10/2026 14h (Brasília); sem rede.
"""

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.asset_types.base import Identidade
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.core.config import Settings
from app.domain.enums import TipoTransacao
from app.domain.erros import ConflitoError, NaoEncontradoError, ValidacaoError
from app.main import create_app
from app.providers.registry import RegistroProviders
from app.repositories import modelos as m
from app.services.cadastros import NovoAtivo, criar_ativo, preparar_ativo
from app.services.movimentacoes import (
    AtivoSemelhanteError,
    NovaMovimentacao,
    registrar_movimentacao,
)
from app.services.transacoes import NovaTransacao
from tests import fabricas as f
from tests.conftest import TOKEN_TESTE
from tests.test_api import AGORA
from tests.test_coleta import CotacaoFalsa

D = f.D
Json = dict[str, Any]


def ident(
    simbolo: str | None = None, externo: str | None = None, **metadados: object
) -> Identidade:
    return Identidade(simbolo, externo, metadados)


# ---------------------------------------------------------------- identidade por tipo


@pytest.mark.parametrize(
    ("tipo", "a", "b", "mesmo"),
    [
        ("acao_br", ident("PETR4"), ident("petr4.sa"), True),
        ("acao_br", ident("PETR4"), ident("PETR3"), False),
        ("fundo_listado", ident("HGLG11"), ident(" hglg11 "), True),
        ("etf_br", ident("BOVA11"), ident("BOVA11.SA"), True),
        ("acao_us", ident("BRK.B"), ident("brk-b"), True),
        ("etf_us", ident("SPY"), ident("spy"), True),
        ("cripto", ident("BTC", "bitcoin"), ident("btc", "BITCOIN"), True),
        ("cripto", ident("BTC"), ident("BTC", "bitcoin"), True),  # um ainda sem id
        ("cripto", ident("BTC", "bitcoin"), ident("BTC", "batcat"), False),  # ids diferentes
        ("fundo", ident(None, None, cnpj="1"), ident(None, None, cnpj="1"), True),
        ("fundo", ident(None, "A", cnpj="1"), ident(None, "B", cnpj="1"), False),  # subclasse
        (
            "tesouro_direto",
            ident(None, None, titulo="selic", vencimento="2029-03-01"),
            ident(None, None, titulo="selic", vencimento="2031-03-01"),
            False,
        ),
        ("poupanca", ident(), ident(), True),  # um único ativo "Poupança"
        ("renda_fixa", ident(), ident(), False),  # títulos nunca são fundidos sozinhos
    ],
)
def test_mesma_identidade(tipo: str, a: Identidade, b: Identidade, mesmo: bool) -> None:
    assert REGISTRO_PADRAO.obter(tipo).mesma_identidade(a, b) is mesmo


def test_renda_fixa_semelhante_ignora_acento_maiusculas_e_data_de_aplicacao() -> None:
    handler = REGISTRO_PADRAO.obter("renda_fixa")
    base = {"emissor": "Banco Itaú", "indexador": "cdi", "taxa": "110", "vencimento": "2028-01-03"}
    outro = {**base, "emissor": "  banco  ITAU ", "taxa": "110.0", "data_aplicacao": "2026-06-01"}
    assert handler.semelhante(ident(**base), ident(**outro))
    assert not handler.semelhante(ident(**base), ident(**{**base, "taxa": "111"}))
    assert not handler.semelhante(ident(**base), ident(**{**base, "vencimento": "2029-01-02"}))
    assert not handler.semelhante(ident(**base), ident(**{**base, "indexador": "pre"}))
    assert not handler.semelhante(ident(), ident())  # sem dados: nunca semelhante


def test_preparar_ativo_normaliza_ticker_e_simbolo_na_fonte() -> None:
    hglg, _ = preparar_ativo(NovoAtivo(tipo="fundo_listado", nome="Pátria Log", simbolo="hglg11"))
    assert (hglg.simbolo, hglg.simbolo_externo, hglg.provider) == (
        "HGLG11",
        "HGLG11.SA",
        "yfinance",
    )
    brk, _ = preparar_ativo(NovoAtivo(tipo="acao_us", nome="Berkshire", simbolo="brk.b"))
    assert (brk.simbolo, brk.simbolo_externo) == ("BRK-B", None)  # o Yahoo usa o ticker
    proprio, _ = preparar_ativo(
        NovoAtivo(tipo="etf_br", nome="X", simbolo="ABCD11", simbolo_externo="OUTRO.SA")
    )
    assert proprio.simbolo_externo == "OUTRO.SA"  # o informado prevalece


def test_criar_ativo_recusa_duplicado_e_ticker_repetido(sessao: Session) -> None:
    criar_ativo(sessao, NovoAtivo(tipo="acao_br", nome="Petrobras", simbolo="PETR4"))
    with pytest.raises(ConflitoError, match="Já existe o ativo PETR4"):
        criar_ativo(sessao, NovoAtivo(tipo="acao_br", nome="Outro", simbolo="petr4.sa"))
    criar_ativo(
        sessao, NovoAtivo(tipo="cripto", nome="Bitcoin", simbolo="BTC", simbolo_externo="bitcoin")
    )
    with pytest.raises(ConflitoError, match="com outra identificação"):
        criar_ativo(
            sessao, NovoAtivo(tipo="cripto", nome="Batcat", simbolo="BTC", simbolo_externo="batcat")
        )


# ---------------------------------------------------------------- serviço


def compra(**campos: Any) -> NovaTransacao:
    padrao: dict[str, Any] = {
        "ativo_id": 0,
        "instituicao_id": 0,
        "tipo": TipoTransacao.COMPRA,
        "data": date(2026, 10, 1),
        "quantidade": D(10),
        "preco_unitario": D(10),
    }
    return NovaTransacao(**{**padrao, **campos})


def cdb_novo(**metadados: str) -> NovoAtivo:
    return NovoAtivo(
        tipo="renda_fixa",
        nome="CDB Banco X 110%",
        metadados={
            "indexador": "cdi",
            "taxa": "110",
            "data_aplicacao": "2026-06-01",
            "vencimento": "2028-01-03",
            "emissor": "Banco X",
            "liquidez": "diaria",
            **metadados,
        },
    )


@pytest.fixture
def rico(sessao: Session) -> m.Instituicao:
    instituicao = f.instituicao(sessao)
    f.deposito(sessao, instituicao, "10000", date(2026, 1, 2))
    return instituicao


def test_compra_de_ativo_novo_cria_e_compra_de_novo_reaproveita(
    sessao: Session, rico: m.Instituicao
) -> None:
    primeira = registrar_movimentacao(
        sessao,
        NovaMovimentacao(
            transacao=compra(instituicao_id=rico.id),
            novo_ativo=NovoAtivo(tipo="fundo_listado", nome="Pátria Log", simbolo="HGLG11"),
        ),
    )
    assert primeira.ativo_criado
    assert primeira.resultado.transacao is not None
    assert primeira.resultado.transacao.ativo_id == primeira.ativo.id
    # Mesmo papel digitado de outro jeito: reaproveita (não duplica).
    segunda = registrar_movimentacao(
        sessao,
        NovaMovimentacao(
            transacao=compra(instituicao_id=rico.id, data=date(2026, 10, 2)),
            novo_ativo=NovoAtivo(tipo="fundo_listado", nome="Outro nome", simbolo="hglg11.sa"),
        ),
    )
    assert not segunda.ativo_criado
    assert segunda.ativo.id == primeira.ativo.id
    assert segunda.ativo.nome == "Pátria Log"  # o cadastro existente não muda
    assert sessao.query(m.Ativo).count() == 1


def test_ativo_existente_por_id(sessao: Session, rico: m.Instituicao) -> None:
    petr = f.acao_br(sessao, "PETR4")
    resultado = registrar_movimentacao(
        sessao, NovaMovimentacao(transacao=compra(instituicao_id=rico.id), ativo_id=petr.id)
    )
    assert not resultado.ativo_criado
    assert resultado.ativo.id == petr.id
    with pytest.raises(NaoEncontradoError):
        registrar_movimentacao(
            sessao, NovaMovimentacao(transacao=compra(instituicao_id=rico.id), ativo_id=999)
        )


@pytest.mark.parametrize("dois", [True, False])
def test_exige_ativo_id_ou_novo_ativo(sessao: Session, rico: m.Instituicao, dois: bool) -> None:
    novo = NovoAtivo(tipo="acao_br", nome="X", simbolo="XXXX3") if dois else None
    with pytest.raises(ValidacaoError, match="Escolha um ativo cadastrado"):
        registrar_movimentacao(
            sessao,
            NovaMovimentacao(
                transacao=compra(instituicao_id=rico.id),
                ativo_id=1 if dois else None,
                novo_ativo=novo,
            ),
        )


@pytest.mark.parametrize("tipo", [TipoTransacao.VENDA, TipoTransacao.PROVENTO])
def test_so_compra_e_aporte_criam_ativo(
    sessao: Session, rico: m.Instituicao, tipo: TipoTransacao
) -> None:
    with pytest.raises(ValidacaoError, match="só podem ser feitos em um ativo já cadastrado"):
        registrar_movimentacao(
            sessao,
            NovaMovimentacao(
                transacao=compra(instituicao_id=rico.id, tipo=tipo),
                novo_ativo=NovoAtivo(tipo="acao_br", nome="X", simbolo="XXXX3"),
            ),
        )
    assert sessao.query(m.Ativo).count() == 0


def test_venda_maior_que_a_posicao_continua_bloqueada(sessao: Session, rico: m.Instituicao) -> None:
    petr = f.acao_br(sessao, "PETR4")
    f.compra(sessao, petr, rico, date(2026, 10, 1), "10", "10")
    with pytest.raises(Exception, match="posição"):
        registrar_movimentacao(
            sessao,
            NovaMovimentacao(
                transacao=compra(
                    instituicao_id=rico.id,
                    tipo=TipoTransacao.VENDA,
                    data=date(2026, 10, 5),
                    quantidade=D(11),
                ),
                ativo_id=petr.id,
            ),
        )


def test_renda_fixa_semelhante_pergunta_e_respeita_a_resposta(
    sessao: Session, rico: m.Instituicao
) -> None:
    aporte = compra(
        instituicao_id=rico.id,
        tipo=TipoTransacao.APORTE,
        data=date(2026, 6, 1),
        quantidade=None,
        preco_unitario=None,
        valor=D(1000),
    )
    primeiro = registrar_movimentacao(
        sessao, NovaMovimentacao(transacao=aporte, novo_ativo=cdb_novo())
    ).ativo
    # Segunda aplicação, mesmos emissor/indexador/taxa/vencimento, outra data: pergunta.
    segunda = NovaMovimentacao(
        transacao=compra(
            instituicao_id=rico.id,
            tipo=TipoTransacao.APORTE,
            data=date(2026, 7, 1),
            quantidade=None,
            preco_unitario=None,
            valor=D(500),
        ),
        novo_ativo=cdb_novo(data_aplicacao="2026-07-01", emissor="banco x"),
    )
    with pytest.raises(AtivoSemelhanteError) as erro:
        registrar_movimentacao(sessao, segunda)
    detalhes = {d.campo: d.mensagem for d in erro.value.detalhes}
    assert detalhes["ativo_id"] == str(primeiro.id)
    assert detalhes["nome"] == "CDB Banco X 110%"
    assert erro.value.codigo == "ativo_semelhante"

    # "Sim, somar": aporte no título existente (uma linha de R$ 1.500).
    somado = registrar_movimentacao(sessao, _com(segunda, usar_ativo_id=primeiro.id))
    assert (somado.ativo.id, somado.ativo_criado) == (primeiro.id, False)
    # "Não, separar": cria outro título.
    separado = registrar_movimentacao(sessao, _com(segunda, confirmar_novo=True))
    assert separado.ativo_criado
    assert separado.ativo.id != primeiro.id
    # Escolher um ativo que não é semelhante é recusado.
    outro = f.cdb(sessao, taxa="90", nome="Outro CDB")
    with pytest.raises(ValidacaoError, match="não tem os mesmos dados"):
        registrar_movimentacao(sessao, _com(segunda, usar_ativo_id=outro.id))


def _com(dados: NovaMovimentacao, **campos: Any) -> NovaMovimentacao:
    from dataclasses import replace

    return replace(dados, **campos)


def test_poupanca_reaproveita_o_unico_ativo(sessao: Session, rico: m.Instituicao) -> None:
    def aportar() -> m.Ativo:
        return registrar_movimentacao(
            sessao,
            NovaMovimentacao(
                transacao=compra(
                    instituicao_id=rico.id,
                    tipo=TipoTransacao.APORTE,
                    quantidade=None,
                    preco_unitario=None,
                    valor=D(100),
                ),
                novo_ativo=NovoAtivo(tipo="poupanca", nome="Poupança"),
            ),
        ).ativo

    assert aportar().id == aportar().id


# ---------------------------------------------------------------- API


@pytest.fixture
def app_api() -> FastAPI:
    providers = RegistroProviders()
    providers.registrar_cotacao(CotacaoFalsa("yfinance"))
    settings = Settings(token=TOKEN_TESTE, dev=True, atualizacao_automatica=False)
    return create_app(settings, providers=providers, relogio=lambda: AGORA)


@pytest.fixture
def api(app_api: FastAPI) -> Iterator[TestClient]:
    with TestClient(app_api, headers={"Authorization": f"Bearer {TOKEN_TESTE}"}) as cliente:
        yield cliente


@pytest.fixture
def instituicao_id(api: TestClient) -> int:
    resposta = api.post("/api/instituicoes", json={"nome": "RICO", "tipo": "corretora"})
    identificador: int = resposta.json()["id"]
    api.post(
        "/api/movimentos",
        json={
            "instituicao_id": identificador,
            "tipo": "deposito",
            "data": "2026-10-01",
            "valor": "1000",
        },
    )
    return identificador


def corpo_compra(instituicao_id: int, **campos: Any) -> Json:
    return {
        "instituicao_id": instituicao_id,
        "tipo": "compra",
        "data": "2026-10-10",
        "quantidade": "10",
        "preco_unitario": "50",
        "novo_ativo": {"tipo": "etf_br", "nome": "iShares Ibovespa", "simbolo": "bova11"},
        **campos,
    }


def test_api_cria_o_ativo_e_a_transacao(api: TestClient, instituicao_id: int) -> None:
    resposta = api.post("/api/movimentacoes", json=corpo_compra(instituicao_id))
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["ativo_criado"] is True
    assert dados["ativo"]["simbolo"] == "BOVA11"
    assert dados["ativo"]["simbolo_externo"] == "BOVA11.SA"
    assert dados["transacao"]["ativo_id"] == dados["ativo"]["id"]
    assert dados["transacao"]["valor_total"] == "500.00"
    # De novo pelo mesmo ticker: reaproveita.
    de_novo = api.post("/api/movimentacoes", json=corpo_compra(instituicao_id, quantidade="1"))
    assert de_novo.json()["ativo_criado"] is False
    assert len(api.get("/api/ativos").json()) == 1


def test_api_saldo_insuficiente_nao_deixa_ativo_orfao(api: TestClient, instituicao_id: int) -> None:
    caro = corpo_compra(instituicao_id, quantidade="100")  # R$ 5.000 com R$ 1.000 em caixa
    resposta = api.post("/api/movimentacoes", json=caro)
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "saldo_insuficiente"
    assert api.get("/api/ativos").json() == []  # a criação foi desfeita junto
    aceito = api.post("/api/movimentacoes", json={**caro, "aceitar_ajuste": True})
    assert aceito.status_code == 201
    assert len(api.get("/api/ativos").json()) == 1


def test_api_transacao_invalida_nao_deixa_ativo_orfao(api: TestClient, instituicao_id: int) -> None:
    resposta = api.post("/api/movimentacoes", json=corpo_compra(instituicao_id, quantidade="0"))
    assert resposta.status_code == 422
    assert api.get("/api/ativos").json() == []


def test_api_ativo_semelhante(api: TestClient, instituicao_id: int) -> None:
    metadados = {
        "indexador": "cdi",
        "taxa": "110",
        "data_aplicacao": "2026-10-02",
        "vencimento": "2028-01-03",
        "emissor": "Banco X",
        "liquidez": "diaria",
    }
    cdb: Json = {"tipo": "renda_fixa", "nome": "CDB X", "metadados": metadados}
    aporte = {
        "instituicao_id": instituicao_id,
        "tipo": "aporte",
        "data": "2026-10-02",
        "valor": "100",
        "novo_ativo": cdb,
    }
    assert api.post("/api/movimentacoes", json=aporte).status_code == 201
    outra = {**aporte, "data": "2026-10-05"}
    outra["novo_ativo"] = {**cdb, "metadados": {**metadados, "data_aplicacao": "2026-10-05"}}
    resposta = api.post("/api/movimentacoes", json=outra)
    assert resposta.status_code == 409
    erro = resposta.json()
    assert erro["codigo"] == "ativo_semelhante"
    existente = next(d["mensagem"] for d in erro["detalhes"] if d["campo"] == "ativo_id")
    somado = api.post("/api/movimentacoes", json={**outra, "usar_ativo_id": int(existente)})
    assert somado.json()["ativo"]["id"] == int(existente)
    separado = api.post("/api/movimentacoes", json={**outra, "confirmar_novo": True})
    assert separado.json()["ativo_criado"] is True


def test_api_movimentacao_exige_token_e_valida(app_api: FastAPI) -> None:
    with TestClient(app_api) as sem_token:
        assert sem_token.post("/api/movimentacoes", json={}).status_code == 401
        assert sem_token.get("/api/simbolos/busca", params={"tipo": "acao_br"}).status_code == 401
    with TestClient(app_api, headers={"Authorization": f"Bearer {TOKEN_TESTE}"}) as api:
        resposta = api.post("/api/movimentacoes", json={"tipo": "compra"})
        assert resposta.status_code == 422
        assert resposta.json()["codigo"] == "validacao"


def test_api_simbolos_busca_listas_e_atualizar(api: TestClient) -> None:
    busca = api.get("/api/simbolos/busca", params={"tipo": "acao_br", "q": "PETR4"})
    assert busca.status_code == 200
    dados = busca.json()
    assert dados["itens"] == []
    assert dados["bolsa"] == "B3"
    assert dados["lista_disponivel"] is False
    assert dados["atualizando_lista"] is False  # agendador parado nos testes
    listas = api.get("/api/simbolos/listas").json()
    assert listas == {"em_andamento": False, "listas": []}  # sem fontes registradas
    assert api.post("/api/simbolos/atualizar").status_code == 202
    desconhecido = api.get("/api/simbolos/busca", params={"tipo": "xyz", "q": "a"})
    assert desconhecido.status_code == 422
