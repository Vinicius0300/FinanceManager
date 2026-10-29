"""Portfólio: resumo, posições, alocação, evolução, maiores ativos, variação do dia e
rentabilidade, na **Análise Geral** (sem ``instituicao_id``) ou **por Instituição**.

Arredondamento na saída (apresentação; os cálculos internos não arredondam):
dinheiro com 2 casas, preço/quantidade com 8, razões (percentuais como 0,1234) com 8.
"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query

from app.api.dependencias import PROTEGIDO, HojeDep, SessaoDep, respostas
from app.api.schemas import Modelo, Numero
from app.domain.carteira import FatiaAlocacao, SaldoCaixa
from app.domain.enums import OrigemPreco
from app.domain.erros import exigir
from app.domain.metricas import Metricas
from app.domain.numeros import arredondar, arredondar_moeda
from app.services.cadastros import listar_instituicoes, obter_instituicao
from app.services.carteira import avaliar_carteira
from app.services.patrimonio import serie_patrimonio
from app.services.portfolio import Portfolio, PosicaoPortfolio, VariacaoDia, montar_portfolio

router = APIRouter(prefix="/api/portfolio", tags=["portfólio"], dependencies=PROTEGIDO)

CASAS_SAIDA = 8
DIAS_MAXIMOS_EVOLUCAO = 366


def _moeda(valor: Decimal) -> Decimal:
    return arredondar_moeda(valor)


def _moeda_opcional(valor: Decimal | None) -> Decimal | None:
    return None if valor is None else arredondar_moeda(valor)


def _fino(valor: Decimal | None) -> Decimal | None:
    return None if valor is None else arredondar(valor, CASAS_SAIDA).normalize()


class MetricasSaida(Modelo):
    valor_atual: Numero
    custo: Numero
    lucro_nao_realizado: Numero
    valorizacao: Numero | None
    lucro_realizado: Numero
    proventos: Numero
    rendimentos_bonificacao: Numero
    resultado_total: Numero
    total_investido: Numero
    rentabilidade_total: Numero | None


class VariacaoDiaSaida(Modelo):
    preco_atual: Numero
    data_atual: date
    preco_anterior: Numero
    data_anterior: date
    variacao: Numero | None
    variacao_brl: Numero | None


class PosicaoSaida(Modelo):
    ativo_id: int
    nome: str
    simbolo: str | None
    tipo: str
    moeda: str
    instituicao_id: int | None
    quantidade: Numero | None
    preco_medio: Numero | None
    preco_atual: Numero | None
    valor: Numero | None
    valor_brl: Numero | None
    origem: OrigemPreco | None
    data_preco: date | None
    defasado: bool
    aviso: str | None
    erro: str | None
    participacao: Numero | None
    metricas: MetricasSaida | None
    metricas_brl: MetricasSaida | None
    variacao_dia: VariacaoDiaSaida | None


class CaixaSaida(Modelo):
    instituicao_id: int
    moeda: str
    saldo: Numero
    saldo_brl: Numero | None
    defasado: bool
    aviso: str | None
    erro: str | None


class FatiaSaida(Modelo):
    grupo: str
    valor: Numero
    percentual: Numero


class ResumoSaida(Modelo):
    data_ref: date
    instituicao_id: int | None
    investimentos_brl: Numero
    caixa_brl: Numero
    patrimonio_brl: Numero
    completo: bool
    variacao_dia_brl: Numero
    variacao_dia: Numero | None
    rentabilidade: MetricasSaida | None
    caixas: list[CaixaSaida]


class ResumoInstituicao(Modelo):
    instituicao_id: int
    nome: str
    investimentos_brl: Numero
    caixa_brl: Numero
    patrimonio_brl: Numero
    completo: bool


class PontoEvolucao(Modelo):
    data: date
    investimentos: Numero
    caixa: Numero
    patrimonio: Numero


class EvolucaoSaida(Modelo):
    pontos: list[PontoEvolucao]
    avisos: list[str]


class VariacaoAtivoSaida(Modelo):
    ativo_id: int
    nome: str
    variacao: VariacaoDiaSaida


class VariacaoCarteiraSaida(Modelo):
    variacao_dia_brl: Numero
    variacao_dia: Numero | None
    ativos: list[VariacaoAtivoSaida]


class RentabilidadeAtivo(Modelo):
    ativo_id: int
    nome: str
    metricas_brl: MetricasSaida | None


class RentabilidadeSaida(Modelo):
    carteira: MetricasSaida | None
    ativos: list[RentabilidadeAtivo]


# ---------------------------------------------------------------- conversões


def _metricas(metricas: Metricas | None) -> MetricasSaida | None:
    if metricas is None:
        return None
    return MetricasSaida(
        valor_atual=_moeda(metricas.valor_atual),
        custo=_moeda(metricas.custo),
        lucro_nao_realizado=_moeda(metricas.lucro_nao_realizado),
        valorizacao=_fino(metricas.valorizacao),
        lucro_realizado=_moeda(metricas.lucro_realizado),
        proventos=_moeda(metricas.proventos),
        rendimentos_bonificacao=_moeda(metricas.rendimentos_bonificacao),
        resultado_total=_moeda(metricas.resultado_total),
        total_investido=_moeda(metricas.total_investido),
        rentabilidade_total=_fino(metricas.rentabilidade_total),
    )


def _variacao(variacao: VariacaoDia | None) -> VariacaoDiaSaida | None:
    if variacao is None:
        return None
    return VariacaoDiaSaida(
        preco_atual=variacao.preco_atual,
        data_atual=variacao.data_atual,
        preco_anterior=variacao.preco_anterior,
        data_anterior=variacao.data_anterior,
        variacao=_fino(variacao.variacao),
        variacao_brl=_moeda_opcional(variacao.variacao_brl),
    )


def _posicao(item: PosicaoPortfolio) -> PosicaoSaida:
    posicao, avaliacao = item.posicao, item.posicao.avaliacao
    return PosicaoSaida(
        ativo_id=posicao.ativo_id,
        nome=item.ativo.nome,
        simbolo=item.ativo.simbolo,
        tipo=posicao.tipo_ativo,
        moeda=posicao.moeda,
        instituicao_id=posicao.instituicao_id,
        quantidade=_fino(posicao.quantidade),
        preco_medio=_fino(posicao.preco_medio),
        preco_atual=_fino(avaliacao.preco_unitario),
        valor=_moeda_opcional(avaliacao.valor),
        valor_brl=_moeda_opcional(avaliacao.valor_brl),
        origem=avaliacao.origem,
        data_preco=avaliacao.data_preco,
        defasado=avaliacao.defasado,
        aviso=avaliacao.aviso,
        erro=avaliacao.erro,
        participacao=_fino(item.participacao),
        metricas=_metricas(posicao.metricas),
        metricas_brl=_metricas(posicao.metricas_brl),
        variacao_dia=_variacao(item.variacao_dia),
    )


def _caixa(caixa: SaldoCaixa) -> CaixaSaida:
    return CaixaSaida(
        instituicao_id=caixa.instituicao_id,
        moeda=caixa.moeda,
        saldo=_moeda(caixa.saldo),
        saldo_brl=_moeda_opcional(caixa.saldo_brl),
        defasado=caixa.defasado,
        aviso=caixa.aviso,
        erro=caixa.erro,
    )


def _fatia(fatia: FatiaAlocacao) -> FatiaSaida:
    return FatiaSaida(
        grupo=fatia.grupo, valor=_moeda(fatia.valor), percentual=_fino(fatia.percentual) or 0
    )


def _portfolio(
    sessao: SessaoDep, hoje: date, data: date | None, instituicao_id: int | None
) -> Portfolio:
    return montar_portfolio(sessao, data or hoje, instituicao_id)


Data = Query(None, description="Data de referência (padrão: hoje).")
Instituicao = Query(None, description="Análise por Instituição (omita para a Análise Geral).")


# ---------------------------------------------------------------- rotas


@router.get(
    "/resumo",
    response_model=ResumoSaida,
    summary="Patrimônio, caixa, variação do dia e rentabilidade",
    responses=respostas(404),
)
def obter_resumo(
    sessao: SessaoDep,
    hoje: HojeDep,
    instituicao_id: int | None = Instituicao,
    data: date | None = Data,
) -> ResumoSaida:
    portfolio = _portfolio(sessao, hoje, data, instituicao_id)
    resumo = portfolio.resumo
    return ResumoSaida(
        data_ref=portfolio.data_ref,
        instituicao_id=instituicao_id,
        investimentos_brl=_moeda(resumo.investimentos_brl),
        caixa_brl=_moeda(resumo.caixa_brl),
        patrimonio_brl=_moeda(resumo.patrimonio_brl),
        completo=resumo.completo,
        variacao_dia_brl=_moeda(portfolio.variacao_dia_brl),
        variacao_dia=_fino(portfolio.variacao_dia),
        rentabilidade=_metricas(portfolio.rentabilidade),
        caixas=[_caixa(c) for c in resumo.caixas],
    )


@router.get(
    "/posicoes",
    response_model=list[PosicaoSaida],
    summary="Posições abertas por ativo (da maior para a menor)",
    responses=respostas(404),
)
def listar_posicoes(
    sessao: SessaoDep,
    hoje: HojeDep,
    instituicao_id: int | None = Instituicao,
    data: date | None = Data,
) -> list[PosicaoSaida]:
    portfolio = _portfolio(sessao, hoje, data, instituicao_id)
    return [_posicao(p) for p in portfolio.posicoes]


@router.get(
    "/maiores",
    response_model=list[PosicaoSaida],
    summary="Maiores posições em valor (BRL)",
    responses=respostas(404),
)
def listar_maiores(
    sessao: SessaoDep,
    hoje: HojeDep,
    limite: int = Query(5, ge=1, le=50),
    instituicao_id: int | None = Instituicao,
    data: date | None = Data,
) -> list[PosicaoSaida]:
    portfolio = _portfolio(sessao, hoje, data, instituicao_id)
    return [_posicao(p) for p in portfolio.posicoes[:limite]]


@router.get(
    "/alocacao",
    response_model=list[FatiaSaida],
    summary="Alocação por tipo de ativo (com a fatia caixa)",
    responses=respostas(404),
)
def obter_alocacao(
    sessao: SessaoDep,
    hoje: HojeDep,
    instituicao_id: int | None = Instituicao,
    data: date | None = Data,
) -> list[FatiaSaida]:
    portfolio = _portfolio(sessao, hoje, data, instituicao_id)
    return [_fatia(f) for f in portfolio.resumo.alocacao]


@router.get(
    "/variacao-dia",
    response_model=VariacaoCarteiraSaida,
    summary="Variação do dia (preço atual sobre o fechamento anterior)",
    responses=respostas(404),
)
def obter_variacao_dia(
    sessao: SessaoDep,
    hoje: HojeDep,
    instituicao_id: int | None = Instituicao,
    data: date | None = Data,
) -> VariacaoCarteiraSaida:
    portfolio = _portfolio(sessao, hoje, data, instituicao_id)
    ativos = [
        VariacaoAtivoSaida(ativo_id=p.ativo.id, nome=p.ativo.nome, variacao=variacao)
        for p in portfolio.posicoes
        if (variacao := _variacao(p.variacao_dia)) is not None
    ]
    return VariacaoCarteiraSaida(
        variacao_dia_brl=_moeda(portfolio.variacao_dia_brl),
        variacao_dia=_fino(portfolio.variacao_dia),
        ativos=ativos,
    )


@router.get(
    "/rentabilidade",
    response_model=RentabilidadeSaida,
    summary="Rentabilidade da carteira e de cada ativo (em BRL)",
    responses=respostas(404),
)
def obter_rentabilidade(
    sessao: SessaoDep,
    hoje: HojeDep,
    instituicao_id: int | None = Instituicao,
    data: date | None = Data,
) -> RentabilidadeSaida:
    portfolio = _portfolio(sessao, hoje, data, instituicao_id)
    nomes = {p.ativo.id: p.ativo.nome for p in portfolio.posicoes}
    return RentabilidadeSaida(
        carteira=_metricas(portfolio.rentabilidade),
        ativos=[
            RentabilidadeAtivo(
                ativo_id=p.ativo_id,
                nome=nomes.get(p.ativo_id, str(p.ativo_id)),
                metricas_brl=_metricas(p.metricas_brl),
            )
            for p in portfolio.resumo.posicoes
            if p.ativo_id in nomes
        ],
    )


@router.get(
    "/instituicoes",
    response_model=list[ResumoInstituicao],
    summary="Patrimônio de cada instituição (base da Análise por Instituição)",
    responses=respostas(),
)
def listar_resumo_instituicoes(
    sessao: SessaoDep, hoje: HojeDep, data: date | None = Data
) -> list[ResumoInstituicao]:
    carteira = avaliar_carteira(sessao, data or hoje)
    resultado = []
    for instituicao in listar_instituicoes(sessao):
        resumo = carteira.por_instituicao(instituicao.id)
        resultado.append(
            ResumoInstituicao(
                instituicao_id=instituicao.id,
                nome=instituicao.nome,
                investimentos_brl=_moeda(resumo.investimentos_brl),
                caixa_brl=_moeda(resumo.caixa_brl),
                patrimonio_brl=_moeda(resumo.patrimonio_brl),
                completo=resumo.completo,
            )
        )
    return resultado


@router.get(
    "/evolucao",
    response_model=EvolucaoSaida,
    summary="Evolução diária do patrimônio (até 1 ano)",
    description="Padrão: os últimos 365 dias até hoje, a partir dos fechamentos diários.",
    responses=respostas(404, 422),
)
def obter_evolucao(
    sessao: SessaoDep,
    hoje: HojeDep,
    inicio: date | None = None,
    fim: date | None = None,
    instituicao_id: int | None = Instituicao,
) -> EvolucaoSaida:
    final = fim or hoje
    inicial = inicio or final - timedelta(days=DIAS_MAXIMOS_EVOLUCAO - 1)
    exigir(inicial <= final, "inicio", "O início deve ser anterior ou igual ao fim.")
    exigir(
        (final - inicial).days < DIAS_MAXIMOS_EVOLUCAO,
        "inicio",
        "O período máximo da evolução é de 1 ano.",
    )
    if instituicao_id is not None:
        obter_instituicao(sessao, instituicao_id)
    serie = serie_patrimonio(sessao, inicial, final, instituicao_id=instituicao_id)
    return EvolucaoSaida(
        pontos=[
            PontoEvolucao(
                data=p.data,
                investimentos=_moeda(p.investimentos),
                caixa=_moeda(p.caixa),
                patrimonio=_moeda(p.patrimonio),
            )
            for p in serie.pontos
        ],
        avisos=list(serie.avisos),
    )
