"""Registry de tipos de ativo: schema, validação, valor atual e extensão (7º tipo)."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import ClassVar

import pytest
from sqlalchemy.orm import Session

from app.asset_types.base import (
    CampoEspecifico,
    HandlerCotado,
    Metadados,
    Opcao,
    TipoCampo,
)
from app.asset_types.catalogo import HANDLERS_PADRAO, REGISTRO_PADRAO, criar_registro_padrao
from app.asset_types.fundo import cnpj_valido
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import Indexador, OrigemPreco, TipoIndicador, TipoTransacao
from app.domain.erros import DetalheCampo, OperacaoNaoPermitidaError, ValidacaoError
from app.domain.indicadores import Indicadores, PontoIndicador, SerieIndicador
from app.domain.montante import Aporte, aplicar_operacoes_montante
from app.domain.posicao import Compra, aplicar_operacoes
from app.domain.precos import PontoPreco, SeriePrecos
from app.services.cadastros import NovoAtivo, criar_ativo

D = Decimal
METADADOS_CDB = {
    "indexador": "cdi",
    "taxa": "110",
    "data_aplicacao": "2025-08-01",
    "vencimento": "2027-08-02",
    "emissor": "Banco X",
    "liquidez": "diaria",
}


def erros_de(excecao: pytest.ExceptionInfo[ValidacaoError]) -> dict[str, str]:
    return {d.campo: d.mensagem for d in excecao.value.detalhes}


# ---------------------------------------------------------------- Registry e schema


def test_registro_padrao_tem_os_dez_tipos() -> None:
    assert REGISTRO_PADRAO.slugs == [
        "acao_br",
        "acao_us",
        "cripto",
        "etf_br",
        "etf_us",
        "fundo",
        "fundo_listado",
        "poupanca",
        "renda_fixa",
        "tesouro_direto",
    ]
    assert "acao_br" in REGISTRO_PADRAO
    assert "fii" not in REGISTRO_PADRAO


def test_schemas_sao_serializaveis_e_completos() -> None:
    for handler in REGISTRO_PADRAO.todos():
        schema = handler.schema()
        json.dumps(schema)  # o front recebe isso como JSON
        assert set(schema) == {
            "slug",
            "nome",
            "descricao",
            "modo",
            "moeda_padrao",
            "moedas_aceitas",
            "provider",
            "tipos_transacao",
            "aceita_taxas",
            "busca_por_ticker",
            "lista_simbolos",
            "campos",
        }
        assert schema["moeda_padrao"] in schema["moedas_aceitas"]


def test_schema_da_renda_fixa() -> None:
    schema = REGISTRO_PADRAO.obter("renda_fixa").schema()
    assert schema["modo"] == "montante"
    assert schema["provider"] is None
    assert schema["tipos_transacao"] == ["aporte", "resgate"]
    taxa = next(c for c in schema["campos"] if c["nome"] == "taxa")
    assert taxa == {
        "nome": "taxa",
        "rotulo": "Taxa",
        "tipo": "decimal",
        "obrigatorio": True,
        "ajuda": "Prefixado: % ao ano. % do CDI: percentual (ex.: 110). IPCA +: % ao ano.",
        "opcoes": [],
        "minimo": "0",
        "maximo": "1000",
        "tamanho_maximo": None,
    }


@pytest.mark.parametrize(
    ("slug", "provider", "moedas"),
    [
        ("acao_br", "yfinance", ("BRL",)),
        ("acao_us", "yfinance", ("USD",)),
        ("fundo", "cvm", ("BRL",)),
        ("cripto", "coingecko", ("BRL", "USD")),
        ("renda_fixa", None, ("BRL",)),
        ("poupanca", None, ("BRL",)),
        ("tesouro_direto", "tesouro", ("BRL",)),
    ],
)
def test_provider_e_moedas_de_cada_tipo(
    slug: str, provider: str | None, moedas: tuple[str]
) -> None:
    handler = REGISTRO_PADRAO.obter(slug)
    assert handler.provider == provider
    assert handler.moedas_aceitas == moedas


def test_tipo_desconhecido() -> None:
    with pytest.raises(ValidacaoError, match="Tipo de ativo desconhecido: 'imovel'"):
        REGISTRO_PADRAO.obter("imovel")


# ---------------------------------------------------------------- Validação de metadados


def test_renda_fixa_valida_e_normaliza() -> None:
    handler = REGISTRO_PADRAO.obter("renda_fixa")
    normalizados = handler.validar_metadados(
        {**METADADOS_CDB, "taxa": 110, "emissor": "  Banco X "}
    )
    assert normalizados == {**METADADOS_CDB, "taxa": "110"}
    assert handler.indicadores_necessarios(normalizados) == {TipoIndicador.CDI}
    ipca = {**normalizados, "indexador": "ipca"}
    assert handler.indicadores_necessarios(ipca) == {TipoIndicador.IPCA}
    assert handler.indicadores_necessarios({**normalizados, "indexador": "pre"}) == set()


def test_renda_fixa_campos_faltando_desconhecidos_e_invalidos() -> None:
    handler = REGISTRO_PADRAO.obter("renda_fixa")
    with pytest.raises(ValidacaoError) as erro:
        handler.validar_metadados(
            {
                "indexador": "selic",
                "taxa": 1.5,
                "data_aplicacao": "01/08/2025",
                "emissor": "",
                "cor": "azul",
            }
        )
    assert erro.value.mensagem == "Dados inválidos para Renda fixa."
    assert erros_de(erro) == {
        "cor": "Campo desconhecido para este tipo de ativo.",
        "indexador": "Opção inválida. Use uma de: pre, cdi, ipca.",
        "taxa": "Informe um número (use ponto como separador decimal).",
        "data_aplicacao": "Data inválida. Use o formato AAAA-MM-DD.",
        "vencimento": "Campo obrigatório.",
        "emissor": "Campo obrigatório.",
        "liquidez": "Campo obrigatório.",
    }


def test_renda_fixa_regras_entre_campos() -> None:
    handler = REGISTRO_PADRAO.obter("renda_fixa")
    with pytest.raises(ValidacaoError) as erro:
        handler.validar_metadados({**METADADOS_CDB, "taxa": "0", "vencimento": "2025-08-01"})
    assert erros_de(erro) == {
        "taxa": "A taxa deve ser maior que zero.",
        "vencimento": "O vencimento deve ser posterior à data de aplicação.",
    }
    with pytest.raises(ValidacaoError) as acima:
        handler.validar_metadados({**METADADOS_CDB, "taxa": "1000.01"})
    assert erros_de(acima) == {"taxa": "O valor máximo é 1000."}


def test_fundo_valida_cnpj() -> None:
    handler = REGISTRO_PADRAO.obter("fundo")
    assert handler.validar_metadados({"cnpj": "11.222.333/0001-81"}) == {"cnpj": "11222333000181"}
    with pytest.raises(ValidacaoError) as erro:
        handler.validar_metadados({"cnpj": "11.222.333/0001-82"})
    assert erros_de(erro) == {"cnpj": "CNPJ inválido."}
    assert not cnpj_valido("11111111111111")
    assert not cnpj_valido("123")


def test_acao_br_campos_opcionais() -> None:
    handler = REGISTRO_PADRAO.obter("acao_br")
    assert handler.validar_metadados({}) == {}
    assert handler.validar_metadados({"tipo_papel": "PN", "setor": None}) == {"tipo_papel": "PN"}
    with pytest.raises(ValidacaoError) as erro:
        handler.validar_metadados({"tipo_papel": "XX", "setor": "s" * 61})
    assert erros_de(erro) == {
        "tipo_papel": "Opção inválida. Use uma de: ON, PN, UNIT, BDR.",
        "setor": "Use no máximo 60 caracteres.",
    }


def test_campo_texto_e_inteiro_genericos() -> None:
    campo_texto = CampoEspecifico("x", "X", TipoCampo.TEXTO)
    with pytest.raises(ValueError, match="Informe um texto"):
        campo_texto.normalizar(10)
    with pytest.raises(ValueError, match="obrigatório"):
        campo_texto.normalizar("   ")
    inteiro = CampoEspecifico("n", "N", TipoCampo.INTEIRO, minimo=D(1), maximo=D(10))
    assert inteiro.normalizar(5) == 5
    for invalido in (True, "5", 5.0):
        with pytest.raises(ValueError, match="inteiro"):
            inteiro.normalizar(invalido)
    with pytest.raises(ValueError, match="mínimo é 1"):
        inteiro.normalizar(0)
    data = CampoEspecifico("d", "D", TipoCampo.DATA)
    assert data.normalizar(date(2025, 1, 2)) == "2025-01-02"
    with pytest.raises(ValueError, match="Data inválida"):
        data.normalizar(20250102)
    decimal = CampoEspecifico("v", "V", TipoCampo.DECIMAL)
    with pytest.raises(ValueError, match="Informe um número"):
        decimal.normalizar("abc")


def test_validar_moeda_por_tipo() -> None:
    assert REGISTRO_PADRAO.obter("acao_us").validar_moeda(None) == "USD"
    assert REGISTRO_PADRAO.obter("cripto").validar_moeda("usd") == "USD"
    with pytest.raises(ValidacaoError, match="Ação \\(EUA\\) aceita apenas: USD"):
        REGISTRO_PADRAO.obter("acao_us").validar_moeda("BRL")


# ---------------------------------------------------------------- Transações aceitas


def test_transacoes_aceitas_por_tipo() -> None:
    cripto = REGISTRO_PADRAO.obter("cripto")
    cripto.validar_transacao({}, TipoTransacao.COMPRA, date(2025, 1, 1))
    with pytest.raises(OperacaoNaoPermitidaError, match="não aceita transação do tipo provento"):
        cripto.validar_transacao({}, TipoTransacao.PROVENTO, date(2025, 1, 1))
    with pytest.raises(OperacaoNaoPermitidaError):
        REGISTRO_PADRAO.obter("poupanca").validar_transacao(
            {}, TipoTransacao.COMPRA, date(2025, 1, 1)
        )


def test_renda_fixa_datas_das_transacoes() -> None:
    handler = REGISTRO_PADRAO.obter("renda_fixa")
    metadados: Metadados = dict(METADADOS_CDB)
    handler.validar_transacao(metadados, TipoTransacao.APORTE, date(2025, 8, 1))
    handler.validar_transacao(metadados, TipoTransacao.RESGATE, date(2028, 1, 1))  # pós-vencimento
    with pytest.raises(OperacaoNaoPermitidaError, match="anterior à aplicação"):
        handler.validar_transacao(metadados, TipoTransacao.APORTE, date(2025, 7, 31))
    with pytest.raises(OperacaoNaoPermitidaError, match="vencido"):
        handler.validar_transacao(metadados, TipoTransacao.APORTE, date(2027, 8, 2))


# ---------------------------------------------------------------- Valor atual


def precos(*pontos: tuple[date, str]) -> SeriePrecos:
    return SeriePrecos(
        PontoPreco(datetime(d.year, d.month, d.day, 15, tzinfo=UTC), D(v), OrigemPreco.AUTOMATICO)
        for d, v in pontos
    )


def test_ativo_cotado_usa_ultimo_preco() -> None:
    handler = REGISTRO_PADRAO.obter("acao_br")
    assert isinstance(handler, HandlerCotado)
    estado = aplicar_operacoes([Compra(date(2025, 1, 2), D(100), D(10))])
    hoje = date(2025, 1, 10)
    valoracao = handler.avaliar(estado, precos((date(2025, 1, 9), "12.50")), hoje)
    assert valoracao.valor == D(1250)  # 100 × 12,50
    assert valoracao.preco_unitario == D("12.50")
    assert valoracao.origem is OrigemPreco.AUTOMATICO
    assert valoracao.data_preco == date(2025, 1, 9)
    assert not valoracao.defasado
    # Preço com 5 dias (> 4 de tolerância) fica marcado como defasado.
    antigo = handler.avaliar(estado, precos((hoje - timedelta(days=5), "12")), hoje)
    assert antigo.defasado


def test_ativo_sem_cotacao_usa_preco_medio() -> None:
    handler = REGISTRO_PADRAO.obter("acao_br")
    assert isinstance(handler, HandlerCotado)
    estado = aplicar_operacoes([Compra(date(2025, 1, 2), D(100), D(10), taxas=D(5))])
    valoracao = handler.avaliar(estado, SeriePrecos(), date(2025, 1, 10))
    assert valoracao.valor == D(1005)
    assert valoracao.preco_unitario == D("10.05")
    assert valoracao.origem is OrigemPreco.CALCULADO
    assert valoracao.defasado
    assert valoracao.aviso == "Sem cotação registrada: usando o preço médio de compra."


def test_cripto_fica_defasada_depois_de_um_dia() -> None:
    handler = REGISTRO_PADRAO.obter("cripto")
    assert isinstance(handler, HandlerCotado)
    estado = aplicar_operacoes([Compra(date(2025, 1, 2), D("0.5"), D(100000))])
    assert (
        handler.avaliar(estado, precos((date(2025, 1, 9), "1")), date(2025, 1, 10)).defasado
        is False
    )
    assert handler.avaliar(estado, precos((date(2025, 1, 8), "1")), date(2025, 1, 10)).defasado


def test_renda_fixa_e_poupanca_tem_valor_calculado() -> None:
    from app.asset_types.base import HandlerMontante

    indicadores = Indicadores(
        [
            SerieIndicador(TipoIndicador.CDI, [PontoIndicador(date(2025, 1, 1), D("14.90"))]),
            SerieIndicador(TipoIndicador.SELIC, [PontoIndicador(date(2025, 1, 1), D(15))]),
        ]
    )
    renda_fixa = REGISTRO_PADRAO.obter("renda_fixa")
    assert isinstance(renda_fixa, HandlerMontante)
    metadados = renda_fixa.validar_metadados({**METADADOS_CDB, "taxa": "100"})
    fator = renda_fixa.criar_fator(metadados, indicadores)
    estado = aplicar_operacoes_montante([Aporte(date(2025, 8, 1), D(10000))], fator)
    valoracao = renda_fixa.avaliar(estado, fator, date(2025, 9, 1))
    assert valoracao.origem is OrigemPreco.CALCULADO
    assert valoracao.data_preco == date(2025, 9, 1)
    assert round(valoracao.valor, 2) == D("10116.42")

    poupanca = REGISTRO_PADRAO.obter("poupanca")
    assert isinstance(poupanca, HandlerMontante)
    assert poupanca.indicadores_necessarios({}) == {TipoIndicador.SELIC}
    fator_poupanca = poupanca.criar_fator({}, indicadores)
    estado_poupanca = aplicar_operacoes_montante(
        [Aporte(date(2025, 1, 10), D(1000))], fator_poupanca
    )
    assert poupanca.avaliar(estado_poupanca, fator_poupanca, date(2025, 2, 10)).valor == D(1005)
    assert Indexador.CDI.value == metadados["indexador"]


# ---------------------------------------------------------------- Extensão: 7º tipo


class Fii(HandlerCotado):
    """Exemplo de 7º tipo (o mesmo de docs/TIPOS_DE_ATIVO.md)."""

    slug = "fii"
    nome = "Fundo imobiliário"
    descricao = "Cotas de fundos imobiliários negociadas na B3."
    moedas_aceitas: ClassVar[tuple[str, ...]] = ("BRL",)
    provider = "yfinance"
    campos = (
        CampoEspecifico(
            nome="segmento",
            rotulo="Segmento",
            tipo=TipoCampo.ESCOLHA,
            obrigatorio=False,
            opcoes=(Opcao("logistica", "Logística"), Opcao("papel", "Papel (CRI)")),
        ),
        CampoEspecifico(nome="cnpj", rotulo="CNPJ", tipo=TipoCampo.TEXTO, tamanho_maximo=18),
    )

    def regras_adicionais(self, metadados: Metadados) -> list[DetalheCampo]:
        return (
            [] if cnpj_valido(str(metadados["cnpj"])) else [DetalheCampo("cnpj", "CNPJ inválido.")]
        )


def test_tipo_novo_entra_sem_alterar_os_existentes(sessao: Session) -> None:
    registro = criar_registro_padrao()
    schemas_antes = {h.slug: h.schema() for h in registro.todos()}
    registro.registrar(Fii())

    assert registro.slugs == sorted([*schemas_antes, "fii"])
    assert {h.slug: h.schema() for h in registro.todos() if h.slug != "fii"} == schemas_antes
    assert len(HANDLERS_PADRAO) == 10  # o catálogo padrão não mudou
    ativo = criar_ativo(
        sessao,
        NovoAtivo(
            tipo="fii", nome="FII Teste", simbolo="tstf11", metadados={"cnpj": "11222333000181"}
        ),
        registro=registro,
    )
    assert (ativo.tipo, ativo.simbolo, ativo.provider) == ("fii", "TSTF11", "yfinance")
    with pytest.raises(ValidacaoError, match="desconhecido"):
        criar_ativo(sessao, NovoAtivo(tipo="fii", nome="X"))  # registro padrão não conhece


def test_registro_recusa_slug_duplicado_invalido_ou_sem_moeda() -> None:
    registro = RegistroTiposAtivo()
    registro.registrar(Fii())
    with pytest.raises(ValueError, match="já registrado"):
        registro.registrar(Fii())

    class SlugRuim(Fii):
        slug = "FII-X"

    with pytest.raises(ValueError, match="Slug de tipo de ativo inválido"):
        registro.registrar(SlugRuim())

    class SemMoeda(Fii):
        slug = "sem_moeda"
        moedas_aceitas: ClassVar[tuple[str, ...]] = ()

    with pytest.raises(ValueError, match="ao menos uma moeda"):
        registro.registrar(SemMoeda())


# ---------------------------------------------------------------- Tesouro Direto

METADADOS_TESOURO: Metadados = {"titulo": "ipca_juros", "vencimento": "2035-05-15"}


def test_tesouro_direto_e_cotado_sem_taxas_e_diario() -> None:
    from app.domain.agenda import AGENDA_DIARIA

    handler = REGISTRO_PADRAO.obter("tesouro_direto")
    schema = handler.schema()
    assert schema["modo"] == "cotas"
    assert schema["aceita_taxas"] is False
    assert schema["tipos_transacao"] == ["compra", "provento", "venda"]
    assert [c["nome"] for c in schema["campos"]] == ["titulo", "vencimento"]
    titulo = schema["campos"][0]
    assert [o["valor"] for o in titulo["opcoes"]] == [
        "selic",
        "prefixado",
        "prefixado_juros",
        "ipca",
        "ipca_juros",
        "renda_mais",
        "educa_mais",
    ]
    assert handler.agenda is AGENDA_DIARIA
    assert REGISTRO_PADRAO.obter("renda_fixa").aceita_taxas is True


def test_tesouro_direto_valida_campos() -> None:
    handler = REGISTRO_PADRAO.obter("tesouro_direto")
    assert handler.validar_metadados(METADADOS_TESOURO) == METADADOS_TESOURO
    with pytest.raises(ValidacaoError) as erro:
        handler.validar_metadados({"titulo": "lft", "vencimento": "2035"})
    assert set(erros_de(erro)) == {"titulo", "vencimento"}


def test_tesouro_direto_regras_de_transacao() -> None:
    handler = REGISTRO_PADRAO.obter("tesouro_direto")
    handler.validar_transacao(METADADOS_TESOURO, TipoTransacao.COMPRA, date(2035, 5, 14))
    handler.validar_transacao(METADADOS_TESOURO, TipoTransacao.PROVENTO, date(2030, 5, 15))
    handler.validar_transacao(METADADOS_TESOURO, TipoTransacao.VENDA, date(2035, 5, 15))
    with pytest.raises(OperacaoNaoPermitidaError, match="vencido em 15/05/2035"):
        handler.validar_transacao(METADADOS_TESOURO, TipoTransacao.COMPRA, date(2035, 5, 15))
    sem_cupom: Metadados = {"titulo": "ipca", "vencimento": "2035-05-15"}
    with pytest.raises(OperacaoNaoPermitidaError, match="juros semestrais"):
        handler.validar_transacao(sem_cupom, TipoTransacao.PROVENTO, date(2030, 5, 15))
    with pytest.raises(OperacaoNaoPermitidaError, match="aporte"):
        handler.validar_transacao(METADADOS_TESOURO, TipoTransacao.APORTE, date(2030, 5, 15))


def test_tesouro_direto_vale_quantidade_vezes_pu() -> None:
    # 2,5 títulos × PU de R$ 4.000,00 = R$ 10.000,00
    handler = REGISTRO_PADRAO.obter("tesouro_direto")
    assert isinstance(handler, HandlerCotado)
    estado = aplicar_operacoes([Compra(date(2026, 1, 5), D("2.5"), D("3800"), D(0), D(1), 1)])
    valoracao = handler.avaliar(estado, precos((date(2026, 10, 28), "4000")), date(2026, 10, 29))
    assert valoracao.valor == D("10000.0")
    assert valoracao.origem is OrigemPreco.AUTOMATICO
    assert valoracao.defasado is False
