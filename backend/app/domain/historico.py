"""Histórico de operações: resultado por venda/resgate, situação e totais do filtro.

Regras (decididas com o dono na Parte 4, ver ``docs/CALCULOS.md``):

- **Resultado da operação** = lucro realizado **daquela** venda ou resgate, pela mesma
  regra do preço médio de ``domain.posicao`` / ``domain.montante``: é a diferença do
  ``lucro_realizado`` acumulado da posição antes e depois da operação. Por isso a soma
  dos resultados de uma posição é exatamente o lucro realizado dela. Vem na moeda do
  ativo (``resultado``) e em BRL (``resultado_brl``, que inclui a variação do câmbio).
- **Valor total** = o que saiu ou entrou no caixa (o movimento automático da conta):
  compra = qtd × preço + taxas, venda = qtd × preço − taxas (ambos a centavos), aporte e
  resgate = valor, provento = valor líquido. Em BRL, multiplicado pelo câmbio da operação.
- **Taxas** e **imposto retido** em BRL pelo câmbio da operação. O cartão "Taxas pagas"
  soma só taxas; o IR retido dos proventos é um total à parte (opção A do dono).
- **Situação**: uma posição (ativo + instituição) está *aberta* enquanto tem quantidade
  (cotas) ou lotes (montante); um ativo está aberto se qualquer posição dele estiver.

Funções puras: sem banco, sem relógio.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.conta_corrente import movimento_da_transacao
from app.domain.enums import TipoTransacao
from app.domain.montante import (
    EstadoMontante,
    FatorAcumulado,
    OperacaoMontante,
    Resgate,
    aplicar_operacao_montante,
)
from app.domain.montante import chave_ordenacao as chave_montante
from app.domain.numeros import ZERO
from app.domain.posicao import (
    EstadoPosicao,
    OperacaoCotas,
    Venda,
    aplicar_operacao,
    chave_ordenacao,
)
from app.domain.tempo import primeiro_dia_do_mes, somar_meses

COMPRAS = frozenset({TipoTransacao.COMPRA, TipoTransacao.APORTE})
VENDAS = frozenset({TipoTransacao.VENDA, TipoTransacao.RESGATE})


class SituacaoPosicao(StrEnum):
    ABERTA = "aberta"  # ainda na carteira
    ENCERRADA = "encerrada"  # posição zerada


@dataclass(frozen=True)
class ResultadoOperacao:
    """Lucro (positivo) ou prejuízo (negativo) realizado numa venda/resgate."""

    resultado: Decimal  # moeda do ativo
    resultado_brl: Decimal


@dataclass(frozen=True)
class AnalisePosicao:
    """Resultado de cada venda/resgate (chave = id da transação) e a situação final."""

    resultados: Mapping[int, ResultadoOperacao]
    situacao: SituacaoPosicao


def analisar_cotas(operacoes: Iterable[OperacaoCotas]) -> AnalisePosicao:
    """Dobra as operações de uma posição em cotas guardando o lucro de cada venda.

    Ex.: 100 a R$ 10 + 100 a R$ 12 (PM 11); vende 50 a R$ 15 com R$ 5 de taxa →
    resultado = 750 − 5 − 550 = +195. A chave é a ``ordem`` (id da transação).
    """
    estado = EstadoPosicao()
    resultados: dict[int, ResultadoOperacao] = {}
    for operacao in sorted(operacoes, key=chave_ordenacao):
        novo = aplicar_operacao(estado, operacao)
        if isinstance(operacao, Venda):
            resultados[operacao.ordem] = ResultadoOperacao(
                resultado=novo.moeda.lucro_realizado - estado.moeda.lucro_realizado,
                resultado_brl=novo.brl.lucro_realizado - estado.brl.lucro_realizado,
            )
        estado = novo
    situacao = SituacaoPosicao.ENCERRADA if estado.zerada else SituacaoPosicao.ABERTA
    return AnalisePosicao(resultados, situacao)


def analisar_montante(
    operacoes: Iterable[OperacaoMontante], fator: FatorAcumulado
) -> AnalisePosicao:
    """Mesmo que ``analisar_cotas`` para renda fixa/poupança (sempre em BRL).

    Ex.: aporte de R$ 1.000 que rendeu até R$ 1.100; resgate de R$ 550 (metade do saldo)
    tira metade do custo (R$ 500) → resultado = 550 − 500 = +50.
    """
    estado = EstadoMontante()
    resultados: dict[int, ResultadoOperacao] = {}
    for operacao in sorted(operacoes, key=chave_montante):
        novo = aplicar_operacao_montante(estado, operacao, fator)
        if isinstance(operacao, Resgate):
            lucro = novo.valores.lucro_realizado - estado.valores.lucro_realizado
            resultados[operacao.ordem] = ResultadoOperacao(lucro, lucro)
        estado = novo
    situacao = SituacaoPosicao.ENCERRADA if estado.zerada else SituacaoPosicao.ABERTA
    return AnalisePosicao(resultados, situacao)


def situacao_do_ativo(situacoes: Iterable[SituacaoPosicao]) -> SituacaoPosicao:
    """Aberto se qualquer posição (instituição) ainda estiver aberta."""
    return (
        SituacaoPosicao.ABERTA
        if any(s is SituacaoPosicao.ABERTA for s in situacoes)
        else SituacaoPosicao.ENCERRADA
    )


@dataclass(frozen=True)
class OperacaoHistorico:
    """Uma transação vista pelo histórico (valores na moeda do ativo + câmbio)."""

    id: int
    data: date
    tipo: TipoTransacao
    ativo_id: int
    instituicao_id: int
    cambio: Decimal
    valor_total: Decimal  # movimento de caixa na moeda do ativo
    taxas: Decimal = ZERO
    imposto_retido: Decimal = ZERO
    resultado: ResultadoOperacao | None = None  # só venda/resgate

    @property
    def valor_total_brl(self) -> Decimal:
        return self.valor_total * self.cambio

    @property
    def taxas_brl(self) -> Decimal:
        return self.taxas * self.cambio

    @property
    def imposto_retido_brl(self) -> Decimal:
        return self.imposto_retido * self.cambio

    @property
    def tem_custos(self) -> bool:
        return self.taxas > ZERO or self.imposto_retido > ZERO

    @property
    def prejuizo(self) -> bool:
        return self.resultado is not None and self.resultado.resultado_brl < ZERO


def valor_total(
    tipo: TipoTransacao,
    *,
    quantidade: Decimal | None,
    preco_unitario: Decimal | None,
    taxas: Decimal,
    valor: Decimal | None,
) -> Decimal:
    """Valor que saiu/entrou no caixa, igual ao movimento automático da transação."""
    return movimento_da_transacao(
        tipo, quantidade=quantidade, preco_unitario=preco_unitario, taxas=taxas, valor=valor
    )[1]


@dataclass(frozen=True)
class TotaisHistorico:
    """Totais em BRL (sem arredondar; a API arredonda na apresentação)."""

    operacoes: int = 0
    total_comprado: Decimal = ZERO  # compras + aportes
    total_vendido: Decimal = ZERO  # vendas + resgates
    lucro_realizado: Decimal = ZERO  # soma dos resultados das vendas/resgates
    proventos_liquidos: Decimal = ZERO
    impostos_retidos: Decimal = ZERO  # IR retido nos proventos
    taxas: Decimal = ZERO
    operacoes_com_taxas: int = 0


def totalizar(operacoes: Iterable[OperacaoHistorico]) -> TotaisHistorico:
    contagem = com_taxas = 0
    comprado = vendido = lucro = proventos = impostos = taxas = ZERO
    for op in operacoes:
        contagem += 1
        if op.tipo in COMPRAS:
            comprado += op.valor_total_brl
        elif op.tipo in VENDAS:
            vendido += op.valor_total_brl
            if op.resultado is not None:
                lucro += op.resultado.resultado_brl
        else:
            proventos += op.valor_total_brl
            impostos += op.imposto_retido_brl
        if op.taxas > ZERO:
            com_taxas += 1
            taxas += op.taxas_brl
    return TotaisHistorico(
        operacoes=contagem,
        total_comprado=comprado,
        total_vendido=vendido,
        lucro_realizado=lucro,
        proventos_liquidos=proventos,
        impostos_retidos=impostos,
        taxas=taxas,
        operacoes_com_taxas=com_taxas,
    )


@dataclass(frozen=True)
class PontoMensal:
    mes: date  # dia 1º do mês
    compras: Decimal = ZERO  # compras + aportes (BRL)
    vendas: Decimal = ZERO  # vendas + resgates (BRL)
    proventos: Decimal = ZERO  # líquidos (BRL)


def meses_entre(inicio: date, fim: date) -> list[date]:
    """Dia 1º de cada mês de ``inicio`` a ``fim`` (inclusive); vazio se fim < inicio."""
    meses: list[date] = []
    atual, ultimo = primeiro_dia_do_mes(inicio), primeiro_dia_do_mes(fim)
    while atual <= ultimo:
        meses.append(atual)
        atual = somar_meses(atual, 1)
    return meses


def serie_mensal(
    operacoes: Iterable[OperacaoHistorico], inicio: date, fim: date
) -> list[PontoMensal]:
    """Uma barra por mês do período, inclusive os meses sem operação (valores zero)."""
    compras: dict[date, Decimal] = defaultdict(lambda: ZERO)
    vendas: dict[date, Decimal] = defaultdict(lambda: ZERO)
    proventos: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for op in operacoes:
        mes = primeiro_dia_do_mes(op.data)
        destino = compras if op.tipo in COMPRAS else vendas if op.tipo in VENDAS else proventos
        destino[mes] += op.valor_total_brl
    return [
        PontoMensal(mes, compras[mes], vendas[mes], proventos[mes])
        for mes in meses_entre(inicio, fim)
    ]


@dataclass(frozen=True)
class GrupoInstituicao:
    instituicao_id: int
    situacao: SituacaoPosicao
    totais: TotaisHistorico


@dataclass(frozen=True)
class GrupoAtivo:
    ativo_id: int
    situacao: SituacaoPosicao
    totais: TotaisHistorico
    instituicoes: tuple[GrupoInstituicao, ...]


def agrupar_por_ativo(
    operacoes: Iterable[OperacaoHistorico],
    situacao_posicao: Callable[[int, int], SituacaoPosicao],
    situacao_ativo: Callable[[int], SituacaoPosicao],
) -> list[GrupoAtivo]:
    """Totais por ativo e, dentro dele, por instituição (visão "Por ativo" do histórico).

    A situação de cada nível vem de quem chama: com filtro de instituição, a do ativo é a
    da própria posição; sem filtro, a do ativo agregado (todas as instituições).
    A ordem dos ativos e das instituições é a de primeira aparição em ``operacoes``.
    """
    por_ativo: dict[int, dict[int, list[OperacaoHistorico]]] = {}
    for op in operacoes:
        por_ativo.setdefault(op.ativo_id, {}).setdefault(op.instituicao_id, []).append(op)
    grupos: list[GrupoAtivo] = []
    for ativo_id, por_instituicao in por_ativo.items():
        instituicoes = tuple(
            GrupoInstituicao(
                instituicao_id, situacao_posicao(ativo_id, instituicao_id), totalizar(ops)
            )
            for instituicao_id, ops in por_instituicao.items()
        )
        todas = [op for ops in por_instituicao.values() for op in ops]
        grupos.append(
            GrupoAtivo(ativo_id, situacao_ativo(ativo_id), totalizar(todas), instituicoes)
        )
    return grupos
