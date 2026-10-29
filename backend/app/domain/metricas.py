"""Métricas de resultado de uma posição (decididas com o dono, opção A).

- Lucro não realizado = valor atual − custo da posição restante.
- Valorização = lucro não realizado / custo (só preço; ``None`` se não há custo).
- Resultado total = lucro não realizado + lucro realizado + proventos líquidos
  + rendimentos de bonificação (custo atribuído às ações bonificadas, que entrou no custo
  pela regra da Receita e por isso precisa ser reconhecido como rendimento aqui).
- Rentabilidade total = resultado total / total investido (soma do custo de todas as
  compras/aportes; ``None`` se nada foi investido).

Exemplo: compra 100 @ 10 (1.000), provento 50, cotação 11 → valorização 10% e
rentabilidade total (1.100 − 1.000 + 0 + 50) / 1.000 = 15%.
Todas as razões ficam sem arredondar (use ``numeros.percentual`` na apresentação).
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.numeros import ZERO, dividir
from app.domain.posicao import ValoresPosicao


@dataclass(frozen=True)
class Metricas:
    valor_atual: Decimal
    custo: Decimal
    lucro_nao_realizado: Decimal
    valorizacao: Decimal | None
    lucro_realizado: Decimal
    proventos: Decimal
    rendimentos_bonificacao: Decimal
    resultado_total: Decimal
    total_investido: Decimal
    rentabilidade_total: Decimal | None


def calcular_metricas(valor_atual: Decimal, valores: ValoresPosicao) -> Metricas:
    lucro_nao_realizado = valor_atual - valores.custo
    resultado = (
        lucro_nao_realizado
        + valores.lucro_realizado
        + valores.proventos
        + valores.rendimentos_bonificacao
    )
    return Metricas(
        valor_atual=valor_atual,
        custo=valores.custo,
        lucro_nao_realizado=lucro_nao_realizado,
        valorizacao=dividir(lucro_nao_realizado, valores.custo) if valores.custo > ZERO else None,
        lucro_realizado=valores.lucro_realizado,
        proventos=valores.proventos,
        rendimentos_bonificacao=valores.rendimentos_bonificacao,
        resultado_total=resultado,
        total_investido=valores.total_investido,
        rentabilidade_total=(
            dividir(resultado, valores.total_investido) if valores.total_investido > ZERO else None
        ),
    )
