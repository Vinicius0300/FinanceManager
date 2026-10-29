"""Estrutura de analytics (Protocols e registry), erros de domínio na API e inicialização."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.analytics.protocolos import (
    Backtester,
    FeatureBuilder,
    Predictor,
    Previsao,
    ResultadoBacktest,
    Strategy,
    Sugestao,
)
from app.analytics.registry import (
    REGISTRO_MODELOS,
    ModeloIndisponivelError,
    RegistroModelos,
    chave_versao,
)
from app.core import paths
from app.core.migracoes import revisao_do_banco
from app.domain.erros import (
    ConflitoError,
    DetalheCampo,
    NaoEncontradoError,
    PosicaoInsuficienteError,
    ValidacaoError,
)

# ---------------------------------------------------------------- Analytics


class PreditorIngenuo:
    """Exemplo mínimo que satisfaz o Protocol (repete o último valor)."""

    nome = "ingenuo"

    def __init__(self, versao: str = "1.0.0") -> None:
        self.versao = versao
        self.ultimo = Decimal(0)

    def treinar(self, features: pd.DataFrame, alvo: pd.Series) -> None:
        self.ultimo = Decimal(str(alvo.iloc[-1]))

    def prever(self, features: pd.DataFrame, data_referencia: date) -> Sequence[Previsao]:
        return [Previsao("ativo:1:preco", data_referencia, data_referencia, self.ultimo)]


class EstrategiaVazia:
    nome = "vazia"
    versao = "1.0.0"

    def sugerir(
        self, previsoes: Sequence[Previsao], carteira: pd.DataFrame, data_referencia: date
    ) -> Sequence[Sugestao]:
        return [Sugestao(data_referencia, "manter", None, "Sem mudanças.")]


class FeaturesVazias:
    nome = "vazias"

    def construir(self, dados: Mapping[str, pd.DataFrame], data_referencia: date) -> pd.DataFrame:
        return pd.DataFrame()


class BacktesterFixo:
    def executar(
        self,
        modelo: Predictor | Strategy,
        dados: Mapping[str, pd.DataFrame],
        inicio: date,
        fim: date,
    ) -> ResultadoBacktest:
        return ResultadoBacktest(inicio, fim, {"retorno_total": Decimal(0)})


def test_implementacoes_satisfazem_os_protocolos() -> None:
    assert isinstance(PreditorIngenuo(), Predictor)
    assert isinstance(EstrategiaVazia(), Strategy)
    assert isinstance(FeaturesVazias(), FeatureBuilder)
    assert isinstance(BacktesterFixo(), Backtester)
    assert not isinstance(object(), Predictor)
    preditor = PreditorIngenuo()
    preditor.treinar(pd.DataFrame(), pd.Series([1, 2, 3]))
    assert preditor.prever(pd.DataFrame(), date(2025, 1, 1))[0].valor == Decimal(3)


def test_registro_de_modelos_versionados() -> None:
    registro = RegistroModelos()
    registro.registrar("ingenuo", "1.9.0", lambda: PreditorIngenuo("1.9.0"))
    registro.registrar("ingenuo", "1.10.0", lambda: PreditorIngenuo("1.10.0"), "mais nova")
    registro.registrar("estrategia", "0.1.0", EstrategiaVazia)
    # 1.10.0 > 1.9.0 (comparação numérica, não alfabética).
    assert registro.versoes("ingenuo") == ["1.9.0", "1.10.0"]
    assert registro.obter("ingenuo").versao == "1.10.0"
    assert registro.obter("ingenuo", "1.9.0").versao == "1.9.0"
    assert [(r.nome, r.versao) for r in registro.listar()] == [
        ("estrategia", "0.1.0"),
        ("ingenuo", "1.9.0"),
        ("ingenuo", "1.10.0"),
    ]
    with pytest.raises(ValueError, match="já registrado"):
        registro.registrar("ingenuo", "1.9.0", PreditorIngenuo)
    with pytest.raises(ValueError, match="Versão inválida"):
        registro.registrar("ingenuo", "v2", PreditorIngenuo)
    with pytest.raises(ModeloIndisponivelError, match="não registrado"):
        registro.obter("lstm")
    with pytest.raises(ModeloIndisponivelError, match=r"Versão 3\.0\.0"):
        registro.obter("ingenuo", "3.0.0")


def test_modelo_com_dependencia_opcional_ausente() -> None:
    def fabrica_pesada() -> Predictor:
        import biblioteca_de_ml_inexistente  # type: ignore[import-not-found]  # noqa: F401

        return PreditorIngenuo()

    registro = RegistroModelos()
    registro.registrar("pesado", "1.0.0", fabrica_pesada)
    with pytest.raises(ModeloIndisponivelError, match="componente opcional"):
        registro.obter("pesado")


def test_nenhum_modelo_registrado_nesta_fase() -> None:
    assert REGISTRO_MODELOS.listar() == []
    assert chave_versao("2.0.10") == (2, 0, 10)


# ---------------------------------------------------------------- Erros de domínio na API


@pytest.fixture
def app_com_erros(app: FastAPI) -> FastAPI:
    erros = {
        "validacao": ValidacaoError("Dados inválidos.", [DetalheCampo("valor", "Obrigatório.")]),
        "nao-encontrado": NaoEncontradoError("Ativo 9 não encontrado."),
        "conflito": ConflitoError("Já existe."),
        "posicao": PosicaoInsuficienteError("Venda maior que a posição."),
    }

    def rota_que_levanta(erro: Exception) -> Callable[[], None]:
        def rota() -> None:
            raise erro

        return rota

    for nome, erro in erros.items():
        app.add_api_route(f"/teste/{nome}", rota_que_levanta(erro))
    return app


@pytest.mark.parametrize(
    ("rota", "status", "corpo"),
    [
        (
            "validacao",
            422,
            {
                "codigo": "validacao",
                "mensagem": "Dados inválidos.",
                "detalhes": [{"campo": "valor", "mensagem": "Obrigatório."}],
            },
        ),
        (
            "nao-encontrado",
            404,
            {"codigo": "nao_encontrado", "mensagem": "Ativo 9 não encontrado."},
        ),
        ("conflito", 409, {"codigo": "conflito", "mensagem": "Já existe."}),
        (
            "posicao",
            422,
            {"codigo": "posicao_insuficiente", "mensagem": "Venda maior que a posição."},
        ),
    ],
)
def test_erros_de_dominio_viram_respostas_em_pt_br(
    app_com_erros: FastAPI, rota: str, status: int, corpo: dict[str, object]
) -> None:
    with TestClient(app_com_erros) as cliente:
        resposta = cliente.get(f"/teste/{rota}")
    assert resposta.status_code == status
    assert resposta.json() == corpo


# ---------------------------------------------------------------- Inicialização


def test_inicializacao_migra_o_banco_e_abre_a_engine(cliente: TestClient, app: FastAPI) -> None:
    assert paths.caminho_banco().exists()
    assert revisao_do_banco(paths.caminho_banco()) == "0003_precos_diarios_estado_coleta"
    with app.state.engine.connect() as conexao:
        assert conexao.execute(text("PRAGMA foreign_keys")).scalar() == 1
    with app.state.fabrica_sessoes() as sessao:
        assert sessao.execute(text("SELECT count(*) FROM ativos")).scalar() == 0
