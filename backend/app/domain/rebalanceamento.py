"""Rebalanceamento por metas de alocação: regras puras, determinísticas e sem banco nem rede.

O plano é **informativo**: o app nunca executa ordens. Nada aqui recomenda ativos por
conta própria; tudo sai das metas que o usuário definiu. Fórmulas e exemplos conferidos
à mão em ``docs/CALCULOS.md`` (seção Rebalanceamento).

Notação: T = valor atual das posições abertas (BRL, sem caixa); A = aporte; N = T + A;
``meta_i`` = meta da classe como razão (35% = 0,35); ``atual_i`` = valor atual da classe.

- **Desvio** da classe = % atual (sobre T) − meta, em pontos percentuais (p.p.), com
  2 casas. **Fora da banda** se |desvio| > tolerância. **Desvio total** = Σ |desvio| ÷ 2.
- **Só com aportes** (nunca vende): déficit_i = max(0, meta_i × N − atual_i). Se
  Σ déficits ≥ A, A é dividido na proporção dos déficits; senão, cada déficit é preenchido
  e a sobra (A − Σ déficits) é dividida pelas metas.
- **Completo** (compra e vende): diferença_i = meta_i × N − atual_i (positivo compra,
  negativo vende). Como Σ metas = 1, Σ diferenças = N − T = A.
- **Dentro da classe com pesos**: o mesmo algoritmo entre os ativos da classe, com o valor
  que a classe recebe no papel de A e os pesos no papel das metas (ativo sem peso = 0%).
- **Arredondamento**: cada sugestão em centavos (``ROUND_HALF_EVEN``); a diferença de
  centavos para fechar exatamente o total vai pelo **maior resto** (quem perdeu mais no
  arredondamento recebe o centavo; empate pela ordem de apresentação). Vale nos dois
  níveis: classes (fecha A) e ativos de uma classe (fecha a sugestão da classe).
- **Venda estimada** (modo completo, nível de ativo): quantidade ≈ venda ÷ preço atual
  (= venda × quantidade ÷ valor) e lucro estimado = venda − quantidade × preço médio
  (= venda × (valor − custo) ÷ valor), em BRL. O app não calcula IR.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.numeros import CEM, ZERO, arredondar, arredondar_moeda, casas_decimais, dividir

CENTAVO = Decimal("0.01")
TOLERANCIA_PADRAO_PP = 5
TOLERANCIA_MINIMA_PP = 1
TOLERANCIA_MAXIMA_PP = 20
CASAS_PP = 2


class ModoPlano(StrEnum):
    APORTES = "aportes"
    COMPLETO = "completo"


class AcaoSugerida(StrEnum):
    APORTAR = "aportar"
    VENDER = "vender"
    MANTER = "manter"


@dataclass(frozen=True)
class PosicaoPlano:
    """Uma posição aberta (Análise Geral) vista pelo rebalanceamento, em BRL."""

    ativo_id: int
    tipo_ativo: str
    valor: Decimal  # valor atual em BRL (zero se a posição não pôde ser avaliada)
    custo: Decimal  # custo da posição aberta em BRL
    quantidade: Decimal | None  # None para posições por montante (renda fixa, poupança)
    defasado: bool = False
    aviso: str | None = None


@dataclass(frozen=True)
class EntradaPlano:
    posicoes: tuple[PosicaoPlano, ...]
    metas_classe: Mapping[str, Decimal]  # tipo → % da carteira (0 a 100); vazio = sem metas
    pesos: Mapping[str, Mapping[int, Decimal]]  # tipo → ativo → % da classe (0 a 100)
    aporte: Decimal  # BRL, ≥ 0, no máximo 2 casas
    modo: ModoPlano
    tolerancia_pp: int


@dataclass(frozen=True)
class SugestaoAtivo:
    ativo_id: int
    valor_atual: Decimal
    peso: Decimal | None  # % da classe; None quando a classe não usa pesos
    sugestao: Decimal | None  # centavos; None quando a classe não usa pesos
    quantidade_estimada: Decimal | None  # só em vendas de ativo cotado
    lucro_estimado: Decimal | None  # só em vendas
    defasado: bool
    aviso: str | None


@dataclass(frozen=True)
class ClassePlano:
    tipo_ativo: str
    valor_atual: Decimal
    percentual_atual: Decimal  # % de T (exato)
    meta: Decimal | None  # % da carteira; None sem metas
    desvio_pp: Decimal | None  # 2 casas
    fora_da_banda: bool
    sugestao: Decimal | None  # centavos; None sem metas
    usa_pesos: bool
    ativos: tuple[SugestaoAtivo, ...]


@dataclass(frozen=True)
class Plano:
    tem_metas: bool
    total: Decimal  # T
    aporte: Decimal
    modo: ModoPlano
    tolerancia_pp: int
    desvio_total_pp: Decimal | None  # 2 casas
    classes_fora_da_banda: int
    classes: tuple[ClassePlano, ...]
    classes_com_pesos_invalidos: tuple[str, ...]  # pesos gravados que não somam 100%


# ---------------------------------------------------------------- funções básicas


def acao(sugestao: Decimal | None) -> AcaoSugerida:
    """Sugestão abaixo de R$ 0,01 (em módulo) vira "manter"."""
    if sugestao is None or abs(sugestao) < CENTAVO:
        return AcaoSugerida.MANTER
    return AcaoSugerida.APORTAR if sugestao > ZERO else AcaoSugerida.VENDER


def desvio_pp(percentual_atual: Decimal, meta: Decimal) -> Decimal:
    """Desvio em pontos percentuais, com 2 casas (28% atual − 25% meta = 3,00 p.p.)."""
    return arredondar(percentual_atual - meta, CASAS_PP)


def fora_da_banda(desvio: Decimal, tolerancia_pp: int) -> bool:
    return abs(desvio) > tolerancia_pp


def dividir_so_aportes(
    atuais: Sequence[Decimal], metas: Sequence[Decimal], aporte: Decimal
) -> list[Decimal]:
    """Divide o aporte sem vender (valores exatos, sem arredondar).

    ``metas`` em razão, somando 1. Ex.: atuais 42.000/28.000/15.000/9.000/4.000/2.000,
    metas 35/25/15/15/7/3% e A = 5.000 → déficits 0/0/750/6.750/3.350/1.150 (Σ 12.000 > A)
    → 0/0/312,50/2.812,50/1.395,83…/479,16….
    """
    if aporte <= ZERO:
        return [ZERO for _ in atuais]
    novo_total = sum(atuais, ZERO) + aporte
    deficits = [
        max(ZERO, meta * novo_total - atual) for atual, meta in zip(atuais, metas, strict=True)
    ]
    soma = sum(deficits, ZERO)
    if soma >= aporte:
        return [dividir(aporte * deficit, soma) for deficit in deficits]
    sobra = aporte - soma
    return [deficit + sobra * meta for deficit, meta in zip(deficits, metas, strict=True)]


def dividir_completo(
    atuais: Sequence[Decimal], metas: Sequence[Decimal], aporte: Decimal
) -> list[Decimal]:
    """Diferença para a meta (positivo compra, negativo vende); soma = ``aporte``."""
    novo_total = sum(atuais, ZERO) + aporte
    return [meta * novo_total - atual for atual, meta in zip(atuais, metas, strict=True)]


def arredondar_pelo_maior_resto(brutos: Sequence[Decimal], total: Decimal) -> list[Decimal]:
    """Centavos (``ROUND_HALF_EVEN``) com a diferença distribuída pelo maior resto.

    Ex.: 100,00 entre três partes iguais (33,333…) → 33,33 cada (Σ 99,99); o centavo que
    falta vai para quem perdeu mais no arredondamento; empatados, para o primeiro:
    33,34 / 33,33 / 33,33. Itens com valor bruto zero nunca recebem centavo.
    """
    if casas_decimais(total) > 2:
        raise ValueError("O total do arredondamento precisa ter no máximo 2 casas.")
    arredondados = [arredondar_moeda(bruto) for bruto in brutos]
    passos = int(dividir(total - sum(arredondados, ZERO), CENTAVO))
    if passos == 0:
        return arredondados
    sinal = 1 if passos > 0 else -1
    candidatos = [i for i, bruto in enumerate(brutos) if bruto != ZERO]
    if not candidatos:
        raise ValueError("Não há onde distribuir a diferença de centavos.")
    ordem = sorted(candidatos, key=lambda i: (-sinal * (brutos[i] - arredondados[i]), i))
    for passo in range(abs(passos)):
        indice = ordem[passo % len(ordem)]
        arredondados[indice] += sinal * CENTAVO
    return arredondados


def estimar_venda(
    venda: Decimal, valor: Decimal, custo: Decimal, quantidade: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    """Quantidade aproximada e lucro estimado de vender ``venda`` (BRL) da posição.

    Ex.: 100 cotas, valor 5.000 (preço 50), custo 4.000 (PM 40); vender 1.000 →
    quantidade 20 e lucro 1.000 − 20 × 40 = 200. Sem quantidade (renda fixa), só o lucro,
    pela proporção do custo no valor.
    """
    if venda <= ZERO or valor <= ZERO:
        return None, None
    quantidade_estimada = dividir(venda * quantidade, valor) if quantidade else None
    lucro = venda - dividir(venda * custo, valor)
    return quantidade_estimada, lucro


def aviso_cotacao(
    *, defasado: bool, erro: str | None, aviso: str | None, data_preco: date | None, hoje: date
) -> str | None:
    """Aviso curto da linha do ativo: sem avaliação, ou cotação de N dias atrás."""
    if erro:
        return f"Sem valor atual (ficou fora do cálculo): {erro}"
    if not defasado:
        return None
    if data_preco is not None and data_preco < hoje:
        dias = (hoje - data_preco).days
        return f"Cotação de {dias} dia{'s' if dias != 1 else ''} atrás."
    return aviso or "Cotação defasada."


# ---------------------------------------------------------------- plano


def _pesos_validos(pesos: Mapping[int, Decimal]) -> bool:
    return bool(pesos) and sum(pesos.values(), ZERO) == CEM


def _dividir(
    modo: ModoPlano, atuais: list[Decimal], metas: list[Decimal], total: Decimal
) -> list[Decimal]:
    if modo is ModoPlano.APORTES:
        brutos = dividir_so_aportes(atuais, metas, total)
    else:
        brutos = dividir_completo(atuais, metas, total)
    return arredondar_pelo_maior_resto(brutos, total)


def _ativos_da_classe(
    posicoes: list[PosicaoPlano],
    pesos: Mapping[int, Decimal],
    usa_pesos: bool,
    sugestao_classe: Decimal | None,
    modo: ModoPlano,
) -> tuple[SugestaoAtivo, ...]:
    por_id = {p.ativo_id: p for p in posicoes}
    ids = set(por_id) | (set(pesos) if usa_pesos else set())

    def peso(ativo_id: int) -> Decimal:
        return pesos.get(ativo_id, ZERO)

    def valor(ativo_id: int) -> Decimal:
        posicao = por_id.get(ativo_id)
        return posicao.valor if posicao else ZERO

    ordem = sorted(ids, key=lambda i: (-valor(i), -peso(i), i))
    sugestoes: list[Decimal | None] = [None for _ in ordem]
    if usa_pesos and sugestao_classe is not None:
        sugestoes = list(
            _dividir(
                modo,
                [valor(i) for i in ordem],
                [dividir(peso(i), CEM) for i in ordem],
                sugestao_classe,
            )
        )
    itens: list[SugestaoAtivo] = []
    for ativo_id, sugestao in zip(ordem, sugestoes, strict=True):
        posicao = por_id.get(ativo_id)
        quantidade = lucro = None
        if posicao is not None and sugestao is not None and sugestao < ZERO:
            quantidade, lucro = estimar_venda(
                -sugestao, posicao.valor, posicao.custo, posicao.quantidade
            )
        itens.append(
            SugestaoAtivo(
                ativo_id=ativo_id,
                valor_atual=valor(ativo_id),
                peso=peso(ativo_id) if usa_pesos else None,
                sugestao=sugestao,
                quantidade_estimada=quantidade,
                lucro_estimado=lucro,
                defasado=posicao.defasado if posicao else False,
                aviso=posicao.aviso if posicao else None,
            )
        )
    return tuple(itens)


def montar_plano(entrada: EntradaPlano) -> Plano:
    """Desvios por classe e a sugestão de cada classe (e de cada ativo, com pesos)."""
    if entrada.aporte < ZERO or casas_decimais(entrada.aporte) > 2:
        raise ValueError("O aporte deve ser maior ou igual a zero, com no máximo 2 casas.")
    tem_metas = bool(entrada.metas_classe)
    posicoes_por_tipo: dict[str, list[PosicaoPlano]] = defaultdict(list)
    for posicao in entrada.posicoes:
        posicoes_por_tipo[posicao.tipo_ativo].append(posicao)
    valores = {
        tipo: sum((p.valor for p in itens), ZERO) for tipo, itens in posicoes_por_tipo.items()
    }
    total = sum(valores.values(), ZERO)
    tipos = sorted(
        set(valores) | set(entrada.metas_classe),
        key=lambda t: (-valores.get(t, ZERO), -entrada.metas_classe.get(t, ZERO), t),
    )
    sugestoes: list[Decimal | None] = [None for _ in tipos]
    if tem_metas:
        sugestoes = list(
            _dividir(
                entrada.modo,
                [valores.get(t, ZERO) for t in tipos],
                [dividir(entrada.metas_classe.get(t, ZERO), CEM) for t in tipos],
                entrada.aporte,
            )
        )
    classes: list[ClassePlano] = []
    invalidos: list[str] = []
    soma_desvios = ZERO
    for tipo, sugestao in zip(tipos, sugestoes, strict=True):
        valor = valores.get(tipo, ZERO)
        atual = dividir(valor * CEM, total) if total > ZERO else ZERO
        meta = entrada.metas_classe.get(tipo, ZERO) if tem_metas else None
        desvio = desvio_pp(atual, meta) if meta is not None else None
        if meta is not None:
            soma_desvios += abs(atual - meta)
        pesos = entrada.pesos.get(tipo, {})
        usa_pesos = tem_metas and _pesos_validos(pesos)
        if tem_metas and pesos and not usa_pesos:
            invalidos.append(tipo)
        classes.append(
            ClassePlano(
                tipo_ativo=tipo,
                valor_atual=valor,
                percentual_atual=atual,
                meta=meta,
                desvio_pp=desvio,
                fora_da_banda=desvio is not None and fora_da_banda(desvio, entrada.tolerancia_pp),
                sugestao=sugestao,
                usa_pesos=usa_pesos,
                ativos=_ativos_da_classe(
                    posicoes_por_tipo.get(tipo, []), pesos, usa_pesos, sugestao, entrada.modo
                ),
            )
        )
    return Plano(
        tem_metas=tem_metas,
        total=total,
        aporte=entrada.aporte,
        modo=entrada.modo,
        tolerancia_pp=entrada.tolerancia_pp,
        desvio_total_pp=arredondar(dividir(soma_desvios, Decimal(2)), CASAS_PP)
        if tem_metas
        else None,
        classes_fora_da_banda=sum(1 for c in classes if c.fora_da_banda),
        classes=tuple(classes),
        classes_com_pesos_invalidos=tuple(invalidos),
    )
