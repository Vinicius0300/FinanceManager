"""Rebalanceamento: metas de alocação (classe + peso por ativo) e plano informativo.

O plano nunca executa ordens: só diz quanto cada classe está desviada da meta, onde aportar
e, no modo completo, o que vender e comprar. Vale para a carteira inteira (Análise Geral).

Arredondamento na saída: dinheiro com 2 casas (as sugestões já vêm em centavos, fechando
exatamente o aporte), percentuais e desvios com 2 casas, quantidade estimada com 8.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencias import PROTEGIDO, HojeDep, SessaoDep, respostas
from app.api.schemas import Modelo, Numero
from app.domain.numeros import CASAS_PERCENTUAL, arredondar, arredondar_moeda, arredondar_quantidade
from app.domain.rebalanceamento import (
    AcaoSugerida,
    ClassePlano,
    ModoPlano,
    SugestaoAtivo,
    acao,
)
from app.services import rebalanceamento as servico
from app.services.rebalanceamento import MetaClasse, Metas, PesoAtivo, PlanoRebalanceamento

router = APIRouter(prefix="/api/rebalanceamento", tags=["rebalanceamento"], dependencies=PROTEGIDO)


class MetaClasseEsquema(Modelo):
    tipo_ativo: str
    percentual: Numero


class PesoAtivoEsquema(Modelo):
    tipo_ativo: str
    ativo_id: int
    peso: Numero


class MetasEsquema(Modelo):
    classes: list[MetaClasseEsquema]
    ativos: list[PesoAtivoEsquema]
    tolerancia_pp: int


class AtivoPlanoSaida(Modelo):
    ativo_id: int
    simbolo: str | None
    nome: str
    valor_atual: Numero
    peso: Numero | None
    sugestao: Numero | None
    acao: AcaoSugerida
    quantidade_estimada: Numero | None
    lucro_estimado: Numero | None
    defasado: bool
    aviso: str | None


class ClassePlanoSaida(Modelo):
    tipo_ativo: str
    valor_atual: Numero
    percentual_atual: Numero
    meta: Numero | None
    desvio_pp: Numero | None
    fora_da_banda: bool
    sugestao: Numero | None
    acao: AcaoSugerida
    usa_pesos: bool
    ativos: list[AtivoPlanoSaida]


class PlanoSaida(Modelo):
    tem_metas: bool
    patrimonio_considerado: Numero
    caixa_disponivel: Numero
    aporte: Numero
    modo: ModoPlano
    tolerancia_pp: int
    desvio_total_pp: Numero | None
    classes_fora_da_banda: int
    classes: list[ClassePlanoSaida]
    avisos: list[str]


# ---------------------------------------------------------------- conversões


def _pct(valor: Decimal) -> Decimal:
    return arredondar(valor, CASAS_PERCENTUAL)


def _pct_opcional(valor: Decimal | None) -> Decimal | None:
    return None if valor is None else _pct(valor)


def _moeda_opcional(valor: Decimal | None) -> Decimal | None:
    return None if valor is None else arredondar_moeda(valor)


def _metas(metas: Metas) -> MetasEsquema:
    return MetasEsquema(
        classes=[
            MetaClasseEsquema(tipo_ativo=c.tipo_ativo, percentual=_pct(c.percentual))
            for c in metas.classes
        ],
        ativos=[
            PesoAtivoEsquema(tipo_ativo=a.tipo_ativo, ativo_id=a.ativo_id, peso=_pct(a.peso))
            for a in metas.ativos
        ],
        tolerancia_pp=metas.tolerancia_pp,
    )


def _ativo(item: SugestaoAtivo, resultado: PlanoRebalanceamento) -> AtivoPlanoSaida:
    cadastro = resultado.ativos[item.ativo_id]
    return AtivoPlanoSaida(
        ativo_id=item.ativo_id,
        simbolo=cadastro.simbolo,
        nome=cadastro.nome,
        valor_atual=arredondar_moeda(item.valor_atual),
        peso=_pct_opcional(item.peso),
        sugestao=item.sugestao,
        acao=acao(item.sugestao),
        quantidade_estimada=None
        if item.quantidade_estimada is None
        else arredondar_quantidade(item.quantidade_estimada).normalize(),
        lucro_estimado=_moeda_opcional(item.lucro_estimado),
        defasado=item.defasado,
        aviso=item.aviso,
    )


def _classe(classe: ClassePlano, resultado: PlanoRebalanceamento) -> ClassePlanoSaida:
    return ClassePlanoSaida(
        tipo_ativo=classe.tipo_ativo,
        valor_atual=arredondar_moeda(classe.valor_atual),
        percentual_atual=_pct(classe.percentual_atual),
        meta=_pct_opcional(classe.meta),
        desvio_pp=classe.desvio_pp,
        fora_da_banda=classe.fora_da_banda,
        sugestao=classe.sugestao,
        acao=acao(classe.sugestao),
        usa_pesos=classe.usa_pesos,
        ativos=[_ativo(a, resultado) for a in classe.ativos],
    )


Aporte = Annotated[
    Numero | None, Query(description="Valor a aportar em BRL (padrão: o caixa disponível).")
]
Modo = Annotated[ModoPlano, Query(description="aportes (só compra) ou completo (compra e venda).")]


# ---------------------------------------------------------------- rotas


@router.get(
    "/metas",
    response_model=MetasEsquema,
    summary="Metas de alocação por classe, pesos por ativo e tolerância da banda",
    responses=respostas(),
)
def obter_metas(sessao: SessaoDep) -> MetasEsquema:
    return _metas(servico.obter_metas(sessao))


@router.put(
    "/metas",
    response_model=MetasEsquema,
    summary="Substitui todas as metas (lista vazia de classes apaga as metas)",
    description=(
        "As metas das classes somam exatamente 100%; os pesos dos ativos de uma classe "
        "também. Metas e pesos com no máximo 2 casas; tolerância inteira de 1 a 20 p.p."
    ),
    responses=respostas(422),
)
def gravar_metas(dados: MetasEsquema, sessao: SessaoDep) -> MetasEsquema:
    metas = servico.gravar_metas(
        sessao,
        Metas(
            classes=tuple(MetaClasse(c.tipo_ativo, c.percentual) for c in dados.classes),
            ativos=tuple(PesoAtivo(a.tipo_ativo, a.ativo_id, a.peso) for a in dados.ativos),
            tolerancia_pp=dados.tolerancia_pp,
        ),
    )
    return _metas(metas)


@router.get(
    "/plano",
    response_model=PlanoSaida,
    summary="Desvios das metas e sugestão de aporte (ou de compra e venda)",
    description=(
        "Sugestão informativa; o app nunca executa ordens. Sem `aporte`, usa o caixa "
        "disponível de todas as instituições."
    ),
    responses=respostas(422),
)
def obter_plano(
    sessao: SessaoDep,
    hoje: HojeDep,
    aporte: Aporte = None,
    modo: Modo = ModoPlano.APORTES,
) -> PlanoSaida:
    resultado = servico.montar_plano_rebalanceamento(sessao, hoje, aporte, modo)
    plano = resultado.plano
    return PlanoSaida(
        tem_metas=plano.tem_metas,
        patrimonio_considerado=arredondar_moeda(plano.total),
        caixa_disponivel=resultado.caixa_disponivel,
        aporte=arredondar_moeda(plano.aporte),
        modo=plano.modo,
        tolerancia_pp=plano.tolerancia_pp,
        desvio_total_pp=plano.desvio_total_pp,
        classes_fora_da_banda=plano.classes_fora_da_banda,
        classes=[_classe(c, resultado) for c in plano.classes],
        avisos=list(resultado.avisos),
    )
