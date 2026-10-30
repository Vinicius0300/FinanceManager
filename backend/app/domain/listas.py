"""Classificação oficial dos papéis de bolsa (regras puras, sem rede nem banco).

O tipo de um ticker vem do **cadastro oficial** da bolsa, nunca de regra sobre o texto do
ticker (o final 11 é unit, FII ou ETF; nos EUA o ticker não diz nada). Validado no arquivo
``InstrumentsConsolidatedFile`` da B3 de 30/10/2026 (ver ``docs/CONTEXTO.md`` §8.4).

**B3** (colunas ``SgmtNm``, ``MktNm``, ``SctyCtgyNm``, ``SpcfctnCd``, ``Asst``, ``CrpnNm``):

- mercado à vista (``CASH`` + ``EQUITY-CASH``):
  ``SHARES`` com especificação ON → ação ON; PN, PNA... PRA, PRB, PNV → ação PN;
  ``UNIT`` → ação (unit); ``BDR`` → ação (BDR); ``ETF EQUITIES``/``ETF FOREIGN INDEX`` → ETF;
  ``FUNDS`` → fundo listado (FII, Fiagro, FI-Infra...); recibos, direitos, warrants,
  índices e ``SHARES`` com especificação ``DIA`` (taxas de financiamento do termo) ficam fora;
- ETF de renda fixa: ``FORWARD`` + ``FIXED INCOME TRADABLE INSTRUMENT T1`` **e** o mesmo
  ``Asst`` com uma linha ``ETF PRIMARY MARKET`` (as duas condições juntas);
- qualquer outra categoria do mercado à vista é **não mapeada**: fica fora da lista e é
  informada para o log (nunca vira "ação" por exclusão).

**EUA** (diretório de símbolos da NASDAQ, ``nasdaqlisted.txt`` e ``otherlisted.txt``):
``ETF = Y`` → ETF; ``N`` → ação. ``Test Issue = Y`` e símbolos com sufixo especial
(preferenciais ``$``, warrants, direitos, units...) ficam fora. ``BRK.B`` vira ``BRK-B``
(formato do Yahoo).
"""

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

BOLSA_B3 = "B3"
BOLSA_EUA = "EUA"

TIPO_ACAO_BR = "acao_br"
TIPO_FUNDO_LISTADO = "fundo_listado"
TIPO_ETF_BR = "etf_br"
TIPO_ACAO_US = "acao_us"
TIPO_ETF_US = "etf_us"

SUFIXO_YAHOO_B3 = ".SA"

ESPECIFICACOES_ON = frozenset({"ON"})
ESPECIFICACOES_PN = frozenset({"PN", "PNA", "PNB", "PNC", "PND", "PRA", "PRB", "PNV"})

CATEGORIAS_IGNORADAS_B3 = frozenset({"RECEIPTS", "RIGHTS", "WARRANT", "WARRANTS", "INDEX"})
CATEGORIA_ETF_RENDA_FIXA = "FIXED INCOME TRADABLE INSTRUMENT T1"

COLUNAS_B3 = ("TckrSymb", "Asst", "SgmtNm", "MktNm", "SctyCtgyNm", "SpcfctnCd", "CrpnNm")

BOLSAS_OTHERLISTED = {"N": "NYSE", "A": "AMEX"}  # demais (P, Z, V...) → "OUTRA"
RODAPE_NASDAQ = "File Creation Time"


class FormatoListaError(ValueError):
    """Arquivo da bolsa num formato inesperado (mensagem em pt-BR)."""


@dataclass(frozen=True)
class ItemListado:
    """Um papel da lista oficial, já com o tipo de ativo do app."""

    bolsa: str
    simbolo: str
    nome: str
    tipo: str
    categoria: str  # categoria original da fonte (para conferência)
    simbolo_yahoo: str
    tipo_papel: str | None = None  # B3: ON, PN, UNIT, BDR
    bolsa_eua: str | None = None  # EUA: NYSE, NASDAQ, AMEX, OUTRA

    @property
    def campos_sugeridos(self) -> dict[str, str]:
        """Campos específicos que o cadastro já pode preencher (o tipo filtra os seus)."""
        sugeridos: dict[str, str] = {}
        if self.tipo_papel:
            sugeridos["tipo_papel"] = self.tipo_papel
        if self.bolsa_eua:
            sugeridos["bolsa"] = self.bolsa_eua
        return sugeridos


@dataclass
class ResultadoClassificacao:
    itens: list[ItemListado] = field(default_factory=list)
    nao_mapeados: list[tuple[str, str]] = field(default_factory=list)  # (ticker, categoria)
    ignorados: int = 0


# ------------------------------------------------------------------ B3


def _especificacao(bruta: str) -> str:
    """Primeira palavra, sem asterisco: "PN      N2" → "PN"; "PNA*" → "PNA"."""
    partes = bruta.split()
    return partes[0].rstrip("*") if partes else ""


def _classificar_a_vista(linha: Mapping[str, str]) -> tuple[str, str | None] | None:
    """(tipo, tipo de papel) de um papel do mercado à vista; ``None`` = fora da lista.

    Levanta ``KeyError`` (com a categoria) para categoria não mapeada.
    """
    categoria = linha["SctyCtgyNm"].strip()
    especificacao = _especificacao(linha["SpcfctnCd"])
    if categoria == "SHARES":
        if especificacao in ESPECIFICACOES_ON:
            return TIPO_ACAO_BR, "ON"
        if especificacao in ESPECIFICACOES_PN:
            return TIPO_ACAO_BR, "PN"
        if especificacao in {"DIA", "REC"}:
            return None  # taxa de financiamento do termo e recibos: não são ações
        raise KeyError(f"SHARES/{especificacao or 'sem especificação'}")
    if categoria == "UNIT":
        return TIPO_ACAO_BR, "UNIT"
    if categoria == "BDR":
        return TIPO_ACAO_BR, "BDR"
    if categoria in {"ETF EQUITIES", "ETF FOREIGN INDEX"}:
        return TIPO_ETF_BR, None
    if categoria == "FUNDS":
        return TIPO_FUNDO_LISTADO, None
    if categoria in CATEGORIAS_IGNORADAS_B3:
        return None
    raise KeyError(categoria)


def _item_b3(linha: Mapping[str, str], tipo: str, tipo_papel: str | None) -> ItemListado:
    simbolo = linha["TckrSymb"].strip().upper()
    return ItemListado(
        bolsa=BOLSA_B3,
        simbolo=simbolo,
        nome=linha["CrpnNm"].strip() or simbolo,
        tipo=tipo,
        categoria=linha["SctyCtgyNm"].strip(),
        simbolo_yahoo=simbolo + SUFIXO_YAHOO_B3,
        tipo_papel=tipo_papel,
    )


def classificar_b3(linhas: Iterable[Mapping[str, str]]) -> ResultadoClassificacao:
    """Classifica as linhas do cadastro de instrumentos da B3 numa só passada."""
    resultado = ResultadoClassificacao()
    vistos: set[str] = set()
    etf_primario: set[str] = set()
    candidatos_renda_fixa: list[Mapping[str, str]] = []
    conferidas = False
    for linha in linhas:
        if not conferidas:
            faltando = [c for c in COLUNAS_B3 if c not in linha]
            if faltando:
                raise FormatoListaError(
                    "Arquivo da B3 sem as colunas esperadas: " + ", ".join(faltando) + "."
                )
            conferidas = True
        segmento = linha["SgmtNm"].strip()
        if segmento == "ETF PRIMARY MARKET":
            etf_primario.add(linha["Asst"].strip())
            continue
        if segmento == "FORWARD" and linha["SctyCtgyNm"].strip() == CATEGORIA_ETF_RENDA_FIXA:
            candidatos_renda_fixa.append(linha)
            continue
        if segmento != "CASH" or linha["MktNm"].strip() != "EQUITY-CASH":
            continue
        simbolo = linha["TckrSymb"].strip().upper()
        if not simbolo or simbolo in vistos:
            continue
        try:
            classificacao = _classificar_a_vista(linha)
        except KeyError as erro:
            resultado.nao_mapeados.append((simbolo, str(erro.args[0])))
            continue
        if classificacao is None:
            resultado.ignorados += 1
            continue
        vistos.add(simbolo)
        resultado.itens.append(_item_b3(linha, *classificacao))
    for linha in candidatos_renda_fixa:
        simbolo = linha["TckrSymb"].strip().upper()
        if simbolo in vistos:
            continue
        if linha["Asst"].strip() in etf_primario:
            vistos.add(simbolo)
            resultado.itens.append(_item_b3(linha, TIPO_ETF_BR, None))
        else:
            resultado.nao_mapeados.append((simbolo, CATEGORIA_ETF_RENDA_FIXA))
    if not conferidas:
        raise FormatoListaError("Arquivo da B3 vazio.")
    return resultado


# ------------------------------------------------------------------ EUA


def simbolo_yahoo_eua(simbolo: str) -> str | None:
    """Ticker no formato do Yahoo (``BRK.B`` → ``BRK-B``); ``None`` para sufixos especiais.

    Só letras/números com, no máximo, uma classe de uma letra. Preferenciais (``$``),
    warrants, direitos e units usam outros sufixos e não entram na lista.
    """
    texto = simbolo.strip().upper()
    base, ponto, classe = texto.partition(".")
    if not base.isalnum() or not base.isascii():
        return None
    if ponto and not (len(classe) == 1 and classe.isalpha() and classe.isascii()):
        return None
    return f"{base}-{classe}" if ponto else base


def _linhas_pipe(texto: str, nome_arquivo: str, colunas: tuple[str, ...]) -> list[dict[str, str]]:
    leitor = csv.DictReader(io.StringIO(texto), delimiter="|")
    cabecalho = [c.strip() for c in (leitor.fieldnames or [])]
    faltando = [c for c in colunas if c not in cabecalho]
    if faltando:
        raise FormatoListaError(
            f"{nome_arquivo} sem as colunas esperadas: " + ", ".join(faltando) + "."
        )
    leitor.fieldnames = cabecalho
    linhas = []
    for linha in leitor:
        primeira = (linha.get(cabecalho[0]) or "").strip()
        if primeira.startswith(RODAPE_NASDAQ):
            continue
        linhas.append({k: (v or "").strip() for k, v in linha.items() if k is not None})
    return linhas


def _item_eua(
    simbolo: str, nome: str, etf: str, bolsa: str, resultado: ResultadoClassificacao
) -> ItemListado | None:
    yahoo = simbolo_yahoo_eua(simbolo)
    if yahoo is None or etf not in {"Y", "N"}:
        resultado.ignorados += 1
        return None
    return ItemListado(
        bolsa=BOLSA_EUA,
        simbolo=yahoo,
        nome=nome or yahoo,
        tipo=TIPO_ETF_US if etf == "Y" else TIPO_ACAO_US,
        categoria="ETF" if etf == "Y" else "não ETF",
        simbolo_yahoo=yahoo,
        bolsa_eua=bolsa,
    )


def _bolsa_nasdaq(_linha: Mapping[str, str]) -> str:
    return "NASDAQ"


def _bolsa_otherlisted(linha: Mapping[str, str]) -> str:
    return BOLSAS_OTHERLISTED.get(linha["Exchange"], "OUTRA")


def classificar_nasdaq(nasdaqlisted: str, otherlisted: str) -> ResultadoClassificacao:
    """Classifica os dois arquivos do diretório de símbolos da NASDAQ."""
    resultado = ResultadoClassificacao()
    vistos: set[str] = set()
    fontes = (
        (
            _linhas_pipe(
                nasdaqlisted, "nasdaqlisted.txt", ("Symbol", "Security Name", "Test Issue", "ETF")
            ),
            "Symbol",
            _bolsa_nasdaq,
        ),
        (
            _linhas_pipe(
                otherlisted,
                "otherlisted.txt",
                ("ACT Symbol", "Security Name", "Exchange", "ETF", "Test Issue"),
            ),
            "ACT Symbol",
            _bolsa_otherlisted,
        ),
    )
    for linhas, coluna_simbolo, bolsa in fontes:
        for linha in linhas:
            if linha["Test Issue"] == "Y":
                resultado.ignorados += 1
                continue
            item = _item_eua(
                linha[coluna_simbolo], linha["Security Name"], linha["ETF"], bolsa(linha), resultado
            )
            if item is None or item.simbolo in vistos:
                continue
            vistos.add(item.simbolo)
            resultado.itens.append(item)
    if not resultado.itens:
        raise FormatoListaError("Diretório da NASDAQ sem nenhum símbolo.")
    return resultado
