"""Visões do portfólio para a API: resumo, posições, variação do dia e rentabilidade.

Tudo em duas análises: **Geral** (cada ativo consolidado entre as instituições) e **por
Instituição** (só as posições e o caixa daquela instituição).

- **Variação do dia** (ativos cotados) = preço atual em relação ao fechamento do dia
  anterior (o último preço com data anterior à do preço atual). Em BRL, para a posição:
  quantidade × (atual − anterior) × câmbio vigente. A variação da carteira é a soma das
  posições sobre o valor delas no fechamento anterior.
- **Rentabilidade da carteira**: as métricas da posição (``domain/metricas``) somando, em
  BRL, os valores de todas as posições avaliadas (inclusive as zeradas, que guardam lucro
  realizado e proventos).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.carteira import PosicaoAvaliada, ResumoCarteira
from app.domain.metricas import Metricas, calcular_metricas
from app.domain.numeros import ZERO, dividir
from app.domain.posicao import ValoresPosicao
from app.domain.precos import variacao
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.services.cadastros import obter_instituicao
from app.services.carteira import CarteiraAvaliada, avaliar_carteira
from app.services.mercado import carregar_precos


@dataclass(frozen=True)
class VariacaoDia:
    preco_atual: Decimal
    data_atual: date
    preco_anterior: Decimal
    data_anterior: date
    variacao: Decimal | None  # razão (0,01 = 1%)
    variacao_brl: Decimal | None  # efeito na posição, em BRL


@dataclass(frozen=True)
class PosicaoPortfolio:
    posicao: PosicaoAvaliada
    ativo: m.Ativo
    participacao: Decimal | None  # razão do patrimônio
    variacao_dia: VariacaoDia | None


@dataclass(frozen=True)
class Portfolio:
    data_ref: date
    instituicao_id: int | None
    resumo: ResumoCarteira
    posicoes: tuple[PosicaoPortfolio, ...]  # abertas, da maior para a menor (BRL)
    variacao_dia_brl: Decimal
    variacao_dia: Decimal | None
    rentabilidade: Metricas | None


def _variacao_dia(
    sessao: Session, posicao: PosicaoAvaliada, data_ref: date, cambio: Decimal | None
) -> VariacaoDia | None:
    if posicao.quantidade is None:  # renda fixa/poupança: sem cotação
        return None
    precos = carregar_precos(sessao, posicao.ativo_id)
    atual = precos.ultimo_ate(data_ref)
    if atual is None:
        return None
    anterior = precos.anterior_a(atual.data)
    if anterior is None:
        return None
    variacao_brl = (
        posicao.quantidade * (atual.valor - anterior.valor) * cambio if cambio is not None else None
    )
    return VariacaoDia(
        preco_atual=atual.valor,
        data_atual=atual.data,
        preco_anterior=anterior.valor,
        data_anterior=anterior.data,
        variacao=variacao(atual.valor, anterior.valor),
        variacao_brl=variacao_brl,
    )


def _cambio(posicao: PosicaoAvaliada) -> Decimal | None:
    """Câmbio implícito da avaliação (valor em BRL / valor na moeda do ativo)."""
    valor, valor_brl = posicao.avaliacao.valor, posicao.avaliacao.valor_brl
    if valor is None or valor_brl is None or valor == ZERO:
        return None
    return dividir(valor_brl, valor)


def _rentabilidade(posicoes: tuple[PosicaoAvaliada, ...]) -> Metricas | None:
    avaliadas = [p for p in posicoes if p.avaliacao.valor_brl is not None]
    if not avaliadas:
        return None
    valor = sum((p.avaliacao.valor_brl or ZERO for p in avaliadas), ZERO)
    valores = sum((p.valores_brl for p in avaliadas), ValoresPosicao())
    return calcular_metricas(valor, valores)


def montar_portfolio(
    sessao: Session,
    data_ref: date,
    instituicao_id: int | None = None,
    *,
    carteira: CarteiraAvaliada | None = None,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> Portfolio:
    if instituicao_id is not None:
        obter_instituicao(sessao, instituicao_id)
    carteira = carteira or avaliar_carteira(sessao, data_ref, registro)
    resumo = (
        carteira.geral() if instituicao_id is None else carteira.por_instituicao(instituicao_id)
    )
    ativos = {a.id: a for a in RepositorioAtivos(sessao).listar()}
    patrimonio = resumo.patrimonio_brl
    posicoes: list[PosicaoPortfolio] = []
    variacao_total = ZERO
    base_variacao = ZERO
    for posicao in resumo.posicoes:
        if not posicao.aberta:
            continue
        variacao_dia = _variacao_dia(sessao, posicao, data_ref, _cambio(posicao))
        if variacao_dia is not None and variacao_dia.variacao_brl is not None:
            variacao_total += variacao_dia.variacao_brl
            base_variacao += (posicao.avaliacao.valor_brl or ZERO) - variacao_dia.variacao_brl
        valor_brl = posicao.avaliacao.valor_brl
        participacao = (
            dividir(valor_brl, patrimonio) if valor_brl is not None and patrimonio > ZERO else None
        )
        posicoes.append(
            PosicaoPortfolio(posicao, ativos[posicao.ativo_id], participacao, variacao_dia)
        )
    posicoes.sort(key=lambda p: (-(p.posicao.avaliacao.valor_brl or ZERO), p.ativo.nome))
    return Portfolio(
        data_ref=data_ref,
        instituicao_id=instituicao_id,
        resumo=resumo,
        posicoes=tuple(posicoes),
        variacao_dia_brl=variacao_total,
        variacao_dia=dividir(variacao_total, base_variacao) if base_variacao > ZERO else None,
        rentabilidade=_rentabilidade(resumo.posicoes),
    )
