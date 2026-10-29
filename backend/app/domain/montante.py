"""Posição por montante (renda fixa, poupança): aportes e resgates em R$.

Cada aporte vira um **lote** que rende a partir da própria data, segundo um
``FatorAcumulado(inicio, fim)`` fornecido pelo tipo de ativo (pré, % CDI, IPCA+,
poupança). O valor do investimento numa data é a soma de ``principal × fator`` dos lotes.

Resgate (decidido com o dono): reduz o principal **proporcionalmente ao saldo**.
Com saldo bruto S na data e resgate X, a fração resgatada é f = X / S; cada lote
fica com principal × (1 − f) e sai f do custo. Lucro realizado = X − f × custo.
Resgatar exatamente o saldo exibido (S arredondado a centavos) zera a posição.
Resgate maior que o saldo é erro de domínio.

Montante é sempre em BRL e não aceita taxas (renda fixa e poupança não as têm).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.erros import PosicaoInsuficienteError, exigir
from app.domain.numeros import UM, ZERO, arredondar_moeda, dividir, formatar_numero
from app.domain.posicao import ValoresPosicao
from app.domain.tempo import formatar_data

FatorAcumulado = Callable[[date, date], Decimal]
"""Fator de rendimento de ``inicio`` até ``fim`` (1 quando ``fim <= inicio``)."""


@dataclass(frozen=True)
class Aporte:
    data: date
    valor: Decimal
    ordem: int = 0

    def __post_init__(self) -> None:
        exigir(self.valor > ZERO, "valor", "O valor do aporte deve ser maior que zero.")


@dataclass(frozen=True)
class Resgate:
    data: date
    valor: Decimal
    ordem: int = 0

    def __post_init__(self) -> None:
        exigir(self.valor > ZERO, "valor", "O valor do resgate deve ser maior que zero.")


OperacaoMontante = Aporte | Resgate


@dataclass(frozen=True)
class Lote:
    data_inicio: date
    principal: Decimal  # principal original já reduzido pelos resgates proporcionais


@dataclass(frozen=True)
class EstadoMontante:
    lotes: tuple[Lote, ...] = ()
    valores: ValoresPosicao = field(default_factory=ValoresPosicao)

    @property
    def zerada(self) -> bool:
        return not self.lotes

    def valor_em(self, dia: date, fator: FatorAcumulado) -> Decimal:
        """Saldo bruto estimado em ``dia`` (sem arredondar)."""
        return sum((lote.principal * fator(lote.data_inicio, dia) for lote in self.lotes), ZERO)


def chave_ordenacao(operacao: OperacaoMontante) -> tuple[date, int]:
    return (operacao.data, operacao.ordem)


def aplicar_operacao_montante(
    estado: EstadoMontante, operacao: OperacaoMontante, fator: FatorAcumulado
) -> EstadoMontante:
    if isinstance(operacao, Aporte):
        return EstadoMontante(
            lotes=(*estado.lotes, Lote(operacao.data, operacao.valor)),
            valores=ValoresPosicao(
                custo=estado.valores.custo + operacao.valor,
                total_investido=estado.valores.total_investido + operacao.valor,
                lucro_realizado=estado.valores.lucro_realizado,
            ),
        )
    return _aplicar_resgate(estado, operacao, fator)


def aplicar_operacoes_montante(
    operacoes: Iterable[OperacaoMontante], fator: FatorAcumulado
) -> EstadoMontante:
    estado = EstadoMontante()
    for operacao in sorted(operacoes, key=chave_ordenacao):
        estado = aplicar_operacao_montante(estado, operacao, fator)
    return estado


def _aplicar_resgate(
    estado: EstadoMontante, resgate: Resgate, fator: FatorAcumulado
) -> EstadoMontante:
    saldo = estado.valor_em(resgate.data, fator)
    saldo_exibido = arredondar_moeda(saldo)
    if saldo == ZERO or resgate.valor > saldo_exibido:
        raise PosicaoInsuficienteError(
            f"Resgate de R$ {formatar_numero(resgate.valor)} maior que o saldo estimado de "
            f"R$ {formatar_numero(saldo_exibido)} em {formatar_data(resgate.data)}."
        )
    fracao = UM if resgate.valor == saldo_exibido else dividir(resgate.valor, saldo)
    restante = UM - fracao
    custo_saida = estado.valores.custo if fracao == UM else estado.valores.custo * fracao
    lotes = (
        ()
        if fracao == UM
        else tuple(Lote(lote.data_inicio, lote.principal * restante) for lote in estado.lotes)
    )
    return EstadoMontante(
        lotes=lotes,
        valores=ValoresPosicao(
            custo=estado.valores.custo - custo_saida,
            total_investido=estado.valores.total_investido,
            lucro_realizado=estado.valores.lucro_realizado + resgate.valor - custo_saida,
        ),
    )
