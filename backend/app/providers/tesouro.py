"""Tesouro Transparente (dados abertos): PU de venda dos títulos do Tesouro Direto.

Arquivo único com o histórico de todos os títulos (``PrecoTaxaTesouroDireto.csv``,
separador ``;``, decimais com vírgula, datas dd/mm/aaaa), baixado uma vez por ciclo
(cache) e filtrado pelo título e vencimento de cada ativo. Colunas:
``Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;
PU Compra Manha;PU Venda Manha;PU Base Manha``.

Usa o **PU Venda Manhã** (valor de resgate antecipado do título naquele dia). A cotação
"atual" é a da Data Base mais recente (o arquivo é publicado no fim do dia útil).
"""

import csv
import io
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime

from app.domain.precos import instante_fechamento
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
    valor_cotacao,
)
from app.providers.http import ClienteHttp

URL_CSV = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/"
    "download/PrecoTaxaTesouroDireto.csv"
)
NOME = "tesouro"
ROTULO = "Tesouro Transparente"
TTL_CACHE_S = 1800.0
TIMEOUT_S = 120.0

NOMES_NA_FONTE = {
    "selic": "Tesouro Selic",
    "prefixado": "Tesouro Prefixado",
    "prefixado_juros": "Tesouro Prefixado com Juros Semestrais",
    "ipca": "Tesouro IPCA+",
    "ipca_juros": "Tesouro IPCA+ com Juros Semestrais",
    "renda_mais": "Tesouro Renda+ Aposentadoria Extra",
    "educa_mais": "Tesouro Educa+",
}
COLUNA_TITULO = "Tipo Titulo"
COLUNA_VENCIMENTO = "Data Vencimento"
COLUNA_DATA = "Data Base"
COLUNA_PU = "PU Venda Manha"

Chave = tuple[str, date]


def _data(texto: str) -> date:
    return datetime.strptime(texto.strip(), "%d/%m/%Y").date()


class ProviderTesouro:
    nome = NOME
    identificador_persistente = False

    def __init__(self, http: ClienteHttp) -> None:
        self._http = http

    def _chave(self, alvo: AlvoCotacao) -> Chave:
        titulo = NOMES_NA_FONTE.get(str(alvo.metadados.get("titulo", "")))
        vencimento = alvo.metadados.get("vencimento")
        if titulo is None or not isinstance(vencimento, str):
            raise SimboloNaoEncontradoError(f"{alvo.nome}: título ou vencimento não informado.")
        return titulo.casefold(), date.fromisoformat(vencimento)

    def identificar(self, alvo: AlvoCotacao) -> str:
        titulo, vencimento = self._chave(alvo)
        return f"{titulo} {vencimento.isoformat()}"

    def _precos(self, chaves: set[Chave]) -> dict[Chave, list[Fechamento]]:
        texto = self._http.get_texto(
            URL_CSV, ttl=TTL_CACHE_S, codificacao="latin-1", timeout=TIMEOUT_S
        )
        if not texto:
            raise RespostaInvalidaError(f"{ROTULO}: arquivo de preços vazio.")
        leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
        colunas = set(leitor.fieldnames or ())
        if not {COLUNA_TITULO, COLUNA_VENCIMENTO, COLUNA_DATA, COLUNA_PU} <= colunas:
            raise RespostaInvalidaError(f"{ROTULO}: o arquivo mudou de formato (colunas).")
        por_chave: dict[Chave, dict[date, str]] = defaultdict(dict)
        for linha in leitor:
            try:
                chave = (linha[COLUNA_TITULO].strip().casefold(), _data(linha[COLUNA_VENCIMENTO]))
                if chave in chaves and linha[COLUNA_PU].strip():
                    por_chave[chave][_data(linha[COLUNA_DATA])] = linha[COLUNA_PU]
            except (ValueError, AttributeError):
                continue  # linha malformada não derruba as demais
        return {
            chave: [
                Fechamento(
                    dia, valor_cotacao(pu.strip().replace(".", "").replace(",", "."), ROTULO)
                )
                for dia, pu in sorted(dias.items())
            ]
            for chave, dias in por_chave.items()
        }

    def _por_alvo(
        self, alvos: Sequence[AlvoCotacao]
    ) -> tuple[dict[int, Chave], dict[int, ProviderError], dict[Chave, list[Fechamento]]]:
        chaves: dict[int, Chave] = {}
        erros: dict[int, ProviderError] = {}
        for alvo in alvos:
            try:
                chaves[alvo.ativo_id] = self._chave(alvo)
            except ProviderError as erro:
                erros[alvo.ativo_id] = erro
        precos = self._precos(set(chaves.values())) if chaves else {}
        return chaves, erros, precos

    @staticmethod
    def _nao_encontrado(alvo: AlvoCotacao) -> SimboloNaoEncontradoError:
        return SimboloNaoEncontradoError(
            f"{ROTULO} não tem preços para {alvo.nome} (confira título e vencimento)."
        )

    def cotacoes(self, alvos: Sequence[AlvoCotacao]) -> dict[int, ResultadoCotacao]:
        try:
            chaves, erros, precos = self._por_alvo(alvos)
        except ProviderError as erro:
            return dict.fromkeys((a.ativo_id for a in alvos), erro)
        resultados: dict[int, ResultadoCotacao] = dict(erros)
        for alvo in alvos:
            if alvo.ativo_id not in chaves:
                continue
            serie = precos.get(chaves[alvo.ativo_id])
            if not serie:
                resultados[alvo.ativo_id] = self._nao_encontrado(alvo)
                continue
            ultimo = serie[-1]
            resultados[alvo.ativo_id] = Cotacao(
                data=ultimo.data, data_hora=instante_fechamento(ultimo.data), valor=ultimo.valor
            )
        return resultados

    def historicos(
        self, pedidos: Sequence[PedidoHistorico], fim: date
    ) -> dict[int, ResultadoHistorico]:
        alvos = [p.alvo for p in pedidos]
        try:
            chaves, erros, precos = self._por_alvo(alvos)
        except ProviderError as erro:
            return dict.fromkeys((a.ativo_id for a in alvos), erro)
        resultados: dict[int, ResultadoHistorico] = dict(erros)
        for pedido in pedidos:
            ativo_id = pedido.alvo.ativo_id
            if ativo_id not in chaves:
                continue
            serie = precos.get(chaves[ativo_id])
            if serie is None:
                resultados[ativo_id] = self._nao_encontrado(pedido.alvo)
                continue
            resultados[ativo_id] = [f for f in serie if pedido.inicio <= f.data <= fim]
        return resultados
