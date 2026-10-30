"""Listas oficiais de tickers: classificação, fontes (rede simulada), importação e busca.

As linhas da B3 imitam o ``InstrumentsConsolidatedFile`` real de 30/10/2026 (mesmo
cabeçalho, mesmos valores de categoria/especificação/CFI dos papéis citados). Nenhum teste
acessa a internet.
"""

import csv
import io
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime

import httpx2
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.banco import criar_fabrica_sessoes, sessao_transacional
from app.domain.listas import (
    FormatoListaError,
    ItemListado,
    classificar_b3,
    classificar_nasdaq,
    simbolo_yahoo_eua,
)
from app.providers.base import (
    FonteIndisponivelError,
    ListaBaixada,
    ProviderError,
    RespostaInvalidaError,
    SimboloNaoEncontradoError,
    SugestaoNome,
)
from app.providers.coingecko import BuscaCoinGecko
from app.providers.http import ClienteHttp
from app.providers.listas_b3 import FonteListaB3, ler_arquivo_b3
from app.providers.listas_nasdaq import FonteListaNasdaq
from app.providers.registry import RegistroProviders
from app.providers.yahoo import BuscaYahoo
from app.repositories import modelos as m
from app.repositories.simbolos import RepositorioListasSimbolos, RepositorioSimbolosListados
from app.services.coleta import EventoColeta
from app.services.simbolos import (
    ImportadorListas,
    buscar_simbolos,
    limpar_texto_busca,
    tentou_hoje,
)
from tests import fabricas as f

CABECALHO_B3 = (
    "RptDt;TckrSymb;Asst;AsstDesc;SgmtNm;MktNm;SctyCtgyNm;XprtnDt;XprtnCd;TradgStartDt;"
    "TradgEndDt;BaseCd;ConvsCritNm;MtrtyDtTrgtPt;ReqrdConvsInd;ISIN;CFICd;DlvryNtceStartDt;"
    "DlvryNtceEndDt;OptnTp;CtrctMltplr;AsstQtnQty;AllcnRndLot;TradgCcy;DlvryTpNm;WdrwlDays;"
    "WrkgDays;ClnrDays;RlvrBasePricNm;OpngFutrPosDay;SdTpCd1;UndrlygTckrSymb1;SdTpCd2;"
    "UndrlygTckrSymb2;PureGoldWght;ExrcPric;OptnStyle;ValTpNm;PrmUpfrntInd;OpngPosLmtDt;"
    "DstrbtnId;PricFctr;DaysToSttlm;SrsTpNm;PrtcnFlg;AutomtcExrcInd;SpcfctnCd;CrpnNm;"
    "CorpActnStartDt;CtdyTrtmntTpNm;MktCptlstn;CorpGovnLvlNm"
)
COLUNAS = CABECALHO_B3.split(";")


def linha_b3(
    ticker: str,
    categoria: str,
    especificacao: str = "",
    nome: str = "",
    *,
    segmento: str = "CASH",
    mercado: str = "EQUITY-CASH",
    ativo: str | None = None,
    cfi: str = "",
) -> dict[str, str]:
    linha = dict.fromkeys(COLUNAS, "")
    linha.update(
        RptDt="2026-10-30",
        TckrSymb=ticker,
        Asst=ativo or ticker[:4],
        SgmtNm=segmento,
        MktNm=mercado,
        SctyCtgyNm=categoria,
        CFICd=cfi,
        SpcfctnCd=especificacao,
        CrpnNm=nome,
    )
    return linha


# Papéis conferidos no arquivo real (categoria, especificação e CFI como lá).
LINHAS_REAIS = [
    linha_b3("PETR4", "SHARES", "PN      N2", "PETROLEO BRASILEIRO S.A. PETROBRAS", cfi="EPNNPR"),
    linha_b3("PETR3", "SHARES", "ON      N2", "PETROLEO BRASILEIRO S.A. PETROBRAS", cfi="ESVUFR"),
    linha_b3("BRKM5", "SHARES", "PNA*    N1", "BRASKEM S.A.", cfi="EPNNPR"),
    linha_b3("TAEE11", "UNIT", "UNT     N2", "TRANSMISSORA ALIANÇA DE ENERGIA", cfi="EMXXXR"),
    linha_b3("AAPL34", "BDR", "DRN", "APPLE INC.", cfi="EDSXPR"),
    linha_b3("BIVB39", "BDR", "DRE", "ISHARES CORE S&P 500 ETF", cfi="EDMXPR"),
    linha_b3("BOVA11", "ETF EQUITIES", "CI  ATZ", "ISHARES IBOVESPA FUNDO DE ÍNDICE", cfi="CEOGES"),
    linha_b3("IVVB11", "ETF FOREIGN INDEX", "CI", "ISHARES S&P 500 FUNDO DE ÍNDICE", cfi="CEOGES"),
    linha_b3("HGLG11", "FUNDS", "CI", "PATRIA LOG - FDO INV IMOB", cfi="CICIRU"),
    linha_b3("XPML11", "FUNDS", "CI", "XP MALLS FDO INV IMOB FII RESP LIM", cfi="CMXXXS"),
    linha_b3("KNCA11", "FUNDS", "CI", "KINEA CRÉDITO AGRO FIAGRO RESP LIM", cfi="CICJRU"),
    linha_b3("KDIF11", "FUNDS", "CI", "KINEA INFRA - FDO INV COTAS", cfi="CICILY"),
    # Fora da lista: taxa de financiamento do termo, recibo, direito, warrant e índice.
    linha_b3("TAXA100", "SHARES", "DIA", "TAXA DE FINANCIAMENTO", cfi="EMXXXX"),
    linha_b3("ABCD9", "RECEIPTS", "REC", "RECIBO"),
    linha_b3("ABCD1", "RIGHTS", "DIR", "DIREITO"),
    linha_b3("ABCD13", "WARRANT", "BNS", "BONUS"),
    linha_b3("IBOV11", "INDEX", "IBO/", "INDICE"),
    # Categoria não mapeada (CPA): nunca vira "ação" por exclusão.
    linha_b3("XYZW3", "SHARES", "CPA", "CERTIFICADO"),
    # ETF de renda fixa: categoria própria + mercado primário de ETF do mesmo ativo.
    linha_b3(
        "FIXA11",
        "FIXED INCOME TRADABLE INSTRUMENT T1",
        segmento="FORWARD",
        mercado="FIXED INCOME",
        ativo="FIXA",
    ),
    linha_b3(
        "FIXAETF11H",
        "ETF PRIMARY MARKET - GROSS SETTLEMENT",
        segmento="ETF PRIMARY MARKET",
        mercado="FIXED INCOME",
        ativo="FIXA",
    ),
    # Mesma categoria de renda fixa, sem mercado primário de ETF: não identificado.
    linha_b3(
        "ZZZZ11",
        "FIXED INCOME TRADABLE INSTRUMENT T1",
        segmento="FORWARD",
        mercado="FIXED INCOME",
        ativo="ZZZZ",
    ),
    # Derivativo qualquer: ignorado sem barulho.
    linha_b3("PETRK400", "OPTION ON EQUITIES", segmento="OPTIONS", mercado="EQUITY-DERIVATE"),
]


def csv_b3(linhas: list[dict[str, str]], status: str | None = "Parcial") -> bytes:
    saida = io.StringIO()
    if status is not None:
        saida.write(f"Status do Arquivo: {status}\n")
    escritor = csv.DictWriter(saida, fieldnames=COLUNAS, delimiter=";", lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(linhas)
    return saida.getvalue().encode("latin-1")


def por_simbolo(itens: list[ItemListado]) -> dict[str, ItemListado]:
    return {i.simbolo: i for i in itens}


# ---------------------------------------------------------------- classificação B3


def test_classificacao_b3_segue_a_categoria_oficial() -> None:
    resultado = classificar_b3(LINHAS_REAIS)
    itens = por_simbolo(resultado.itens)
    tipos = {s: (i.tipo, i.tipo_papel) for s, i in itens.items()}
    assert tipos == {
        "PETR4": ("acao_br", "PN"),
        "PETR3": ("acao_br", "ON"),
        "BRKM5": ("acao_br", "PN"),  # "PNA*" → PN
        "TAEE11": ("acao_br", "UNIT"),
        "AAPL34": ("acao_br", "BDR"),
        "BIVB39": ("acao_br", "BDR"),  # BDR de ETF continua BDR (como a B3 registra)
        "BOVA11": ("etf_br", None),
        "IVVB11": ("etf_br", None),
        "HGLG11": ("fundo_listado", None),
        "XPML11": ("fundo_listado", None),  # CFI diferente (CMXXXS), mesma categoria FUNDS
        "KNCA11": ("fundo_listado", None),  # Fiagro
        "KDIF11": ("fundo_listado", None),  # FI-Infra
        "FIXA11": ("etf_br", None),  # ETF de renda fixa
    }
    # O "11" sozinho não decide nada: unit, ETF e FII com o mesmo final.
    assert {itens[t].tipo for t in ("TAEE11", "BOVA11", "HGLG11")} == {
        "acao_br",
        "etf_br",
        "fundo_listado",
    }
    assert sorted(resultado.nao_mapeados) == [
        ("XYZW3", "SHARES/CPA"),
        ("ZZZZ11", "FIXED INCOME TRADABLE INSTRUMENT T1"),
    ]
    assert resultado.ignorados == 5  # DIA, recibo, direito, warrant e índice
    assert itens["PETR4"].simbolo_yahoo == "PETR4.SA"
    assert itens["PETR4"].campos_sugeridos == {"tipo_papel": "PN"}
    assert itens["FIXA11"].nome == "FIXA11"  # sem CrpnNm: o próprio ticker


def test_classificacao_b3_ticker_repetido_fica_com_o_primeiro() -> None:
    linhas = [linha_b3("PETR4", "SHARES", "PN", "A"), linha_b3("PETR4", "SHARES", "PN", "B")]
    assert [i.nome for i in classificar_b3(linhas).itens] == ["A"]


def test_classificacao_b3_recusa_arquivo_sem_colunas_ou_vazio() -> None:
    with pytest.raises(FormatoListaError, match="SctyCtgyNm"):
        classificar_b3([{"TckrSymb": "PETR4", "Asst": "PETR"}])
    with pytest.raises(FormatoListaError, match="vazio"):
        classificar_b3([])


def test_ler_arquivo_b3_com_e_sem_linha_de_status() -> None:
    lista = ler_arquivo_b3(io.BytesIO(csv_b3(LINHAS_REAIS)), date(2026, 10, 30))
    assert lista.status_arquivo == "Parcial"
    assert lista.data_arquivo == date(2026, 10, 30)
    assert len(lista.itens) == 13
    sem_status = ler_arquivo_b3(io.BytesIO(csv_b3(LINHAS_REAIS, None)), date(2026, 10, 30))
    assert sem_status.status_arquivo is None
    assert len(sem_status.itens) == 13
    # Acentos em latin-1 chegam certos.
    assert por_simbolo(lista.itens)["KNCA11"].nome == "KINEA CRÉDITO AGRO FIAGRO RESP LIM"


def test_ler_arquivo_b3_sem_papeis_a_vista_e_resposta_invalida() -> None:
    so_derivativos = [LINHAS_REAIS[-1]]
    with pytest.raises(RespostaInvalidaError, match="sem papéis à vista"):
        ler_arquivo_b3(io.BytesIO(csv_b3(so_derivativos)), date(2026, 10, 30))
    with pytest.raises(RespostaInvalidaError, match="colunas esperadas"):
        ler_arquivo_b3(io.BytesIO(b"a;b\n1;2\n"), date(2026, 10, 30))


# ---------------------------------------------------------------- classificação EUA

NASDAQ = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|"
    "NextShares\n"
    "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
    "QQQ|Invesco QQQ Trust, Series 1|G|N|N|100|Y|N\n"
    "ZXZZT|NASDAQ TEST STOCK|G|Y|N|100|N|N\n"
    "File Creation Time: 1030202617:03|||||||\n"
)
OUTRAS = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
    "BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK.B\n"
    "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\n"
    "ABR$D|Arbor Realty Trust Preferred D|N|ABRpD|N|100|N|ABR-D\n"
    "IMO|Imperial Oil Limited|A|IMO|N|100|N|IMO\n"
    "File Creation Time: 1030202617:03|||||||\n"
)


def test_classificacao_nasdaq_pela_coluna_etf() -> None:
    resultado = classificar_nasdaq(NASDAQ, OUTRAS)
    itens = {i.simbolo: (i.tipo, i.bolsa_eua) for i in resultado.itens}
    assert itens == {
        "AAPL": ("acao_us", "NASDAQ"),
        "QQQ": ("etf_us", "NASDAQ"),
        "BRK-B": ("acao_us", "NYSE"),  # formato do Yahoo
        "SPY": ("etf_us", "OUTRA"),  # NYSE Arca
        "IMO": ("acao_us", "AMEX"),
    }
    assert resultado.ignorados == 2  # emissão de teste e preferencial ($)


def test_classificacao_nasdaq_exige_a_coluna_etf() -> None:
    sem_etf = "Symbol|Security Name|Market Category|Test Issue\nAAPL|Apple|Q|N\n"
    with pytest.raises(FormatoListaError, match=r"nasdaqlisted.txt sem as colunas esperadas: ETF"):
        classificar_nasdaq(sem_etf, OUTRAS)
    vazio = "Symbol|Security Name|Test Issue|ETF\n"
    vazio_outras = "ACT Symbol|Security Name|Exchange|ETF|Test Issue\n"
    with pytest.raises(FormatoListaError, match="sem nenhum símbolo"):
        classificar_nasdaq(vazio, vazio_outras)


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("AAPL", "AAPL"),
        ("brk.b", "BRK-B"),
        ("BRK.WS", None),  # warrant
        ("ABR$D", None),  # preferencial
        ("ABC=", None),  # unit
        ("", None),
    ],
)
def test_simbolo_yahoo_eua(bruto: str, esperado: str | None) -> None:
    assert simbolo_yahoo_eua(bruto) == esperado


# ---------------------------------------------------------------- fontes (rede simulada)


def cliente(manipulador: Callable[[httpx2.Request], httpx2.Response]) -> ClienteHttp:
    return ClienteHttp(
        "Teste",
        transporte=httpx2.MockTransport(manipulador),
        tentativas=1,
        dormir=lambda _s: None,
    )


def test_fonte_b3_baixa_em_dois_passos_e_volta_dias_sem_arquivo() -> None:
    pedidos: list[str] = []

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        pedidos.append(str(pedido.url))
        if pedido.url.path.endswith("/requestname"):
            dia = pedido.url.params["date"]
            assert pedido.url.params["fileName"] == "InstrumentsConsolidated"
            if dia == "2026-11-01":  # domingo: sem arquivo
                return httpx2.Response(404)
            if dia == "2026-10-31":  # sábado: token, mas o arquivo vem vazio
                return httpx2.Response(200, json={"token": "SAB"})
            return httpx2.Response(200, json={"redirectUrl": "~/download?token=T", "token": "T"})
        token = pedido.url.params["token"]
        if token == "SAB":
            return httpx2.Response(200, content=b"")
        return httpx2.Response(200, content=csv_b3(LINHAS_REAIS))

    lista = FonteListaB3(cliente(responder)).baixar(date(2026, 11, 1))
    assert lista.bolsa == "B3"
    assert lista.data_arquivo == date(2026, 10, 30)
    assert lista.status_arquivo == "Parcial"
    assert len(lista.itens) == 13
    assert any("token=T" in p for p in pedidos)


def test_fonte_b3_sem_arquivo_na_semana_e_rede_fora() -> None:
    sem = FonteListaB3(cliente(lambda _p: httpx2.Response(200, json={})))
    with pytest.raises(SimboloNaoEncontradoError, match="sem arquivo"):
        sem.baixar(date(2026, 10, 30))

    def fora(pedido: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("sem rede", request=pedido)

    with pytest.raises(FonteIndisponivelError):
        FonteListaB3(cliente(fora)).baixar(date(2026, 10, 30))


def test_fonte_nasdaq_baixa_os_dois_arquivos() -> None:
    def responder(pedido: httpx2.Request) -> httpx2.Response:
        texto = NASDAQ if pedido.url.path.endswith("nasdaqlisted.txt") else OUTRAS
        return httpx2.Response(200, text=texto)

    lista = FonteListaNasdaq(cliente(responder)).baixar(date(2026, 10, 30))
    assert lista.bolsa == "EUA"
    assert {i.simbolo for i in lista.itens} == {"AAPL", "QQQ", "BRK-B", "SPY", "IMO"}

    vazio = FonteListaNasdaq(cliente(lambda _p: httpx2.Response(200, text="")))
    with pytest.raises(RespostaInvalidaError, match="arquivo vazio"):
        vazio.baixar(date(2026, 10, 30))
    formato = FonteListaNasdaq(cliente(lambda _p: httpx2.Response(200, text="a|b\n1|2\n")))
    with pytest.raises(RespostaInvalidaError, match="colunas esperadas"):
        formato.baixar(date(2026, 10, 30))


def test_busca_yahoo_e_coingecko() -> None:
    def yahoo(pedido: httpx2.Request) -> httpx2.Response:
        assert pedido.url.params["q"] == "petr"
        return httpx2.Response(
            200,
            json={
                "quotes": [
                    {"symbol": "PETR4.SA", "longname": "Petróleo Brasileiro", "exchange": "SAO"},
                    {"symbol": "PBR", "shortname": "Petrobras ADR", "exchange": "NYQ"},
                    {"shortname": "sem símbolo"},
                    "lixo",
                ]
            },
        )

    sugestoes = BuscaYahoo(cliente(yahoo)).buscar("petr")
    assert sugestoes == [
        SugestaoNome("PETR4.SA", "Petróleo Brasileiro", "PETR4.SA", "SAO"),
        SugestaoNome("PBR", "Petrobras ADR", "PBR", "NYQ"),
    ]
    with pytest.raises(RespostaInvalidaError):
        BuscaYahoo(cliente(lambda _p: httpx2.Response(200, json={}))).buscar("x")

    def coingecko(_pedido: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "coins": [
                    {"id": "batcat", "symbol": "btc", "name": "Batcat", "market_cap_rank": None},
                    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap_rank": 1},
                    {"symbol": "sem-id"},
                ]
            },
        )

    moedas = BuscaCoinGecko(cliente(coingecko)).buscar("btc")
    assert [(s.simbolo, s.simbolo_externo) for s in moedas] == [
        ("BTC", "bitcoin"),  # maior valor de mercado primeiro
        ("BTC", "batcat"),
    ]


# ---------------------------------------------------------------- importação

AGORA = datetime(2026, 10, 30, 15, tzinfo=UTC)
HOJE = date(2026, 10, 30)


class FonteFalsa:
    def __init__(self, bolsa: str, itens: list[ItemListado]) -> None:
        self.bolsa = bolsa
        self.rotulo = f"Fonte {bolsa}"
        self.itens = itens
        self.falha: Exception | None = None
        self.chamadas: list[date] = []

    def baixar(self, hoje: date) -> ListaBaixada:
        self.chamadas.append(hoje)
        if self.falha is not None:
            raise self.falha
        return ListaBaixada(
            bolsa=self.bolsa,
            itens=self.itens,
            data_arquivo=hoje,
            status_arquivo="Parcial",
            nao_mapeados=[("XYZW3", "SHARES/CPA")],
        )


class BuscaFalsa:
    def __init__(self, nome: str, sugestoes: list[SugestaoNome]) -> None:
        self.nome = nome
        self.sugestoes = sugestoes
        self.falha: ProviderError | None = None
        self.textos: list[str] = []

    def buscar(self, texto: str) -> list[SugestaoNome]:
        self.textos.append(texto)
        if self.falha is not None:
            raise self.falha
        return self.sugestoes


@pytest.fixture
def fabrica(engine: Engine) -> sessionmaker[Session]:
    return criar_fabrica_sessoes(engine)


@pytest.fixture
def fonte_b3() -> FonteFalsa:
    return FonteFalsa("B3", classificar_b3(LINHAS_REAIS).itens)


@pytest.fixture
def fonte_eua() -> FonteFalsa:
    return FonteFalsa("EUA", classificar_nasdaq(NASDAQ, OUTRAS).itens)


@pytest.fixture
def providers(fonte_b3: FonteFalsa, fonte_eua: FonteFalsa) -> RegistroProviders:
    registro = RegistroProviders()
    registro.registrar_lista(fonte_b3)
    registro.registrar_lista(fonte_eua)
    return registro


@pytest.fixture
def eventos() -> list[EventoColeta]:
    return []


@pytest.fixture
def importador(
    fabrica: sessionmaker[Session], providers: RegistroProviders, eventos: list[EventoColeta]
) -> ImportadorListas:
    return ImportadorListas(fabrica, providers, relogio=lambda: AGORA, publicar=eventos.append)


def test_importa_as_bolsas_pendentes_e_registra_a_situacao(
    importador: ImportadorListas,
    fabrica: sessionmaker[Session],
    eventos: list[EventoColeta],
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert importador.pendentes() == ["B3", "EUA"]
    resultados = importador.executar()
    assert [(r.bolsa, r.sucesso, r.quantidade) for r in resultados] == [
        ("B3", True, 13),
        ("EUA", True, 5),
    ]
    assert importador.pendentes() == []
    with sessao_transacional(fabrica) as sessao:
        lista = RepositorioListasSimbolos(sessao).obter("B3")
        assert lista is not None
        assert (lista.quantidade, lista.status_arquivo, lista.data_arquivo) == (13, "Parcial", HOJE)
        assert lista.atualizado_em == AGORA
        assert lista.ultimo_erro is None
        hglg = RepositorioSimbolosListados(sessao).por_simbolo("B3", "HGLG11")
        assert hglg is not None
        assert (hglg.tipo, hglg.simbolo_yahoo) == ("fundo_listado", "HGLG11.SA")
        assert tentou_hoje(sessao, "B3", HOJE)
        assert not tentou_hoje(sessao, "B3", date(2026, 10, 31))
    assert [e.tipo for e in eventos] == ["lista_atualizada", "lista_atualizada"]
    assert "categoria não mapeada" in caplog.text  # papéis fora da lista vão para o log


def test_falha_na_importacao_mantem_a_lista_anterior(
    importador: ImportadorListas,
    fonte_b3: FonteFalsa,
    fabrica: sessionmaker[Session],
    eventos: list[EventoColeta],
) -> None:
    importador.executar(["B3"])
    fonte_b3.falha = FonteIndisponivelError("B3 indisponível no momento.")
    [resultado] = importador.executar(["B3"])
    assert not resultado.sucesso
    assert resultado.mensagem == "B3 indisponível no momento."
    fonte_b3.falha = RuntimeError("bug")
    [inesperado] = importador.executar(["B3"])
    assert inesperado.mensagem == "Erro inesperado ao importar a lista de B3."
    with sessao_transacional(fabrica) as sessao:
        lista = RepositorioListasSimbolos(sessao).obter("B3")
        assert lista is not None
        assert lista.quantidade == 13  # a lista anterior continua
        assert lista.ultimo_erro == "Erro inesperado ao importar a lista de B3."
        assert RepositorioSimbolosListados(sessao).por_simbolo("B3", "PETR4") is not None
    assert [e.tipo for e in eventos] == ["lista_atualizada", "erro_lista", "erro_lista"]
    assert importador.executar(["XX"]) == []  # bolsa sem fonte é ignorada


def test_reimportar_troca_a_lista_inteira(
    importador: ImportadorListas, fonte_b3: FonteFalsa, fabrica: sessionmaker[Session]
) -> None:
    importador.executar(["B3"])
    fonte_b3.itens = classificar_b3([linha_b3("VALE3", "SHARES", "ON", "VALE S.A.")]).itens
    importador.executar(["B3"])
    with sessao_transacional(fabrica) as sessao:
        repositorio = RepositorioSimbolosListados(sessao)
        assert repositorio.por_simbolo("B3", "PETR4") is None
        assert repositorio.por_simbolo("B3", "VALE3") is not None
        assert repositorio.por_simbolo("EUA", "AAPL") is None  # outra bolsa intacta


# ---------------------------------------------------------------- busca


@pytest.fixture
def com_listas(importador: ImportadorListas, fabrica: sessionmaker[Session]) -> Iterator[Session]:
    importador.executar()
    with sessao_transacional(fabrica) as sessao:
        yield sessao


def test_limpar_texto_busca_tira_curingas() -> None:
    assert limpar_texto_busca("  pe%tr_4 ") == "pe tr 4"
    assert limpar_texto_busca("BRK.B") == "BRK.B"
    assert limpar_texto_busca("x" * 100) == "x" * 60


def test_busca_traz_carteira_e_lista_com_o_tipo_oficial(com_listas: Session) -> None:
    sessao = com_listas
    f.acao_br(sessao, "PETR4")
    resultado = buscar_simbolos(sessao, "acao_br", "petr", RegistroProviders(), HOJE)
    assert [(i.simbolo, i.origem, i.tipo) for i in resultado.itens] == [
        ("PETR4", "carteira", "acao_br"),
        ("PETR3", "lista", "acao_br"),  # PETR4 já está na carteira: não repete
    ]
    assert resultado.itens[1].campos_sugeridos == {"tipo_papel": "ON"}
    assert resultado.itens[1].simbolo_externo == "PETR3.SA"
    assert resultado.lista_disponivel
    assert not resultado.lista_desatualizada

    # BOVA11 buscado como "ação": a lista diz que é ETF (o front avisa e sugere o tipo).
    bova = buscar_simbolos(sessao, "acao_br", "BOVA11", RegistroProviders(), HOJE)
    assert [(i.simbolo, i.tipo, i.campos_sugeridos) for i in bova.itens] == [
        ("BOVA11", "etf_br", {})
    ]
    # Busca pelo nome, sem diferenciar maiúsculas.
    nome = buscar_simbolos(sessao, "fundo_listado", "fiagro", RegistroProviders(), HOJE)
    assert [i.simbolo for i in nome.itens] == ["KNCA11"]
    eua = buscar_simbolos(sessao, "acao_us", "brk.b", RegistroProviders(), HOJE)
    assert [(i.simbolo, i.tipo, i.campos_sugeridos) for i in eua.itens] == [
        ("BRK-B", "acao_us", {"bolsa": "NYSE"})
    ]


def test_ticker_fora_da_lista_pede_atualizacao_e_sugere_so_o_nome(com_listas: Session) -> None:
    sessao = com_listas
    yahoo = BuscaFalsa(
        "yfinance",
        [
            SugestaoNome("NOVO3.SA", "Empresa Nova S.A.", "NOVO3.SA", "SAO"),
            SugestaoNome("NOVO", "Outra bolsa", "NOVO", "NYQ"),  # filtrada (não é B3)
        ],
    )
    providers = RegistroProviders()
    providers.registrar_busca(yahoo)
    # Lista importada hoje: não pede de novo (uma vez por dia).
    hoje = buscar_simbolos(sessao, "acao_br", "NOVO3", providers, HOJE)
    assert [(i.simbolo, i.tipo, i.origem) for i in hoje.itens] == [
        ("NOVO3", None, "pesquisa")  # tipo não identificado
    ]
    assert not hoje.lista_desatualizada
    amanha = buscar_simbolos(sessao, "acao_br", "NOVO3", providers, date(2026, 10, 31))
    assert amanha.lista_desatualizada
    # Prefixo de papéis listados não aciona a pesquisa externa.
    buscar_simbolos(sessao, "acao_br", "PET", providers, HOJE)
    assert yahoo.textos == ["NOVO3", "NOVO3"]
    # Pesquisa externa fora do ar: devolve o que tem, com aviso.
    yahoo.falha = FonteIndisponivelError("Yahoo Finance indisponível no momento.")
    falha = buscar_simbolos(sessao, "acao_br", "NOVO3", providers, HOJE)
    assert falha.itens == []
    assert falha.aviso == "Pesquisa externa indisponível: Yahoo Finance indisponível no momento."


def test_busca_sem_lista_importada_pede_a_importacao(sessao: Session) -> None:
    resultado = buscar_simbolos(sessao, "etf_us", "SPY", RegistroProviders(), HOJE)
    assert not resultado.lista_disponivel
    assert resultado.lista_desatualizada
    assert resultado.bolsa == "EUA"
    assert buscar_simbolos(sessao, "etf_us", "  ", RegistroProviders(), HOJE).itens == []


def test_busca_de_cripto_usa_a_coingecko_e_nao_repete_o_que_ja_tenho(sessao: Session) -> None:
    sessao.add(
        m.Ativo(
            tipo="cripto",
            simbolo="BTC",
            nome="Bitcoin",
            moeda="BRL",
            provider="coingecko",
            simbolo_externo="bitcoin",
            metadados={},
        )
    )
    sessao.flush()
    coingecko = BuscaFalsa(
        "coingecko",
        [
            SugestaoNome("BTC", "Bitcoin", "bitcoin"),
            SugestaoNome("BTC", "Batcat", "batcat"),
        ],
    )
    providers = RegistroProviders()
    providers.registrar_busca(coingecko)
    resultado = buscar_simbolos(sessao, "cripto", "btc", providers, HOJE)
    assert [(i.simbolo_externo, i.origem, i.tipo) for i in resultado.itens] == [
        ("bitcoin", "carteira", "cripto"),
        ("batcat", "pesquisa", "cripto"),
    ]
    assert resultado.bolsa is None


def test_busca_de_renda_fixa_so_olha_a_carteira(sessao: Session) -> None:
    f.cdb(sessao, nome="CDB Banco X")
    providers = RegistroProviders()
    yahoo = BuscaFalsa("yfinance", [])
    providers.registrar_busca(yahoo)
    resultado = buscar_simbolos(sessao, "renda_fixa", "banco x", providers, HOJE)
    assert [(i.nome, i.origem) for i in resultado.itens] == [("CDB Banco X", "carteira")]
    assert yahoo.textos == []
