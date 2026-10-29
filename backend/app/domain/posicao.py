"""Posição em cotas (ações, fundos, cripto...): preço médio ponderado e lucro realizado.

A posição é a dobra (fold) cronológica das operações de um ativo em **uma**
instituição. Regras (decididas com o dono, ver ``docs/CALCULOS.md``):

- **Compra:** custo += quantidade × preço + taxas. O preço médio (PM) é custo / quantidade,
  então taxas de compra sobem o PM.
- **Venda:** não altera o PM. Sai da posição o custo proporcional
  (custo × q / quantidade; a posição inteira quando q = quantidade). Lucro realizado =
  (quantidade × preço − taxas de venda) − custo que saiu. Venda maior que a posição
  é erro de domínio. Posição zerada e reaberta recomeça do zero.
- **Provento:** não altera PM nem custo; acumula o valor líquido (e o imposto retido) para
  as métricas. O dinheiro vai para a conta corrente da instituição.
- **Eventos corporativos** (proporção ``de:para``): desdobramento e grupamento multiplicam a
  quantidade por para/de com custo inalterado; bonificação acrescenta
  quantidade × (para − de)/de ações, cujo custo atribuído (custo unitário × novas) soma ao
  custo (regra da Receita) e é registrado como rendimento em ações.

Multimoeda: cada valor é acumulado na moeda do ativo e em BRL (usando o câmbio da
operação), então o custo em BRL fica fixo no câmbio de cada compra.

Ordem: por data; no mesmo dia, eventos corporativos antes das transações (a data do
evento é a data "ex") e, entre transações, a ordem de registro (``ordem``).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from app.domain.enums import TipoEvento
from app.domain.erros import PosicaoInsuficienteError, exigir
from app.domain.numeros import UM, ZERO, dec, dividir, formatar_numero
from app.domain.tempo import formatar_data


@dataclass(frozen=True)
class ValoresPosicao:
    """Valores acumulados de uma posição em uma moeda."""

    custo: Decimal = ZERO  # custo da posição restante
    total_investido: Decimal = ZERO  # soma do custo de todas as compras/aportes
    lucro_realizado: Decimal = ZERO
    proventos: Decimal = ZERO  # líquidos
    impostos_retidos: Decimal = ZERO
    rendimentos_bonificacao: Decimal = ZERO  # custo atribuído às ações bonificadas

    def __add__(self, outro: "ValoresPosicao") -> "ValoresPosicao":
        return ValoresPosicao(
            custo=self.custo + outro.custo,
            total_investido=self.total_investido + outro.total_investido,
            lucro_realizado=self.lucro_realizado + outro.lucro_realizado,
            proventos=self.proventos + outro.proventos,
            impostos_retidos=self.impostos_retidos + outro.impostos_retidos,
            rendimentos_bonificacao=self.rendimentos_bonificacao + outro.rendimentos_bonificacao,
        )


@dataclass(frozen=True)
class EstadoPosicao:
    quantidade: Decimal = ZERO
    moeda: ValoresPosicao = field(default_factory=ValoresPosicao)  # moeda do ativo
    brl: ValoresPosicao = field(default_factory=ValoresPosicao)

    @property
    def zerada(self) -> bool:
        return self.quantidade == ZERO

    @property
    def preco_medio(self) -> Decimal | None:
        return None if self.zerada else dividir(self.moeda.custo, self.quantidade)

    @property
    def preco_medio_brl(self) -> Decimal | None:
        return None if self.zerada else dividir(self.brl.custo, self.quantidade)


@dataclass(frozen=True)
class Compra:
    data: date
    quantidade: Decimal
    preco_unitario: Decimal
    taxas: Decimal = ZERO
    cambio: Decimal = UM  # BRL por unidade da moeda do ativo
    ordem: int = 0

    def __post_init__(self) -> None:
        _validar_negociacao(self.quantidade, self.preco_unitario, self.taxas, self.cambio)

    @property
    def custo_total(self) -> Decimal:
        return self.quantidade * self.preco_unitario + self.taxas


@dataclass(frozen=True)
class Venda:
    data: date
    quantidade: Decimal
    preco_unitario: Decimal
    taxas: Decimal = ZERO
    cambio: Decimal = UM
    ordem: int = 0

    def __post_init__(self) -> None:
        _validar_negociacao(self.quantidade, self.preco_unitario, self.taxas, self.cambio)
        exigir(
            self.taxas <= self.quantidade * self.preco_unitario,
            "taxas",
            "As taxas não podem ser maiores que o valor da venda.",
        )

    @property
    def receita_liquida(self) -> Decimal:
        return self.quantidade * self.preco_unitario - self.taxas


@dataclass(frozen=True)
class Provento:
    data: date
    valor_liquido: Decimal
    imposto_retido: Decimal = ZERO
    cambio: Decimal = UM
    ordem: int = 0

    def __post_init__(self) -> None:
        exigir(self.valor_liquido > ZERO, "valor", "O valor do provento deve ser maior que zero.")
        exigir(
            self.imposto_retido >= ZERO, "imposto_retido", "O imposto retido não pode ser negativo."
        )
        exigir(self.cambio > ZERO, "cambio", "O câmbio deve ser maior que zero.")


@dataclass(frozen=True)
class EventoCorporativo:
    data: date  # data "ex"
    tipo: TipoEvento
    proporcao_de: int
    proporcao_para: int
    custo_unitario: Decimal = ZERO  # só bonificação, na moeda do ativo
    cambio: Decimal = UM
    ordem: int = 0

    def __post_init__(self) -> None:
        validar_proporcao_evento(
            self.tipo, self.proporcao_de, self.proporcao_para, self.custo_unitario
        )
        exigir(self.cambio > ZERO, "cambio", "O câmbio deve ser maior que zero.")

    @property
    def fator(self) -> Decimal:
        return dividir(dec(self.proporcao_para), dec(self.proporcao_de))


OperacaoCotas = Compra | Venda | Provento | EventoCorporativo


def validar_proporcao_evento(
    tipo: TipoEvento, proporcao_de: int, proporcao_para: int, custo_unitario: Decimal
) -> None:
    """Regras de proporção por tipo de evento (compartilhadas com o service)."""
    exigir(
        proporcao_de > 0 and proporcao_para > 0,
        "proporcao",
        "A proporção do evento deve ter números inteiros maiores que zero.",
    )
    if tipo is TipoEvento.GRUPAMENTO:
        exigir(
            proporcao_para < proporcao_de,
            "proporcao",
            "No grupamento, a quantidade final deve ser menor (ex.: 10:1).",
        )
    else:
        exigir(
            proporcao_para > proporcao_de,
            "proporcao",
            "No desdobramento e na bonificação, a quantidade final deve ser maior "
            "(ex.: 1:2 ou 10:11).",
        )
    if tipo is TipoEvento.BONIFICACAO:
        exigir(
            custo_unitario >= ZERO,
            "custo_unitario",
            "O custo atribuído à bonificação não pode ser negativo.",
        )
    else:
        exigir(
            custo_unitario == ZERO,
            "custo_unitario",
            "Custo atribuído só se aplica à bonificação.",
        )


def _validar_negociacao(
    quantidade: Decimal, preco_unitario: Decimal, taxas: Decimal, cambio: Decimal
) -> None:
    exigir(quantidade > ZERO, "quantidade", "A quantidade deve ser maior que zero.")
    exigir(preco_unitario >= ZERO, "preco_unitario", "O preço unitário não pode ser negativo.")
    exigir(taxas >= ZERO, "taxas", "As taxas não podem ser negativas.")
    exigir(cambio > ZERO, "cambio", "O câmbio deve ser maior que zero.")


def chave_ordenacao(operacao: OperacaoCotas) -> tuple[date, int, int]:
    prioridade = 0 if isinstance(operacao, EventoCorporativo) else 1
    return (operacao.data, prioridade, operacao.ordem)


def aplicar_operacao(estado: EstadoPosicao, operacao: OperacaoCotas) -> EstadoPosicao:
    """Aplica uma operação e devolve o novo estado (função pura)."""
    if isinstance(operacao, Compra):
        return _aplicar_compra(estado, operacao)
    if isinstance(operacao, Venda):
        return _aplicar_venda(estado, operacao)
    if isinstance(operacao, Provento):
        return _aplicar_provento(estado, operacao)
    return _aplicar_evento(estado, operacao)


def aplicar_operacoes(
    operacoes: Iterable[OperacaoCotas], estado: EstadoPosicao | None = None
) -> EstadoPosicao:
    """Dobra todas as operações em ordem cronológica a partir de ``estado``."""
    atual = estado or EstadoPosicao()
    for operacao in sorted(operacoes, key=chave_ordenacao):
        atual = aplicar_operacao(atual, operacao)
    return atual


def historico_posicao(operacoes: Iterable[OperacaoCotas]) -> list[tuple[date, EstadoPosicao]]:
    """Estado ao fim de cada dia que teve operação, em ordem de data."""
    historico: list[tuple[date, EstadoPosicao]] = []
    atual = EstadoPosicao()
    for operacao in sorted(operacoes, key=chave_ordenacao):
        atual = aplicar_operacao(atual, operacao)
        if historico and historico[-1][0] == operacao.data:
            historico[-1] = (operacao.data, atual)
        else:
            historico.append((operacao.data, atual))
    return historico


def _aplicar_compra(estado: EstadoPosicao, compra: Compra) -> EstadoPosicao:
    custo = compra.custo_total
    custo_brl = custo * compra.cambio
    return EstadoPosicao(
        quantidade=estado.quantidade + compra.quantidade,
        moeda=replace(
            estado.moeda,
            custo=estado.moeda.custo + custo,
            total_investido=estado.moeda.total_investido + custo,
        ),
        brl=replace(
            estado.brl,
            custo=estado.brl.custo + custo_brl,
            total_investido=estado.brl.total_investido + custo_brl,
        ),
    )


def _aplicar_venda(estado: EstadoPosicao, venda: Venda) -> EstadoPosicao:
    if venda.quantidade > estado.quantidade:
        raise PosicaoInsuficienteError(
            f"Venda de {formatar_numero(venda.quantidade)} maior que a posição disponível de "
            f"{formatar_numero(estado.quantidade)} em {formatar_data(venda.data)}."
        )
    if venda.quantidade == estado.quantidade:
        custo_saida, custo_saida_brl = estado.moeda.custo, estado.brl.custo
    else:
        custo_saida = dividir(estado.moeda.custo * venda.quantidade, estado.quantidade)
        custo_saida_brl = dividir(estado.brl.custo * venda.quantidade, estado.quantidade)
    receita = venda.receita_liquida
    return EstadoPosicao(
        quantidade=estado.quantidade - venda.quantidade,
        moeda=replace(
            estado.moeda,
            custo=estado.moeda.custo - custo_saida,
            lucro_realizado=estado.moeda.lucro_realizado + receita - custo_saida,
        ),
        brl=replace(
            estado.brl,
            custo=estado.brl.custo - custo_saida_brl,
            lucro_realizado=estado.brl.lucro_realizado + receita * venda.cambio - custo_saida_brl,
        ),
    )


def _aplicar_provento(estado: EstadoPosicao, provento: Provento) -> EstadoPosicao:
    return replace(
        estado,
        moeda=replace(
            estado.moeda,
            proventos=estado.moeda.proventos + provento.valor_liquido,
            impostos_retidos=estado.moeda.impostos_retidos + provento.imposto_retido,
        ),
        brl=replace(
            estado.brl,
            proventos=estado.brl.proventos + provento.valor_liquido * provento.cambio,
            impostos_retidos=estado.brl.impostos_retidos
            + provento.imposto_retido * provento.cambio,
        ),
    )


def _aplicar_evento(estado: EstadoPosicao, evento: EventoCorporativo) -> EstadoPosicao:
    if estado.zerada:
        return estado
    if evento.tipo is not TipoEvento.BONIFICACAO:
        # Desdobramento/grupamento: só a quantidade muda; o custo total fica igual.
        return replace(estado, quantidade=estado.quantidade * evento.fator)
    novas = dividir(
        estado.quantidade * (evento.proporcao_para - evento.proporcao_de), dec(evento.proporcao_de)
    )
    custo_novas = novas * evento.custo_unitario
    custo_novas_brl = custo_novas * evento.cambio
    return EstadoPosicao(
        quantidade=estado.quantidade + novas,
        moeda=replace(
            estado.moeda,
            custo=estado.moeda.custo + custo_novas,
            rendimentos_bonificacao=estado.moeda.rendimentos_bonificacao + custo_novas,
        ),
        brl=replace(
            estado.brl,
            custo=estado.brl.custo + custo_novas_brl,
            rendimentos_bonificacao=estado.brl.rendimentos_bonificacao + custo_novas_brl,
        ),
    )
