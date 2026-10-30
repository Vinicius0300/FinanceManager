"""CoinGecko (plano público, sem chave): criptomoedas em BRL ou USD.

- **Id da moeda** (decisão do dono): ``simbolo_externo`` se preenchido; senão a tabela
  embutida das principais (BTC → bitcoin); senão a pesquisa da CoinGecko, escolhendo o
  resultado com o mesmo símbolo e **maior valor de mercado** (menor ``market_cap_rank``).
  O id descoberto é gravado em ``simbolo_externo`` (``identificador_persistente``) e
  pode ser corrigido editando o ativo.
- Cotação atual: todas as moedas numa **única** chamada (``/simple/price``).
- Histórico: ``/coins/{id}/market_chart/range`` (plano público: até 365 dias), um
  valor por dia (o último do dia em Brasília).
- Rate limit do plano público: intervalo mínimo entre chamadas (ver ``catalogo.py``).
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from app.domain.tempo import FUSO_LOCAL, data_local
from app.providers.base import (
    AlvoCotacao,
    Cotacao,
    Fechamento,
    PedidoHistorico,
    ProviderError,
    RespostaInvalidaError,
    ResultadoCotacao,
    ResultadoHistorico,
    SimboloNaoEncontradoError,
    SugestaoNome,
    valor_cotacao,
)
from app.providers.http import ClienteHttp

URL_BASE = "https://api.coingecko.com/api/v3"
NOME = "coingecko"
ROTULO = "CoinGecko"
DIAS_MAXIMOS_HISTORICO = 364
TTL_CACHE_S = 60.0
LIMITE_PESQUISA = 10

IDS_CONHECIDOS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "TRX": "tron",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "POL": "polygon-ecosystem-token",
    "LTC": "litecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "XLM": "stellar",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "BCH": "bitcoin-cash",
    "SHIB": "shiba-inu",
    "TON": "the-open-network",
}


def _rank(moeda: dict[str, Any]) -> int:
    rank = moeda.get("market_cap_rank")
    return rank if isinstance(rank, int) else 10**9


class ProviderCoinGecko:
    nome = NOME
    identificador_persistente = True

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def identificar(self, alvo: AlvoCotacao) -> str:
        if alvo.simbolo_externo:
            return alvo.simbolo_externo.strip().lower()
        if not alvo.simbolo:
            raise SimboloNaoEncontradoError(
                f"{alvo.nome}: informe o símbolo (ex.: BTC) ou o id da CoinGecko."
            )
        simbolo = alvo.simbolo.strip().upper()
        if simbolo in IDS_CONHECIDOS:
            return IDS_CONHECIDOS[simbolo]
        dados = self._http.get_json(f"{URL_BASE}/search", {"query": simbolo}, ttl=TTL_CACHE_S)
        moedas = dados.get("coins") if isinstance(dados, dict) else None
        if not isinstance(moedas, list):
            raise RespostaInvalidaError(f"{ROTULO}: resposta inesperada na pesquisa.")
        candidatas = [
            m
            for m in moedas
            if isinstance(m, dict) and str(m.get("symbol", "")).upper() == simbolo and m.get("id")
        ]
        if not candidatas:
            raise SimboloNaoEncontradoError(f"{ROTULO} não encontrou a criptomoeda {simbolo}.")
        return str(min(candidatas, key=_rank)["id"])

    def cotacoes(self, alvos: Sequence[AlvoCotacao]) -> dict[int, ResultadoCotacao]:
        resultados: dict[int, ResultadoCotacao] = {}
        ids: dict[int, str] = {}
        for alvo in alvos:
            try:
                ids[alvo.ativo_id] = self.identificar(alvo)
            except ProviderError as erro:
                resultados[alvo.ativo_id] = erro
        if not ids:
            return resultados
        try:
            dados = self._http.get_json(
                f"{URL_BASE}/simple/price",
                {
                    "ids": ",".join(sorted(set(ids.values()))),
                    "vs_currencies": "brl,usd",
                    "include_last_updated_at": "true",
                },
            )
            if not isinstance(dados, dict):
                raise RespostaInvalidaError(f"{ROTULO}: resposta inesperada nas cotações.")
        except ProviderError as erro:
            return resultados | dict.fromkeys(ids, erro)
        alvos_por_id = {alvo.ativo_id: alvo for alvo in alvos}
        for ativo_id, identificador in ids.items():
            alvo = alvos_por_id[ativo_id]
            try:
                resultados[ativo_id] = self._cotacao(dados.get(identificador), identificador, alvo)
            except ProviderError as erro:
                resultados[ativo_id] = erro
        return resultados

    @staticmethod
    def _cotacao(dados: object, identificador: str, alvo: AlvoCotacao) -> Cotacao:
        if not isinstance(dados, dict):
            raise SimboloNaoEncontradoError(f"{ROTULO} não tem cotação para {identificador}.")
        moeda = alvo.moeda.lower()
        if moeda not in dados:
            raise RespostaInvalidaError(f"{ROTULO} não cota {identificador} em {alvo.moeda}.")
        marca = dados.get("last_updated_at")
        if isinstance(marca, bool) or not isinstance(marca, int):
            raise RespostaInvalidaError(f"{ROTULO}: cotação de {identificador} sem horário.")
        instante = datetime.fromtimestamp(marca, tz=UTC)
        valor = valor_cotacao(dados[moeda], f"{ROTULO} {identificador}")
        return Cotacao(data=data_local(instante), data_hora=instante, valor=valor)

    def historicos(
        self, pedidos: Sequence[PedidoHistorico], fim: date
    ) -> dict[int, ResultadoHistorico]:
        resultados: dict[int, ResultadoHistorico] = {}
        for pedido in pedidos:
            try:
                resultados[pedido.alvo.ativo_id] = self._historico(pedido, fim)
            except ProviderError as erro:
                resultados[pedido.alvo.ativo_id] = erro
        return resultados

    def _historico(self, pedido: PedidoHistorico, fim: date) -> list[Fechamento]:
        identificador = self.identificar(pedido.alvo)
        inicio = max(pedido.inicio, fim - timedelta(days=DIAS_MAXIMOS_HISTORICO))
        dados = self._http.get_json(
            f"{URL_BASE}/coins/{identificador}/market_chart/range",
            {
                "vs_currency": pedido.alvo.moeda.lower(),
                "from": int(datetime.combine(inicio, time(), tzinfo=FUSO_LOCAL).timestamp()),
                "to": int(
                    datetime.combine(fim + timedelta(days=1), time(), tzinfo=FUSO_LOCAL).timestamp()
                ),
            },
            aceitar_404=True,
        )
        if dados is None:
            raise SimboloNaoEncontradoError(f"{ROTULO} não encontrou {identificador}.")
        precos = dados.get("prices") if isinstance(dados, dict) else None
        if not isinstance(precos, list):
            raise RespostaInvalidaError(f"{ROTULO}: histórico inesperado para {identificador}.")
        ultimo_do_dia: dict[date, tuple[float, object]] = {}
        for item in precos:
            if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], int | float):
                continue
            dia = data_local(datetime.fromtimestamp(item[0] / 1000, tz=UTC))
            if inicio <= dia <= fim and (
                dia not in ultimo_do_dia or item[0] >= ultimo_do_dia[dia][0]
            ):
                ultimo_do_dia[dia] = (item[0], item[1])
        return [
            Fechamento(dia, valor_cotacao(valor, f"{ROTULO} {identificador}"))
            for dia, (_, valor) in sorted(ultimo_do_dia.items())
        ]


class BuscaCoinGecko:
    """Pesquisa de criptomoedas por símbolo ou nome (id da CoinGecko como identificador).

    Cliente próprio, de uma tentativa e timeout curto (a pesquisa responde ao usuário
    enquanto ele digita). Resultados por valor de mercado (maior primeiro).
    """

    nome = NOME

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def buscar(self, texto: str) -> list[SugestaoNome]:
        dados = self._http.get_json(f"{URL_BASE}/search", {"query": texto}, ttl=TTL_CACHE_S)
        moedas = dados.get("coins") if isinstance(dados, dict) else None
        if not isinstance(moedas, list):
            raise RespostaInvalidaError(f"{ROTULO}: resposta inesperada na pesquisa.")
        validas = [m for m in moedas if isinstance(m, dict) and m.get("id") and m.get("symbol")]
        return [
            SugestaoNome(
                simbolo=str(m["symbol"]).upper(),
                nome=str(m.get("name") or m["symbol"]),
                simbolo_externo=str(m["id"]),
            )
            for m in sorted(validas, key=_rank)[:LIMITE_PESQUISA]
        ]
