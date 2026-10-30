"""Yahoo Finance por chamada direta ao endpoint de gráfico (slug ``yfinance``).

Decisão do dono (Parte 3): sem a biblioteca ``yfinance`` (dependências pesadas e
quebra frequente); o slug continua ``yfinance`` para não migrar os ativos cadastrados.

- Ações BR: o símbolo ganha o sufixo ``.SA`` (PETR4 → PETR4.SA). Ações US: o próprio
  ticker. ``simbolo_externo`` preenchido prevalece.
- Cotação atual: ``meta.regularMarketPrice`` e ``meta.regularMarketTime``.
- Histórico: candles diários (``close``); a data é a do pregão no fuso da bolsa.
  O Yahoo devolve o ``close`` **ajustado por desdobramentos**; o ajuste é desfeito com os
  eventos de split da própria resposta (``events=split``), porque as posições já aplicam os
  eventos corporativos na data "ex". Ex.: desdobramento 1:2 em 10/03 e close ajustado de
  20,00 em 09/03 → preço real de 09/03 = 20,00 × 2 = 40,00.
- Casas: o ``priceHint`` da fonte (2 para ações, 4 para câmbio) evita levar para o banco
  o ruído de float da resposta (58.68000030517578 → 58.68).
- Câmbio (reserva da PTAX e dólar ao longo do dia): par ``USDBRL=X``.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.enums import TipoIndicador
from app.domain.indicadores import PontoIndicador
from app.domain.moedas import MOEDA_BASE
from app.domain.numeros import CASAS_PRECO, dec
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
    valor_cambio,
    valor_cotacao,
)
from app.providers.http import ClienteHttp

URL_GRAFICO = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}"
NOME = "yfinance"
ROTULO = "Yahoo Finance"
CASAS_PADRAO = 4
SUFIXO_B3 = ".SA"
TTL_CACHE_S = 60.0


def _instante(epoch: object) -> datetime:
    if isinstance(epoch, bool) or not isinstance(epoch, int | float):
        raise RespostaInvalidaError(f"{ROTULO}: horário da cotação ausente.")
    return datetime.fromtimestamp(epoch, tz=UTC)


def _fuso(meta: dict[str, Any]) -> ZoneInfo:
    try:
        return ZoneInfo(str(meta.get("exchangeTimezoneName") or ""))
    except (ZoneInfoNotFoundError, ValueError):
        return FUSO_LOCAL


def _casas(meta: dict[str, Any]) -> int:
    dica = meta.get("priceHint")
    return dica if isinstance(dica, int) and 0 <= dica <= CASAS_PRECO else CASAS_PADRAO


def _desdobramentos(resultado: dict[str, Any], fuso: ZoneInfo) -> list[tuple[date, Decimal]]:
    """(data do split, fator pelo qual o preço anterior foi dividido) de cada desdobramento."""
    eventos = resultado.get("events")
    splits = eventos.get("splits") if isinstance(eventos, dict) else None
    if not isinstance(splits, dict):
        return []
    fatores: list[tuple[date, Decimal]] = []
    for split in splits.values():
        if not isinstance(split, dict):
            continue
        numerador, denominador = split.get("numerator"), split.get("denominator")
        if not all(isinstance(v, int | float) and v > 0 for v in (numerador, denominador)):
            continue
        dia = _instante(split.get("date")).astimezone(fuso).date()
        fatores.append((dia, dec(str(numerador)) / dec(str(denominador))))
    return fatores


def _sem_ajuste(
    valor: object, dia: date, desdobramentos: list[tuple[date, Decimal]], rotulo: str, casas: int
) -> Decimal:
    """Desfaz o ajuste do Yahoo: multiplica pelos fatores dos splits posteriores ao dia."""
    preco = valor_cotacao(valor, rotulo, casas)  # tira o ruído de float na precisão da fonte
    for data_split, fator in desdobramentos:
        if dia < data_split:
            preco *= fator
    return valor_cotacao(preco, rotulo)  # até 8 casas: 2,05 × 0,1 = 0,205 não perde a casa


class ProviderYahoo:
    nome = NOME
    identificador_persistente = False

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    # ------------------------------------------------------------ cotações

    def identificar(self, alvo: AlvoCotacao) -> str:
        if alvo.simbolo_externo:
            return alvo.simbolo_externo.strip()
        if not alvo.simbolo:
            raise SimboloNaoEncontradoError(
                f"{alvo.nome}: informe o símbolo (ticker) para buscar a cotação."
            )
        simbolo = alvo.simbolo.strip().upper()
        if alvo.tipo == "acao_br" and "." not in simbolo:
            return simbolo + SUFIXO_B3
        return simbolo

    def _grafico(self, simbolo: str, params: dict[str, str | int]) -> dict[str, Any]:
        dados = self._http.get_json(
            URL_GRAFICO.format(simbolo=simbolo), params, ttl=TTL_CACHE_S, aceitar_404=True
        )
        grafico = dados.get("chart") if isinstance(dados, dict) else None
        resultados = grafico.get("result") if isinstance(grafico, dict) else None
        if not resultados:
            raise SimboloNaoEncontradoError(f"{ROTULO} não encontrou o símbolo {simbolo}.")
        resultado = resultados[0]
        if not isinstance(resultado, dict) or not isinstance(resultado.get("meta"), dict):
            raise RespostaInvalidaError(f"{ROTULO}: resposta sem dados para {simbolo}.")
        return resultado

    def _cotacao(self, alvo: AlvoCotacao) -> Cotacao:
        simbolo = self.identificar(alvo)
        meta = self._grafico(simbolo, {"range": "5d", "interval": "1d"})["meta"]
        moeda = str(meta.get("currency") or "").upper()
        if moeda and moeda != alvo.moeda:
            raise RespostaInvalidaError(
                f"{ROTULO} cota {simbolo} em {moeda}, mas o ativo está em {alvo.moeda}."
            )
        instante = _instante(meta.get("regularMarketTime"))
        valor = valor_cotacao(meta.get("regularMarketPrice"), f"{ROTULO} {simbolo}", _casas(meta))
        return Cotacao(data=data_local(instante), data_hora=instante, valor=valor)

    def cotacoes(self, alvos: Sequence[AlvoCotacao]) -> dict[int, ResultadoCotacao]:
        resultados: dict[int, ResultadoCotacao] = {}
        for alvo in alvos:
            try:
                resultados[alvo.ativo_id] = self._cotacao(alvo)
            except ProviderError as erro:
                resultados[alvo.ativo_id] = erro
        return resultados

    # ------------------------------------------------------------ histórico

    def _candles(self, simbolo: str, inicio: date, fim: date) -> list[Fechamento]:
        params: dict[str, str | int] = {
            "period1": int(datetime.combine(inicio, time(), tzinfo=UTC).timestamp()),
            "period2": int(
                datetime.combine(fim + timedelta(days=1), time(), tzinfo=UTC).timestamp()
            ),
            "interval": "1d",
            "events": "split",
        }
        resultado = self._grafico(simbolo, params)
        meta = resultado["meta"]
        fuso, casas = _fuso(meta), _casas(meta)
        desdobramentos = _desdobramentos(resultado, fuso)
        marcas = resultado.get("timestamp") or []
        quotes = (resultado.get("indicators") or {}).get("quote") or [{}]
        fechamentos = quotes[0].get("close") or []
        por_dia: dict[date, object] = {}
        for marca, valor in zip(marcas, fechamentos, strict=False):
            if valor is None:  # dia sem negócio
                continue
            dia = _instante(marca).astimezone(fuso).date()
            if inicio <= dia <= fim:
                por_dia[dia] = valor
        rotulo = f"{ROTULO} {simbolo}"
        return [
            Fechamento(dia, _sem_ajuste(valor, dia, desdobramentos, rotulo, casas))
            for dia, valor in sorted(por_dia.items())
        ]

    def historicos(
        self, pedidos: Sequence[PedidoHistorico], fim: date
    ) -> dict[int, ResultadoHistorico]:
        resultados: dict[int, ResultadoHistorico] = {}
        for pedido in pedidos:
            try:
                simbolo = self.identificar(pedido.alvo)
                resultados[pedido.alvo.ativo_id] = self._candles(simbolo, pedido.inicio, fim)
            except ProviderError as erro:
                resultados[pedido.alvo.ativo_id] = erro
        return resultados

    # ------------------------------------------------------------ câmbio

    def suporta(self, tipo: TipoIndicador, moeda: str) -> bool:
        return tipo is TipoIndicador.CAMBIO and moeda != MOEDA_BASE

    def serie(
        self, tipo: TipoIndicador, moeda: str, inicio: date, fim: date
    ) -> list[PontoIndicador]:
        if not self.suporta(tipo, moeda):
            raise ProviderError(f"{ROTULO} não fornece {tipo.value} em {moeda}.")
        simbolo = f"{moeda}{MOEDA_BASE}=X"
        fechamentos = self._candles(simbolo, inicio, fim)
        return [
            PontoIndicador(f.data, valor_cambio(f.valor, f"{ROTULO} {simbolo}"))
            for f in fechamentos
        ]


# ------------------------------------------------------------ pesquisa por texto

URL_PESQUISA = "https://query1.finance.yahoo.com/v1/finance/search"
LIMITE_PESQUISA = 10


class BuscaYahoo:
    """Pesquisa de papéis por texto (sugere o nome no cadastro; nunca decide o tipo).

    Usa um cliente próprio, de uma tentativa e timeout curto: a pesquisa responde ao
    usuário enquanto ele digita e não deve esperar a fila da coleta.
    """

    nome = NOME

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def buscar(self, texto: str) -> list[SugestaoNome]:
        params: dict[str, str | int] = {
            "q": texto,
            "quotesCount": LIMITE_PESQUISA,
            "newsCount": 0,
            "listsCount": 0,
        }
        dados = self._http.get_json(URL_PESQUISA, params, ttl=TTL_CACHE_S)
        cotacoes = dados.get("quotes") if isinstance(dados, dict) else None
        if not isinstance(cotacoes, list):
            raise RespostaInvalidaError(f"{ROTULO}: resposta inesperada na pesquisa.")
        sugestoes: list[SugestaoNome] = []
        for item in cotacoes:
            if not isinstance(item, dict):
                continue
            simbolo = str(item.get("symbol") or "").strip().upper()
            nome = str(item.get("longname") or item.get("shortname") or "").strip()
            if not simbolo:
                continue
            sugestoes.append(
                SugestaoNome(
                    simbolo=simbolo,
                    nome=nome or simbolo,
                    simbolo_externo=simbolo,
                    bolsa=str(item.get("exchange") or "") or None,
                )
            )
        return sugestoes
