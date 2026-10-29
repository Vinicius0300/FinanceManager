"""CVM dados abertos: valor da cota de fundos pelo informe diário (ZIP mensal).

A CVM publica um ZIP por mês com todos os fundos (~12 MB): ``inf_diario_fi_AAAAMM.zip``.
O arquivo é baixado para um temporário e lido em streaming (nada fica em disco além dos
preços gravados no banco). O mês corrente pode ainda não existir (404) nos primeiros
dias: nesse caso vale o mês anterior.

Formatos do CSV (separador ``;``, latin-1):
- **antigo:** ``TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;...``
- **Resolução CVM 175:** ``TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;
  VL_TOTAL;VL_QUOTA;...``. Uma classe pode ter subclasses (várias cotas no mesmo dia):
  sem ``simbolo_externo`` vale a linha sem subclasse; com ``simbolo_externo`` preenchido,
  ele é o ``ID_SUBCLASSE`` da cota do usuário.

``VL_QUOTA`` vem com até 12 casas e é arredondado a 8.
"""

import csv
import io
import re
import tempfile
import time
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from datetime import date

from app.domain.precos import instante_fechamento
from app.domain.tempo import hoje_local
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

URL_MES = (
    "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ano:04d}{mes:02d}.zip"
)
NOME = "cvm"
ROTULO = "CVM"
_SO_DIGITOS = re.compile(r"\D")
COLUNAS_CNPJ = ("CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO")
SEM_SUBCLASSE = ""
TTL_CACHE_S = 1800.0

Chave = tuple[str, str]  # (CNPJ só com dígitos, id da subclasse ou "")
CotasDoMes = dict[Chave, dict[date, str]]


def _meses(inicio: date, fim: date) -> list[tuple[int, int]]:
    meses = []
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        meses.append((ano, mes))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


def _mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


class ProviderCvm:
    nome = NOME
    identificador_persistente = False

    def __init__(
        self,
        http: ClienteHttp,
        *,
        hoje: Callable[[], date] = hoje_local,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._hoje = hoje
        self._relogio = relogio
        # (ano, mês) → (expira em, chaves lidas, cotas): reaproveita o ZIP no mesmo ciclo.
        self._cache: dict[tuple[int, int], tuple[float, frozenset[Chave], CotasDoMes]] = {}

    def limpar_cache(self) -> None:
        self._cache.clear()

    def _chave(self, alvo: AlvoCotacao) -> Chave:
        cnpj = _SO_DIGITOS.sub("", str(alvo.metadados.get("cnpj", "")))
        if len(cnpj) != 14:
            raise SimboloNaoEncontradoError(f"{alvo.nome}: CNPJ do fundo não informado.")
        return cnpj, (alvo.simbolo_externo or SEM_SUBCLASSE).strip()

    def identificar(self, alvo: AlvoCotacao) -> str:
        cnpj, subclasse = self._chave(alvo)
        return f"{cnpj}/{subclasse}" if subclasse else cnpj

    # ------------------------------------------------------------ leitura do ZIP

    def _linhas(self, ano: int, mes: int) -> Iterator[dict[str, str]] | None:
        temporario = tempfile.TemporaryFile()  # noqa: SIM115 - fechado no finally do gerador
        try:
            if not self._http.baixar_arquivo(
                URL_MES.format(ano=ano, mes=mes), temporario, aceitar_404=True
            ):
                temporario.close()
                return None
        except BaseException:
            temporario.close()
            raise

        def gerar() -> Iterator[dict[str, str]]:
            try:
                with zipfile.ZipFile(temporario) as arquivo_zip:
                    nomes = [n for n in arquivo_zip.namelist() if n.lower().endswith(".csv")]
                    if not nomes:
                        raise RespostaInvalidaError(f"{ROTULO}: ZIP de {mes:02d}/{ano} sem CSV.")
                    with arquivo_zip.open(nomes[0]) as bruto:
                        texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
                        yield from csv.DictReader(texto, delimiter=";")
            except zipfile.BadZipFile as erro:
                raise RespostaInvalidaError(
                    f"{ROTULO}: arquivo de {mes:02d}/{ano} corrompido."
                ) from erro
            finally:
                temporario.close()

        return gerar()

    def _mes(self, ano: int, mes: int, chaves: frozenset[Chave]) -> CotasDoMes | None:
        """Cotas do mês para as chaves pedidas (``None`` se o mês não foi publicado)."""
        guardado = self._cache.get((ano, mes))
        if guardado is not None and guardado[0] > self._relogio() and chaves <= guardado[1]:
            return guardado[2]
        linhas = self._linhas(ano, mes)
        if linhas is None:
            return None
        cnpjs = {cnpj for cnpj, _ in chaves}
        cotas: dict[Chave, dict[date, str]] = defaultdict(dict)
        coluna_cnpj: str | None = None
        for linha in linhas:
            if coluna_cnpj is None:
                coluna_cnpj = next((c for c in COLUNAS_CNPJ if c in linha), None)
                if coluna_cnpj is None or "VL_QUOTA" not in linha or "DT_COMPTC" not in linha:
                    raise RespostaInvalidaError(f"{ROTULO}: o informe diário mudou de formato.")
            cnpj = _SO_DIGITOS.sub("", linha.get(coluna_cnpj) or "")
            if cnpj not in cnpjs:
                continue
            chave = (cnpj, (linha.get("ID_SUBCLASSE") or SEM_SUBCLASSE).strip())
            if chave not in chaves or not (linha.get("VL_QUOTA") or "").strip():
                continue
            try:
                cotas[chave][date.fromisoformat(linha["DT_COMPTC"].strip())] = linha["VL_QUOTA"]
            except ValueError:
                continue
        resultado = dict(cotas)
        self._cache[(ano, mes)] = (self._relogio() + TTL_CACHE_S, chaves, resultado)
        return resultado

    # ------------------------------------------------------------ interface

    def _chaves(
        self, alvos: Sequence[AlvoCotacao]
    ) -> tuple[dict[int, Chave], dict[int, ProviderError]]:
        chaves: dict[int, Chave] = {}
        erros: dict[int, ProviderError] = {}
        for alvo in alvos:
            try:
                chaves[alvo.ativo_id] = self._chave(alvo)
            except ProviderError as erro:
                erros[alvo.ativo_id] = erro
        return chaves, erros

    @staticmethod
    def _nao_encontrado(alvo: AlvoCotacao) -> SimboloNaoEncontradoError:
        return SimboloNaoEncontradoError(
            f"{ROTULO} não tem cotas recentes de {alvo.nome} (confira o CNPJ; fundo com "
            "subclasses precisa do id da subclasse no símbolo externo)."
        )

    def cotacoes(self, alvos: Sequence[AlvoCotacao]) -> dict[int, ResultadoCotacao]:
        """Última cota publicada de cada fundo (mês corrente; se vazio, o anterior)."""
        chaves, erros = self._chaves(alvos)
        resultados: dict[int, ResultadoCotacao] = dict(erros)
        if not chaves:
            return resultados
        referencia = self._hoje()
        conjunto = frozenset(chaves.values())
        ultimos: dict[Chave, tuple[date, str]] = {}
        try:
            ano, mes = referencia.year, referencia.month
            for _ in range(2):  # mês corrente e, se preciso, o anterior
                dados = self._mes(ano, mes, conjunto) or {}
                for chave, dias in dados.items():
                    if chave not in ultimos and dias:
                        dia = max(dias)
                        ultimos[chave] = (dia, dias[dia])
                if conjunto <= set(ultimos):
                    break
                ano, mes = _mes_anterior(ano, mes)
        except ProviderError as erro:
            return resultados | dict.fromkeys(chaves, erro)
        alvos_por_id = {a.ativo_id: a for a in alvos}
        for ativo_id, chave in chaves.items():
            if chave not in ultimos:
                resultados[ativo_id] = self._nao_encontrado(alvos_por_id[ativo_id])
                continue
            dia, bruto = ultimos[chave]
            try:
                resultados[ativo_id] = Cotacao(
                    data=dia,
                    data_hora=instante_fechamento(dia),
                    valor=valor_cotacao(bruto, f"{ROTULO} {chave[0]}"),
                )
            except ProviderError as erro:
                resultados[ativo_id] = erro
        return resultados

    def historicos(
        self, pedidos: Sequence[PedidoHistorico], fim: date
    ) -> dict[int, ResultadoHistorico]:
        chaves, erros = self._chaves([p.alvo for p in pedidos])
        resultados: dict[int, ResultadoHistorico] = dict(erros)
        validos = [p for p in pedidos if p.alvo.ativo_id in chaves]
        if not validos:
            return resultados
        inicio = min(p.inicio for p in validos)
        conjunto = frozenset(chaves.values())
        acumulado: dict[Chave, dict[date, str]] = defaultdict(dict)
        try:
            for ano, mes in _meses(inicio, fim):
                for chave, dias in (self._mes(ano, mes, conjunto) or {}).items():
                    acumulado[chave].update(dias)
        except ProviderError as erro:
            return resultados | {p.alvo.ativo_id: erro for p in validos}
        for pedido in validos:
            ativo_id = pedido.alvo.ativo_id
            dias = acumulado.get(chaves[ativo_id], {})
            try:
                resultados[ativo_id] = [
                    Fechamento(dia, valor_cotacao(bruto, f"{ROTULO} {chaves[ativo_id][0]}"))
                    for dia, bruto in sorted(dias.items())
                    if pedido.inicio <= dia <= fim
                ]
            except ProviderError as erro:
                resultados[ativo_id] = erro
        return resultados
