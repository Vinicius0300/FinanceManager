"""Providers de cotação e indicadores com a rede simulada (``httpx2.MockTransport``).

Nenhum teste acessa a internet nem espera de verdade: ``dormir`` só registra as esperas e
``relogio`` é um contador controlado pelo teste. As respostas imitam o formato real de
cada fonte (conferido em 29/10/2026).
"""

import io
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx2
import pytest

from app.domain.enums import TipoIndicador
from app.domain.indicadores import PontoIndicador
from app.providers.base import (
    AlvoCotacao,
    Cotacao,
    Fechamento,
    FonteIndisponivelError,
    LimiteRequisicoesError,
    PedidoHistorico,
    ProviderError,
    RespostaInvalidaError,
    SimboloNaoEncontradoError,
    valor_cambio,
    valor_cotacao,
    valor_taxa,
)
from app.providers.catalogo import criar_registro_providers
from app.providers.coingecko import ProviderCoinGecko
from app.providers.cvm import ProviderCvm
from app.providers.http import ClienteHttp
from app.providers.sgs import ProviderSgs
from app.providers.tesouro import ProviderTesouro
from app.providers.yahoo import ProviderYahoo

D = Decimal
SP = ZoneInfo("America/Sao_Paulo")
Manipulador = Callable[[httpx2.Request], httpx2.Response]


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.agora += segundos


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


def http(
    manipulador: Manipulador, relogio: Relogio, *, intervalo: float = 0, tentativas: int = 3
) -> ClienteHttp:
    return ClienteHttp(
        "Fonte X",
        transporte=httpx2.MockTransport(manipulador),
        tentativas=tentativas,
        intervalo_minimo=intervalo,
        dormir=relogio.dormir,
        relogio=relogio,
    )


def alvo(
    ativo_id: int = 1,
    tipo: str = "acao_br",
    simbolo: str | None = "PETR4",
    moeda: str = "BRL",
    simbolo_externo: str | None = None,
    metadados: dict[str, object] | None = None,
) -> AlvoCotacao:
    return AlvoCotacao(
        ativo_id=ativo_id,
        tipo=tipo,
        nome=f"Ativo {ativo_id}",
        moeda=moeda,
        simbolo=simbolo,
        simbolo_externo=simbolo_externo,
        metadados=metadados or {},
    )


def epoch(ano: int, mes: int, dia: int, hora: int = 0, minuto: int = 0, fuso: ZoneInfo = SP) -> int:
    return int(datetime(ano, mes, dia, hora, minuto, tzinfo=fuso).timestamp())


# ---------------------------------------------------------------- arredondamento


def test_valores_sao_arredondados_e_normalizados() -> None:
    # float da fonte → texto curto → Decimal; ruído de float some com as casas da fonte.
    assert valor_cotacao(58.68000030517578, "x", 2) == D("58.68")
    assert valor_cotacao("44.636723400000", "x") == D("44.6367234")  # 12 → 8 casas
    assert valor_cotacao("0.123456789", "x") == D("0.12345679")  # meio-par: ...789 → ...79
    assert str(valor_cotacao(52.2, "x", 2)) == "52.2"  # sem zeros à direita
    assert valor_cambio("5.12345678", "x") == D("5.123457")
    assert valor_taxa("-0.11", "x") == D("-0.11")  # IPCA de deflação
    with pytest.raises(RespostaInvalidaError, match="zerada"):
        valor_cotacao("0.000000001", "x")  # arredonda para 0
    with pytest.raises(RespostaInvalidaError, match="ausente"):
        valor_cotacao(None, "x")
    with pytest.raises(RespostaInvalidaError, match="inválido"):
        valor_cotacao("abc", "x")
    with pytest.raises(RespostaInvalidaError, match="câmbio zerado"):
        valor_cambio("0", "x")


# ---------------------------------------------------------------- cliente HTTP


def test_retry_com_backoff_em_erro_do_servidor(relogio: Relogio) -> None:
    respostas = iter([httpx2.Response(503), httpx2.Response(500), httpx2.Response(200, json=[1])])
    cliente = http(lambda _: next(respostas), relogio)
    assert cliente.get_json("https://x.test/a") == [1]
    assert relogio.esperas == [1.0, 2.0]  # 1 s, 2 s


def test_esgota_tentativas_e_falha_com_mensagem(relogio: Relogio) -> None:
    cliente = http(lambda _: httpx2.Response(502), relogio)
    with pytest.raises(FonteIndisponivelError, match=r"Fonte X está fora do ar.*502"):
        cliente.get_json("https://x.test/a")
    assert len(relogio.esperas) == 2


def test_rate_limit_respeita_retry_after(relogio: Relogio) -> None:
    respostas = iter(
        [httpx2.Response(429, headers={"Retry-After": "7"}), httpx2.Response(200, json={})]
    )
    cliente = http(lambda _: next(respostas), relogio)
    assert cliente.get_json("https://x.test/a") == {}
    assert relogio.esperas == [7.0]
    sempre_429 = http(lambda _: httpx2.Response(429), relogio, tentativas=1)
    with pytest.raises(LimiteRequisicoesError, match="muitas requisições"):
        sempre_429.get_json("https://x.test/a")


def test_falha_de_rede_e_timeout(relogio: Relogio) -> None:
    def sem_rede(requisicao: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("sem rede", request=requisicao)

    def lento(requisicao: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("lento", request=requisicao)

    with pytest.raises(FonteIndisponivelError, match="Verifique a conexão"):
        http(sem_rede, relogio).get_json("https://x.test/a")
    with pytest.raises(FonteIndisponivelError, match="não respondeu a tempo"):
        http(lento, relogio, tentativas=1).get_json("https://x.test/a")


def test_erro_4xx_e_404(relogio: Relogio) -> None:
    cliente = http(lambda _: httpx2.Response(404), relogio)
    assert cliente.get_json("https://x.test/a", aceitar_404=True) is None
    assert cliente.get_texto("https://x.test/a", aceitar_404=True) is None
    with pytest.raises(ProviderError, match="recusou a consulta \\(erro 404\\)"):
        cliente.get_json("https://x.test/a")
    assert relogio.esperas == []  # 4xx não é repetido


def test_resposta_que_nao_e_json(relogio: Relogio) -> None:
    cliente = http(lambda _: httpx2.Response(200, text="<html>"), relogio)
    with pytest.raises(RespostaInvalidaError, match="não é JSON"):
        cliente.get_json("https://x.test/a")


def test_cache_curto_e_intervalo_minimo(relogio: Relogio) -> None:
    chamadas: list[str] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        chamadas.append(str(requisicao.url))
        return httpx2.Response(200, json={"n": len(chamadas)})

    cliente = http(manipulador, relogio, intervalo=2.0)
    assert cliente.get_json("https://x.test/a", {"p": 1}, ttl=60) == {"n": 1}
    assert cliente.get_json("https://x.test/a", {"p": 1}, ttl=60) == {"n": 1}  # cache
    assert cliente.get_json("https://x.test/a", {"p": 2}, ttl=60) == {"n": 2}  # outra chave
    assert relogio.esperas == [2.0]  # segunda requisição real esperou o intervalo
    relogio.agora += 61
    assert cliente.get_json("https://x.test/a", {"p": 1}, ttl=60) == {"n": 3}  # expirou
    cliente.limpar_cache()
    assert len(chamadas) == 3


def test_baixar_arquivo_com_retry(relogio: Relogio) -> None:
    respostas = iter([httpx2.Response(500), httpx2.Response(200, content=b"abc" * 1000)])
    cliente = http(lambda _: next(respostas), relogio)
    destino = io.BytesIO()
    assert cliente.baixar_arquivo("https://x.test/f.zip", destino) is True
    assert destino.read() == b"abc" * 1000
    nao_existe = http(lambda _: httpx2.Response(404), relogio)
    assert (
        nao_existe.baixar_arquivo("https://x.test/f.zip", io.BytesIO(), aceitar_404=True) is False
    )


def test_baixar_arquivo_sem_rede(relogio: Relogio) -> None:
    def sem_rede(requisicao: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("x", request=requisicao)

    with pytest.raises(FonteIndisponivelError):
        http(sem_rede, relogio).baixar_arquivo("https://x.test/f.zip", io.BytesIO())
    assert relogio.esperas == [1.0, 2.0]


# ---------------------------------------------------------------- Yahoo


def resposta_yahoo(
    simbolo: str,
    preco: float,
    instante: int,
    *,
    moeda: str = "BRL",
    fuso: str = "America/Sao_Paulo",
    marcas: list[int] | None = None,
    fechamentos: list[float | None] | None = None,
    price_hint: int = 2,
) -> dict[str, object]:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": moeda,
                        "symbol": simbolo,
                        "exchangeTimezoneName": fuso,
                        "regularMarketPrice": preco,
                        "regularMarketTime": instante,
                        "priceHint": price_hint,
                    },
                    "timestamp": marcas or [],
                    "indicators": {"quote": [{"close": fechamentos or []}]},
                }
            ],
            "error": None,
        }
    }


def test_yahoo_identifica_simbolos() -> None:
    yahoo = ProviderYahoo(ClienteHttp("Y"))
    assert yahoo.identificar(alvo(simbolo="petr4")) == "PETR4.SA"
    assert yahoo.identificar(alvo(simbolo="BOVA11.SA")) == "BOVA11.SA"
    assert yahoo.identificar(alvo(tipo="acao_us", simbolo="AAPL", moeda="USD")) == "AAPL"
    assert yahoo.identificar(alvo(simbolo="PETR4", simbolo_externo=" PETR3.SA ")) == "PETR3.SA"
    with pytest.raises(SimboloNaoEncontradoError, match="informe o símbolo"):
        yahoo.identificar(alvo(simbolo=None))


def test_yahoo_cotacao_atual(relogio: Relogio) -> None:
    urls: list[str] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        urls.append(requisicao.url.path)
        if "PETR4.SA" in requisicao.url.path:
            # 28/10/2026 17:05 em Brasília
            return httpx2.Response(
                200, json=resposta_yahoo("PETR4.SA", 52.20000076293945, epoch(2026, 10, 28, 17, 5))
            )
        if "AAPL" in requisicao.url.path:
            return httpx2.Response(
                200,
                json=resposta_yahoo("AAPL", 230.1, epoch(2026, 10, 28, 16), moeda="GBp"),
            )
        return httpx2.Response(
            404, json={"chart": {"result": None, "error": {"code": "Not Found"}}}
        )

    yahoo = ProviderYahoo(http(manipulador, relogio))
    resultados = yahoo.cotacoes(
        [alvo(1), alvo(2, "acao_us", "AAPL", "USD"), alvo(3, simbolo="XXXX3")]
    )
    assert resultados[1] == Cotacao(
        data=date(2026, 10, 28),
        data_hora=datetime(2026, 10, 28, 20, 5, tzinfo=UTC),
        valor=D("52.2"),
    )
    assert isinstance(resultados[2], RespostaInvalidaError)
    assert "em GBP, mas o ativo está em USD" in resultados[2].mensagem
    assert isinstance(resultados[3], SimboloNaoEncontradoError)
    assert "XXXX3.SA" in resultados[3].mensagem
    assert urls == [
        "/v8/finance/chart/PETR4.SA",
        "/v8/finance/chart/AAPL",
        "/v8/finance/chart/XXXX3.SA",
    ]


def test_yahoo_historico_usa_data_da_bolsa_e_pula_dias_sem_negocio(relogio: Relogio) -> None:
    # Candles da bolsa de NY às 9h30 locais: a data é a de Nova York.
    ny = ZoneInfo("America/New_York")
    marcas = [epoch(2026, 10, d, 9, 30, ny) for d in (23, 26, 27, 28)]
    corpo = resposta_yahoo(
        "AAPL",
        231.0,
        epoch(2026, 10, 28, 16, 0, ny),
        moeda="USD",
        fuso="America/New_York",
        marcas=marcas,
        fechamentos=[228.5, None, 229.99000549316406, 231.0],
    )
    parametros: list[dict[str, str]] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        parametros.append(dict(requisicao.url.params))
        return httpx2.Response(200, json=corpo)

    yahoo = ProviderYahoo(http(manipulador, relogio))
    pedido = PedidoHistorico(alvo(1, "acao_us", "AAPL", "USD"), date(2026, 10, 24))
    resultado = yahoo.historicos([pedido], date(2026, 10, 28))[1]
    assert resultado == [
        Fechamento(date(2026, 10, 27), D("229.99")),
        Fechamento(date(2026, 10, 28), D("231")),
    ]  # 23/10 fora do início pedido; 26/10 sem negócio (close nulo)
    assert parametros[0]["interval"] == "1d"
    assert int(parametros[0]["period1"]) == int(datetime(2026, 10, 24, tzinfo=UTC).timestamp())
    assert int(parametros[0]["period2"]) == int(datetime(2026, 10, 29, tzinfo=UTC).timestamp())


def test_yahoo_desfaz_o_ajuste_por_desdobramento(relogio: Relogio) -> None:
    # Desdobramento 1:2 em 10/03/2026 (data "ex"). O Yahoo devolve o close de antes do
    # split já dividido por 2: 20,00 em 09/03 era 40,00 de verdade. Depois dele, nada muda.
    # Grupamento 10:1 (numerator 1, denominator 10) em 20/03: antes dele, ×0,1.
    corpo = resposta_yahoo(
        "TST3.SA",
        2.1,
        epoch(2026, 3, 23, 17),
        marcas=[epoch(2026, 3, 9, 10), epoch(2026, 3, 10, 10), epoch(2026, 3, 23, 10)],
        fechamentos=[2.0, 2.05, 21.0],
    )
    corpo["chart"]["result"][0]["events"] = {  # type: ignore[index]
        "splits": {
            "1": {"date": epoch(2026, 3, 10, 10), "numerator": 2, "denominator": 1},
            "2": {"date": epoch(2026, 3, 20, 10), "numerator": 1, "denominator": 10},
            "3": {"date": epoch(2026, 3, 21, 10), "numerator": 0, "denominator": 1},  # inválido
        }
    }
    parametros: list[dict[str, str]] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        parametros.append(dict(requisicao.url.params))
        return httpx2.Response(200, json=corpo)

    yahoo = ProviderYahoo(http(manipulador, relogio))
    pedido = PedidoHistorico(alvo(1, simbolo="TST3"), date(2026, 3, 1))
    assert yahoo.historicos([pedido], date(2026, 3, 23))[1] == [
        Fechamento(date(2026, 3, 9), D("0.4")),  # 2,00 × 2 × 0,1
        Fechamento(date(2026, 3, 10), D("0.205")),  # 2,05 × 0,1 (o 1:2 já valeu nesse dia)
        Fechamento(date(2026, 3, 23), D("21")),
    ]
    assert parametros[0]["events"] == "split"


def test_yahoo_cambio_reserva(relogio: Relogio) -> None:
    corpo = resposta_yahoo(
        "USDBRL=X",
        5.3712,
        epoch(2026, 10, 28, 12),
        marcas=[epoch(2026, 10, 27), epoch(2026, 10, 28)],
        fechamentos=[5.364999771118164, 5.371200084686279],
        price_hint=4,
    )
    caminhos: list[str] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        caminhos.append(requisicao.url.path)
        return httpx2.Response(200, json=corpo)

    yahoo = ProviderYahoo(http(manipulador, relogio))
    assert yahoo.suporta(TipoIndicador.CAMBIO, "USD")
    assert not yahoo.suporta(TipoIndicador.CDI, "BRL")
    assert yahoo.serie(TipoIndicador.CAMBIO, "USD", date(2026, 10, 27), date(2026, 10, 28)) == [
        PontoIndicador(date(2026, 10, 27), D("5.365")),
        PontoIndicador(date(2026, 10, 28), D("5.3712")),
    ]
    assert caminhos == ["/v8/finance/chart/USDBRL=X"]
    with pytest.raises(ProviderError, match="não fornece cdi"):
        yahoo.serie(TipoIndicador.CDI, "BRL", date(2026, 1, 1), date(2026, 1, 2))


def test_yahoo_resposta_sem_meta(relogio: Relogio) -> None:
    yahoo = ProviderYahoo(
        http(lambda _: httpx2.Response(200, json={"chart": {"result": [{}]}}), relogio)
    )
    resultado = yahoo.cotacoes([alvo()])[1]
    assert isinstance(resultado, RespostaInvalidaError)


# ---------------------------------------------------------------- CoinGecko


def test_coingecko_identifica_pela_tabela_pelo_externo_e_pela_pesquisa(relogio: Relogio) -> None:
    pesquisas: list[str] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        pesquisas.append(requisicao.url.params["query"])
        return httpx2.Response(
            200,
            json={
                "coins": [
                    {"id": "pepe-falso", "symbol": "PEPE", "market_cap_rank": None},
                    {"id": "pepe", "symbol": "PEPE", "market_cap_rank": 40},
                    {"id": "pepe-2", "symbol": "PEPE", "market_cap_rank": 900},
                    {"id": "pepecoin", "symbol": "PEPEC", "market_cap_rank": 5},
                ]
            },
        )

    gecko = ProviderCoinGecko(http(manipulador, relogio))
    assert gecko.identificador_persistente is True
    assert gecko.identificar(alvo(tipo="cripto", simbolo="btc")) == "bitcoin"
    assert gecko.identificar(alvo(tipo="cripto", simbolo="X", simbolo_externo="Meu-Id")) == "meu-id"
    assert (
        gecko.identificar(alvo(tipo="cripto", simbolo="pepe")) == "pepe"
    )  # maior valor de mercado
    assert pesquisas == ["PEPE"]
    with pytest.raises(SimboloNaoEncontradoError, match="não encontrou a criptomoeda ZZZ"):
        gecko.identificar(alvo(tipo="cripto", simbolo="zzz"))
    with pytest.raises(SimboloNaoEncontradoError, match="informe o símbolo"):
        gecko.identificar(alvo(tipo="cripto", simbolo=None))


def test_coingecko_cotacoes_numa_unica_chamada(relogio: Relogio) -> None:
    chamadas: list[dict[str, str]] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        chamadas.append(dict(requisicao.url.params))
        return httpx2.Response(
            200,
            json={
                "bitcoin": {"brl": 426934, "usd": 79289.5, "last_updated_at": 1793310221},
                "ethereum": {"brl": 15000.123456789, "usd": 2790, "last_updated_at": 1793310200},
                "tether": {"brl": 5.37},  # sem horário
            },
        )

    gecko = ProviderCoinGecko(http(manipulador, relogio))
    resultados = gecko.cotacoes(
        [
            alvo(1, "cripto", "BTC", "BRL"),
            alvo(2, "cripto", "BTC", "USD"),
            alvo(3, "cripto", "ETH", "BRL"),
            alvo(4, "cripto", "USDT", "BRL"),
            alvo(5, "cripto", "X", "BRL", simbolo_externo="nao-existe"),
            alvo(6, "cripto", None, "BRL"),
        ]
    )
    assert chamadas == [
        {
            "ids": "bitcoin,ethereum,nao-existe,tether",
            "vs_currencies": "brl,usd",
            "include_last_updated_at": "true",
        }
    ]
    instante = datetime.fromtimestamp(1793310221, tz=UTC)
    assert resultados[1] == Cotacao(date(2026, 10, 29), instante, D("426934"))
    btc_usd = resultados[2]
    assert isinstance(btc_usd, Cotacao)
    assert btc_usd.valor == D("79289.5")
    eth = resultados[3]
    assert isinstance(eth, Cotacao)
    assert eth.valor == D("15000.12345679")
    assert isinstance(resultados[4], RespostaInvalidaError)
    assert isinstance(resultados[5], SimboloNaoEncontradoError)
    assert isinstance(resultados[6], SimboloNaoEncontradoError)


def test_coingecko_falha_geral_vale_para_todos(relogio: Relogio) -> None:
    gecko = ProviderCoinGecko(http(lambda _: httpx2.Response(503), relogio, tentativas=1))
    resultados = gecko.cotacoes([alvo(1, "cripto", "BTC"), alvo(2, "cripto", "ETH")])
    assert all(isinstance(r, FonteIndisponivelError) for r in resultados.values())


def test_coingecko_historico_ultimo_valor_de_cada_dia(relogio: Relogio) -> None:
    def ms(dia: int, hora: int) -> int:
        return epoch(2026, 10, dia, hora) * 1000

    parametros: list[dict[str, str]] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        parametros.append(dict(requisicao.url.params))
        assert requisicao.url.path == "/api/v3/coins/bitcoin/market_chart/range"
        return httpx2.Response(
            200,
            json={
                "prices": [
                    [ms(27, 21), 410000.5],
                    [ms(27, 23), 411000.25],  # último do dia 27 em Brasília
                    [ms(28, 1), 412000],
                    [ms(28, 12), 413000.987654321],
                    "lixo",
                ]
            },
        )

    gecko = ProviderCoinGecko(http(manipulador, relogio))
    pedido = PedidoHistorico(alvo(1, "cripto", "BTC"), date(2025, 1, 1))
    resultado = gecko.historicos([pedido], date(2026, 10, 28))[1]
    assert resultado == [
        Fechamento(date(2026, 10, 27), D("411000.25")),
        Fechamento(date(2026, 10, 28), D("413000.98765432")),
    ]
    # Plano público: no máximo 364 dias para trás.
    assert int(parametros[0]["from"]) == epoch(2025, 10, 29)
    assert parametros[0]["vs_currency"] == "brl"


def test_coingecko_historico_nao_encontrado(relogio: Relogio) -> None:
    gecko = ProviderCoinGecko(http(lambda _: httpx2.Response(404), relogio))
    pedido = PedidoHistorico(alvo(1, "cripto", "BTC"), date(2026, 10, 1))
    assert isinstance(gecko.historicos([pedido], date(2026, 10, 28))[1], SimboloNaoEncontradoError)


# ---------------------------------------------------------------- SGS


def test_sgs_series_unidades_e_paginacao(relogio: Relogio) -> None:
    pedidos: list[tuple[str, dict[str, str]]] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        params = dict(requisicao.url.params)
        pedidos.append((requisicao.url.path, params))
        if params["dataInicial"] == "01/01/2015":
            return httpx2.Response(404, json={"error": "Value(s) not found"})
        return httpx2.Response(
            200,
            json=[
                {"data": "27/10/2026", "valor": "13.65"},
                {"data": "28/10/2026", "valor": ""},  # data publicada antes do valor
                {"data": "29/10/2026", "valor": "13.65"},
            ],
        )

    sgs = ProviderSgs(http(manipulador, relogio))
    pontos = sgs.serie(TipoIndicador.CDI, "BRL", date(2015, 1, 1), date(2026, 10, 29))
    assert pontos == [
        PontoIndicador(date(2026, 10, 27), D("13.65")),
        PontoIndicador(date(2026, 10, 29), D("13.65")),
    ]
    # 2015-01-01 até 2026-10-29 em janelas de 5 anos (a API recusa mais de 10).
    assert [(p["dataInicial"], p["dataFinal"]) for _, p in pedidos] == [
        ("01/01/2015", "31/12/2019"),
        ("01/01/2020", "30/12/2024"),
        ("31/12/2024", "29/10/2026"),
    ]
    assert {caminho for caminho, _ in pedidos} == {"/dados/serie/bcdata.sgs.4389/dados"}


@pytest.mark.parametrize(
    ("tipo", "moeda", "codigo"),
    [
        (TipoIndicador.CDI, "BRL", 4389),
        (TipoIndicador.SELIC, "BRL", 432),
        (TipoIndicador.IPCA, "BRL", 433),
        (TipoIndicador.CAMBIO, "USD", 1),
    ],
)
def test_sgs_codigos_das_series(
    relogio: Relogio, tipo: TipoIndicador, moeda: str, codigo: int
) -> None:
    caminhos: list[str] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        caminhos.append(requisicao.url.path)
        return httpx2.Response(200, json=[])

    ProviderSgs(http(manipulador, relogio)).serie(tipo, moeda, date(2026, 1, 1), date(2026, 1, 2))
    assert caminhos == [f"/dados/serie/bcdata.sgs.{codigo}/dados"]


def test_sgs_selic_meta_ignora_datas_futuras_e_ptax_arredonda(relogio: Relogio) -> None:
    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        if "sgs.432" in requisicao.url.path:
            # A série 432 lista a meta até a próxima reunião do Copom.
            return httpx2.Response(
                200,
                json=[
                    {"data": "29/10/2026", "valor": "13.75"},
                    {"data": "30/10/2026", "valor": "13.75"},
                    {"data": "04/11/2026", "valor": "13.75"},
                ],
            )
        return httpx2.Response(200, json=[{"data": "28/10/2026", "valor": "5.3721547"}])

    sgs = ProviderSgs(http(manipulador, relogio))
    selic = sgs.serie(TipoIndicador.SELIC, "BRL", date(2026, 10, 29), date(2026, 10, 29))
    assert selic == [PontoIndicador(date(2026, 10, 29), D("13.75"))]
    ptax = sgs.serie(TipoIndicador.CAMBIO, "USD", date(2026, 10, 28), date(2026, 10, 29))
    assert ptax == [PontoIndicador(date(2026, 10, 28), D("5.372155"))]


def test_sgs_erros(relogio: Relogio) -> None:
    sgs = ProviderSgs(http(lambda _: httpx2.Response(200, json={"x": 1}), relogio))
    assert not sgs.suporta(TipoIndicador.CAMBIO, "EUR")
    with pytest.raises(ProviderError, match="não fornece cambio em EUR"):
        sgs.serie(TipoIndicador.CAMBIO, "EUR", date(2026, 1, 1), date(2026, 1, 2))
    with pytest.raises(RespostaInvalidaError, match="resposta inesperada"):
        sgs.serie(TipoIndicador.CDI, "BRL", date(2026, 1, 1), date(2026, 1, 2))
    data_ruim = ProviderSgs(
        http(lambda _: httpx2.Response(200, json=[{"data": "2026-01-01", "valor": "1"}]), relogio)
    )
    with pytest.raises(RespostaInvalidaError, match="data inválida"):
        data_ruim.serie(TipoIndicador.CDI, "BRL", date(2026, 1, 1), date(2026, 1, 2))
    item_ruim = ProviderSgs(http(lambda _: httpx2.Response(200, json=["x"]), relogio))
    with pytest.raises(RespostaInvalidaError, match="item inesperado"):
        item_ruim.serie(TipoIndicador.CDI, "BRL", date(2026, 1, 1), date(2026, 1, 2))


# ---------------------------------------------------------------- Tesouro

CSV_TESOURO = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
    "Tesouro Selic;01/03/2029;28/10/2026;0,05;0,06;20166,29;20151,28;20151,28\n"
    "Tesouro Selic;01/03/2029;27/10/2026;0,05;0,06;20160,00;20145,10;20145,10\n"
    "Tesouro IPCA+ com Juros Semestrais;15/05/2035;28/10/2026;7,10;7,22;4321,12;4290,55;4290,55\n"
    "Tesouro IPCA+;15/05/2035;28/10/2026;7,10;7,22;2300,00;2290,00;2290,00\n"
    "linha;quebrada\n"
)


def tesouro(alvo_id: int, titulo: str, vencimento: str) -> AlvoCotacao:
    return alvo(
        alvo_id,
        "tesouro_direto",
        None,
        metadados={"titulo": titulo, "vencimento": vencimento},
    )


def test_tesouro_pu_de_venda_por_titulo_e_vencimento(relogio: Relogio) -> None:
    downloads: list[str] = []

    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        downloads.append(requisicao.url.path)
        return httpx2.Response(200, content=CSV_TESOURO.encode("latin-1"))

    provider = ProviderTesouro(http(manipulador, relogio))
    selic = tesouro(1, "selic", "2029-03-01")
    ipca_juros = tesouro(2, "ipca_juros", "2035-05-15")
    inexistente = tesouro(3, "prefixado", "2031-01-01")
    sem_dados = alvo(4, "tesouro_direto", None, metadados={})
    assert provider.identificar(selic) == "tesouro selic 2029-03-01"
    cotacoes = provider.cotacoes([selic, ipca_juros, inexistente, sem_dados])
    assert cotacoes[1] == Cotacao(
        date(2026, 10, 28), datetime(2026, 10, 28, 18, tzinfo=SP), D("20151.28")
    )
    cotacao_ipca = cotacoes[2]
    assert isinstance(cotacao_ipca, Cotacao)
    assert cotacao_ipca.valor == D("4290.55")  # não confunde com o IPCA+ sem juros
    assert isinstance(cotacoes[3], SimboloNaoEncontradoError)
    assert isinstance(cotacoes[4], SimboloNaoEncontradoError)
    historico = provider.historicos(
        [PedidoHistorico(selic, date(2026, 1, 1)), PedidoHistorico(inexistente, date(2026, 1, 1))],
        date(2026, 10, 28),
    )
    assert historico[1] == [
        Fechamento(date(2026, 10, 27), D("20145.1")),
        Fechamento(date(2026, 10, 28), D("20151.28")),
    ]
    assert isinstance(historico[3], SimboloNaoEncontradoError)
    assert len(downloads) == 1  # cache: cotação e histórico do mesmo ciclo baixam uma vez


def test_tesouro_formato_mudou_ou_fora_do_ar(relogio: Relogio) -> None:
    mudou = ProviderTesouro(http(lambda _: httpx2.Response(200, content=b"a;b\n1;2\n"), relogio))
    resultado = mudou.cotacoes([tesouro(1, "selic", "2029-03-01")])[1]
    assert isinstance(resultado, RespostaInvalidaError)
    fora = ProviderTesouro(http(lambda _: httpx2.Response(500), relogio, tentativas=1))
    historico = fora.historicos(
        [PedidoHistorico(tesouro(1, "selic", "2029-03-01"), date(2026, 1, 1))], date(2026, 10, 28)
    )
    assert isinstance(historico[1], FonteIndisponivelError)
    vazio = ProviderTesouro(http(lambda _: httpx2.Response(200, content=b""), relogio))
    assert isinstance(vazio.cotacoes([tesouro(1, "selic", "2029-03-01")])[1], RespostaInvalidaError)


# ---------------------------------------------------------------- CVM

CNPJ = "00.017.024/0001-53"
CNPJ_DIGITOS = "00017024000153"


def zip_cvm(nome: str, csv_texto: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as arquivo:
        arquivo.writestr(nome, csv_texto.encode("latin-1"))
    return buffer.getvalue()


CSV_175 = (
    "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;"
    "VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
    f"CLASSES - FIF;{CNPJ};;2026-10-01;1;44.636723400000;1;0;0;1\n"
    f"CLASSES - FIF;{CNPJ};;2026-10-02;1;44.655755500000;1;0;0;1\n"
    "CLASSES - FIF;11.222.333/0001-81;SUB1;2026-10-02;1;2.500000000000;1;0;0;1\n"
    "CLASSES - FIF;11.222.333/0001-81;SUB2;2026-10-02;1;3.000000000000;1;0;0;1\n"
    f"CLASSES - FIF;{CNPJ};;data-ruim;1;1;1;0;0;1\n"
)
CSV_ANTIGO = (
    "TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
    f"FI;{CNPJ};2026-09-29;1;44.600000000000;1;0;0;1\n"
    f"FI;{CNPJ};2026-09-30;1;44.610000000000;1;0;0;1\n"
)


def fundo(alvo_id: int, cnpj: str = CNPJ, subclasse: str | None = None) -> AlvoCotacao:
    return alvo(alvo_id, "fundo", None, simbolo_externo=subclasse, metadados={"cnpj": cnpj})


def servidor_cvm(arquivos: dict[str, bytes], baixados: list[str]) -> Manipulador:
    def manipulador(requisicao: httpx2.Request) -> httpx2.Response:
        nome = requisicao.url.path.rsplit("/", 1)[-1]
        baixados.append(nome)
        if nome not in arquivos:
            return httpx2.Response(404)
        return httpx2.Response(200, content=arquivos[nome])

    return manipulador


def test_cvm_cota_mais_recente_e_subclasses(relogio: Relogio) -> None:
    baixados: list[str] = []
    arquivos = {"inf_diario_fi_202610.zip": zip_cvm("inf_diario_fi_202610.csv", CSV_175)}
    cvm = ProviderCvm(
        http(servidor_cvm(arquivos, baixados), relogio),
        hoje=lambda: date(2026, 10, 29),
        relogio=relogio,
    )
    assert cvm.identificar(fundo(1)) == CNPJ_DIGITOS
    assert cvm.identificar(fundo(2, "11222333000181", "SUB2")) == "11222333000181/SUB2"
    resultados = cvm.cotacoes(
        [fundo(1), fundo(2, "11222333000181", "SUB2"), fundo(3, "11222333000181"), fundo(4, "123")]
    )
    assert resultados[1] == Cotacao(
        date(2026, 10, 2), datetime(2026, 10, 2, 18, tzinfo=SP), D("44.6557555")
    )
    sub2 = resultados[2]
    assert isinstance(sub2, Cotacao)
    assert sub2.valor == D("3")
    # Classe com subclasses e sem subclasse informada: não chuta qual é a cota.
    assert isinstance(resultados[3], SimboloNaoEncontradoError)
    assert "subclasses" in resultados[3].mensagem
    assert isinstance(resultados[4], SimboloNaoEncontradoError)
    assert baixados == ["inf_diario_fi_202610.zip", "inf_diario_fi_202609.zip"]
    # O mês anterior foi tentado porque o fundo 3 ficou sem cota no mês corrente.


def test_cvm_mes_corrente_ainda_nao_publicado_usa_o_anterior(relogio: Relogio) -> None:
    baixados: list[str] = []
    arquivos = {"inf_diario_fi_202609.zip": zip_cvm("inf_diario_fi_202609.csv", CSV_ANTIGO)}
    cvm = ProviderCvm(
        http(servidor_cvm(arquivos, baixados), relogio),
        hoje=lambda: date(2026, 10, 1),
        relogio=relogio,
    )
    resultado = cvm.cotacoes([fundo(1)])[1]
    assert resultado == Cotacao(date(2026, 9, 30), datetime(2026, 9, 30, 18, tzinfo=SP), D("44.61"))
    assert baixados == ["inf_diario_fi_202610.zip", "inf_diario_fi_202609.zip"]


def test_cvm_historico_junta_meses_e_formatos(relogio: Relogio) -> None:
    baixados: list[str] = []
    arquivos = {
        "inf_diario_fi_202609.zip": zip_cvm("inf_diario_fi_202609.csv", CSV_ANTIGO),
        "inf_diario_fi_202610.zip": zip_cvm("inf_diario_fi_202610.csv", CSV_175),
    }
    cvm = ProviderCvm(
        http(servidor_cvm(arquivos, baixados), relogio),
        hoje=lambda: date(2026, 10, 29),
        relogio=relogio,
    )
    pedidos = [
        PedidoHistorico(fundo(1), date(2026, 9, 30)),
        PedidoHistorico(fundo(2, "1"), date(2026, 9, 1)),
    ]
    resultado = cvm.historicos(pedidos, date(2026, 10, 29))
    assert resultado[1] == [
        Fechamento(date(2026, 9, 30), D("44.61")),
        Fechamento(date(2026, 10, 1), D("44.6367234")),
        Fechamento(date(2026, 10, 2), D("44.6557555")),
    ]
    assert isinstance(resultado[2], SimboloNaoEncontradoError)
    assert baixados == ["inf_diario_fi_202609.zip", "inf_diario_fi_202610.zip"]
    # Cotação logo depois reaproveita o mês corrente já lido (cache do ciclo).
    cvm.cotacoes([fundo(1)])
    assert len(baixados) == 2
    relogio.agora += 3600  # cache expirado
    cvm.cotacoes([fundo(1)])
    assert len(baixados) == 3
    cvm.limpar_cache()


def test_cvm_arquivo_corrompido_ou_formato_novo(relogio: Relogio) -> None:
    arquivos = {
        "inf_diario_fi_202610.zip": b"nao e zip",
        "inf_diario_fi_202609.zip": zip_cvm("x.csv", "A;B\n1;2\n"),
        "inf_diario_fi_202608.zip": zip_cvm("leia-me.txt", "nada"),
    }
    cvm = ProviderCvm(
        http(servidor_cvm(arquivos, []), relogio), hoje=lambda: date(2026, 10, 29), relogio=relogio
    )
    assert "corrompido" in str(cvm.cotacoes([fundo(1)])[1])
    historico = cvm.historicos([PedidoHistorico(fundo(1), date(2026, 9, 1))], date(2026, 9, 30))
    assert isinstance(historico[1], RespostaInvalidaError)
    assert "mudou de formato" in historico[1].mensagem
    sem_csv = cvm.historicos([PedidoHistorico(fundo(1), date(2026, 8, 1))], date(2026, 8, 31))
    assert "sem CSV" in str(sem_csv[1])


# ---------------------------------------------------------------- registry


def test_registro_padrao_de_providers() -> None:
    registro = criar_registro_providers(
        transporte=httpx2.MockTransport(lambda _: httpx2.Response(500))
    )
    assert registro.nomes_cotacao == ["coingecko", "cvm", "tesouro", "yfinance"]
    assert [p.nome for p in registro.fontes_indicador(TipoIndicador.CAMBIO, "USD")] == [
        "bcb_sgs",
        "yfinance",
    ]
    assert [p.nome for p in registro.fontes_indicador(TipoIndicador.CDI, "BRL")] == ["bcb_sgs"]
    assert registro.fontes_indicador(TipoIndicador.CAMBIO, "EUR")[0].nome == "yfinance"
    assert registro.cotacao("inexistente") is None
    yahoo = registro.cotacao("yfinance")
    assert yahoo is not None
    with pytest.raises(ValueError, match="já registrado"):
        registro.registrar_cotacao(yahoo)
    with pytest.raises(ValueError, match="já registrado"):
        registro.registrar_indicador(registro.fontes_indicador(TipoIndicador.CDI, "BRL")[0])
    registro.fechar()


def test_tipos_de_ativo_cotados_tem_provider_registrado() -> None:
    from app.asset_types.base import HandlerCotado
    from app.asset_types.catalogo import REGISTRO_PADRAO

    registro = criar_registro_providers()
    for handler in REGISTRO_PADRAO.todos():
        if isinstance(handler, HandlerCotado):
            assert handler.provider is not None
            assert registro.cotacao(handler.provider) is not None, handler.slug
    registro.fechar()
