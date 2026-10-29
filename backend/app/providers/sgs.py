"""API SGS do Banco Central (dados abertos): Selic, CDI, IPCA e PTAX.

Séries usadas (conferidas em 29/10/2026; unidades iguais às da tabela ``indicadores``):

======  ====================================  ===========================================
Código  Série                                 Uso / unidade
======  ====================================  ===========================================
4389    CDI anualizado base 252               ``cdi``: % a.a., 2 casas (taxa oficial da
                                              B3, usada no accrual de CDB/LCI/LCA)
432     Meta Selic definida pelo Copom        ``selic``: % a.a. (regra da poupança). A
                                              série traz datas futuras até a próxima
                                              reunião: só valores com data ≤ ``fim``
433     IPCA, variação mensal                 ``ipca``: % no mês, data = dia 1º do mês
1       Dólar comercial (venda), PTAX         ``cambio`` USD: BRL por 1 USD
======  ====================================  ===========================================

A API recusa (HTTP 406) consultas com mais de 10 anos: as datas são paginadas em janelas
de :data:`JANELA_DIAS`. Período sem dados responde 404, tratado como lista vazia.
"""

from datetime import date, datetime, timedelta

from app.domain.enums import TipoIndicador
from app.domain.indicadores import PontoIndicador
from app.domain.moedas import MOEDA_BASE
from app.providers.base import ProviderError, RespostaInvalidaError, valor_cambio, valor_taxa
from app.providers.http import ClienteHttp

URL_SERIE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
NOME = "bcb_sgs"
ROTULO = "Banco Central (SGS)"
JANELA_DIAS = 5 * 365
TTL_CACHE_S = 300.0

SERIES: dict[tuple[TipoIndicador, str], int] = {
    (TipoIndicador.CDI, MOEDA_BASE): 4389,
    (TipoIndicador.SELIC, MOEDA_BASE): 432,
    (TipoIndicador.IPCA, MOEDA_BASE): 433,
    (TipoIndicador.CAMBIO, "USD"): 1,
}


def _data_br(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


class ProviderSgs:
    nome = NOME

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def suporta(self, tipo: TipoIndicador, moeda: str) -> bool:
        return (tipo, moeda) in SERIES

    def serie(
        self, tipo: TipoIndicador, moeda: str, inicio: date, fim: date
    ) -> list[PontoIndicador]:
        codigo = SERIES.get((tipo, moeda))
        if codigo is None:
            raise ProviderError(f"{ROTULO} não fornece {tipo.value} em {moeda}.")
        pontos: dict[date, PontoIndicador] = {}
        janela_inicio = inicio
        while janela_inicio <= fim:
            janela_fim = min(janela_inicio + timedelta(days=JANELA_DIAS), fim)
            for ponto in self._consultar(codigo, tipo, janela_inicio, janela_fim):
                if inicio <= ponto.data <= fim:
                    pontos[ponto.data] = ponto
            janela_inicio = janela_fim + timedelta(days=1)
        return [pontos[d] for d in sorted(pontos)]

    def _consultar(
        self, codigo: int, tipo: TipoIndicador, inicio: date, fim: date
    ) -> list[PontoIndicador]:
        dados = self._http.get_json(
            URL_SERIE.format(codigo=codigo),
            {"formato": "json", "dataInicial": _data_br(inicio), "dataFinal": _data_br(fim)},
            ttl=TTL_CACHE_S,
            aceitar_404=True,
        )
        if dados is None:
            return []
        if not isinstance(dados, list):
            raise RespostaInvalidaError(f"{ROTULO}: resposta inesperada para a série {codigo}.")
        return [p for p in (self._ponto(item, codigo, tipo) for item in dados) if p is not None]

    @staticmethod
    def _ponto(item: object, codigo: int, tipo: TipoIndicador) -> PontoIndicador | None:
        if not isinstance(item, dict):
            raise RespostaInvalidaError(f"{ROTULO}: item inesperado na série {codigo}.")
        bruto = str(item.get("valor", "")).strip()
        if not bruto:  # o SGS às vezes publica a data antes do valor
            return None
        try:
            dia = datetime.strptime(str(item.get("data")), "%d/%m/%Y").date()
        except ValueError as erro:
            raise RespostaInvalidaError(f"{ROTULO}: data inválida na série {codigo}.") from erro
        rotulo = f"{ROTULO} série {codigo}"
        valor = (
            valor_cambio(bruto, rotulo)
            if tipo is TipoIndicador.CAMBIO
            else valor_taxa(bruto, rotulo)
        )
        return PontoIndicador(dia, valor)
