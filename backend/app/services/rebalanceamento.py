"""Rebalanceamento: metas de alocação (classes e pesos por ativo), tolerância e plano.

- As metas valem só para a carteira inteira (Análise Geral); não há filtro por instituição.
- O plano usa as posições abertas avaliadas hoje (``services/portfolio.montar_portfolio``)
  e o caixa de todas as instituições, que **pré-preenche o aporte** sem entrar em T.
- As regras de cálculo estão em ``domain/rebalanceamento.py``; aqui só se lê o banco,
  valida a entrada e monta os textos de aviso. Nada é gravado em ``sugestoes``.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.erros import DetalheCampo, ValidacaoError, exigir
from app.domain.numeros import CEM, ZERO, arredondar_moeda, casas_decimais, formatar_numero
from app.domain.rebalanceamento import (
    TOLERANCIA_MAXIMA_PP,
    TOLERANCIA_MINIMA_PP,
    TOLERANCIA_PADRAO_PP,
    EntradaPlano,
    ModoPlano,
    Plano,
    PosicaoPlano,
    aviso_cotacao,
    montar_plano,
)
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.repositories.configuracoes import RepositorioConfiguracoes
from app.repositories.metas import RepositorioMetas
from app.services.portfolio import montar_portfolio

CHAVE_TOLERANCIA = "rebalanceamento_tolerancia_pp"
CASAS_META = 2


@dataclass(frozen=True)
class MetaClasse:
    tipo_ativo: str
    percentual: Decimal  # % da carteira


@dataclass(frozen=True)
class PesoAtivo:
    tipo_ativo: str
    ativo_id: int
    peso: Decimal  # % da classe


@dataclass(frozen=True)
class Metas:
    classes: tuple[MetaClasse, ...]
    ativos: tuple[PesoAtivo, ...]
    tolerancia_pp: int


@dataclass(frozen=True)
class PlanoRebalanceamento:
    plano: Plano
    caixa_disponivel: Decimal  # BRL, 2 casas
    ativos: Mapping[int, m.Ativo]  # cadastro de cada ativo citado no plano
    avisos: tuple[str, ...]


# ---------------------------------------------------------------- tolerância


def _tolerancia_valida(valor: object) -> bool:
    return (
        isinstance(valor, int)
        and not isinstance(valor, bool)
        and TOLERANCIA_MINIMA_PP <= valor <= TOLERANCIA_MAXIMA_PP
    )


def obter_tolerancia(sessao: Session) -> int:
    """Tolerância da banda em p.p. (padrão 5). Valor gravado fora da faixa cai no padrão."""
    valor = RepositorioConfiguracoes(sessao).valor(CHAVE_TOLERANCIA, TOLERANCIA_PADRAO_PP)
    return valor if isinstance(valor, int) and _tolerancia_valida(valor) else TOLERANCIA_PADRAO_PP


# ---------------------------------------------------------------- metas


def obter_metas(sessao: Session) -> Metas:
    repositorio = RepositorioMetas(sessao)
    return Metas(
        classes=tuple(MetaClasse(c.tipo_ativo, c.percentual) for c in repositorio.classes()),
        ativos=tuple(
            PesoAtivo(ativo.tipo, meta.ativo_id, meta.peso) for meta, ativo in repositorio.ativos()
        ),
        tolerancia_pp=obter_tolerancia(sessao),
    )


def _nome_tipo(registro: RegistroTiposAtivo, tipo: str) -> str:
    return registro.obter(tipo).nome if tipo in registro else tipo


def _validar_percentual(valor: Decimal, campo: str, rotulo: str) -> list[DetalheCampo]:
    if not ZERO <= valor <= CEM:
        return [DetalheCampo(campo, f"{rotulo} deve estar entre 0 e 100%.")]
    if casas_decimais(valor) > CASAS_META:
        return [DetalheCampo(campo, f"Use no máximo {CASAS_META} casas decimais.")]
    return []


def _validar_classes(
    classes: Sequence[MetaClasse], registro: RegistroTiposAtivo
) -> list[DetalheCampo]:
    detalhes: list[DetalheCampo] = []
    vistos: set[str] = set()
    for classe in classes:
        campo = f"classes.{classe.tipo_ativo}"
        if classe.tipo_ativo not in registro:
            detalhes.append(DetalheCampo(campo, "Tipo de ativo desconhecido."))
            continue
        if classe.tipo_ativo in vistos:
            detalhes.append(DetalheCampo(campo, "Classe repetida."))
            continue
        vistos.add(classe.tipo_ativo)
        detalhes += _validar_percentual(classe.percentual, campo, "A meta")
    soma = sum((c.percentual for c in classes), ZERO)
    if classes and not detalhes and soma != CEM:
        detalhes.append(
            DetalheCampo(
                "classes",
                f"As metas das classes devem somar 100% (soma atual: {formatar_numero(soma)}%).",
            )
        )
    return detalhes


def _validar_pesos(
    sessao: Session,
    pesos: Sequence[PesoAtivo],
    classes: Sequence[MetaClasse],
    registro: RegistroTiposAtivo,
) -> list[DetalheCampo]:
    detalhes: list[DetalheCampo] = []
    com_meta = {c.tipo_ativo for c in classes}
    repositorio = RepositorioAtivos(sessao)
    vistos: set[int] = set()
    por_classe: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for peso in pesos:
        campo = f"ativos.{peso.ativo_id}"
        ativo = repositorio.obter(peso.ativo_id)
        if ativo is None:
            detalhes.append(DetalheCampo(campo, "Ativo não encontrado."))
            continue
        if ativo.tipo != peso.tipo_ativo:
            detalhes.append(
                DetalheCampo(
                    campo,
                    f"O ativo {ativo.simbolo or ativo.nome} não é da classe "
                    f"{_nome_tipo(registro, peso.tipo_ativo)}.",
                )
            )
            continue
        if peso.ativo_id in vistos:
            detalhes.append(DetalheCampo(campo, "Ativo repetido."))
            continue
        vistos.add(peso.ativo_id)
        if peso.tipo_ativo not in com_meta:
            detalhes.append(
                DetalheCampo(campo, "Defina a meta da classe antes de dar peso aos ativos dela.")
            )
            continue
        erros = _validar_percentual(peso.peso, campo, "O peso")
        detalhes += erros
        por_classe[peso.tipo_ativo] += peso.peso
    if not detalhes:
        for tipo, soma in sorted(por_classe.items()):
            if soma != CEM:
                detalhes.append(
                    DetalheCampo(
                        f"pesos.{tipo}",
                        f"Os pesos dos ativos de {_nome_tipo(registro, tipo)} devem somar 100% "
                        f"(soma atual: {formatar_numero(soma)}%).",
                    )
                )
    return detalhes


def gravar_metas(
    sessao: Session, metas: Metas, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> Metas:
    """Valida e substitui todas as metas (lista vazia de classes apaga as metas).

    A tolerância é gravada junto. Erros vêm todos de uma vez, por campo
    (``classes.acao_br``, ``ativos.12``, ``pesos.acao_br``, ``tolerancia_pp``).
    """
    detalhes: list[DetalheCampo] = []
    if not _tolerancia_valida(metas.tolerancia_pp):
        detalhes.append(
            DetalheCampo(
                "tolerancia_pp",
                f"A tolerância deve ser um número inteiro de {TOLERANCIA_MINIMA_PP} a "
                f"{TOLERANCIA_MAXIMA_PP} pontos percentuais.",
            )
        )
    detalhes += _validar_classes(metas.classes, registro)
    detalhes += _validar_pesos(sessao, metas.ativos, metas.classes, registro)
    if detalhes:
        raise ValidacaoError("Metas inválidas. Confira os campos destacados.", detalhes)
    RepositorioMetas(sessao).substituir(
        [m.MetaClasse(tipo_ativo=c.tipo_ativo, percentual=c.percentual) for c in metas.classes],
        [m.MetaAtivo(ativo_id=a.ativo_id, peso=a.peso) for a in metas.ativos],
    )
    RepositorioConfiguracoes(sessao).gravar(CHAVE_TOLERANCIA, metas.tolerancia_pp)
    return obter_metas(sessao)


# ---------------------------------------------------------------- plano


def montar_plano_rebalanceamento(
    sessao: Session,
    hoje: date,
    aporte: Decimal | None = None,
    modo: ModoPlano = ModoPlano.APORTES,
    *,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> PlanoRebalanceamento:
    """Plano de hoje para a carteira inteira. Sem ``aporte``, usa o caixa disponível."""
    if aporte is not None:
        exigir(aporte >= ZERO, "aporte", "O aporte não pode ser negativo.")
        exigir(casas_decimais(aporte) <= 2, "aporte", "Use no máximo 2 casas decimais.")
    portfolio = montar_portfolio(sessao, hoje, registro=registro)
    caixa = arredondar_moeda(portfolio.resumo.caixa_brl)
    metas = obter_metas(sessao)
    ativos: dict[int, m.Ativo] = {}
    posicoes: list[PosicaoPlano] = []
    avisos: list[str] = []
    for item in portfolio.posicoes:
        posicao, avaliacao = item.posicao, item.posicao.avaliacao
        ativos[item.ativo.id] = item.ativo
        if avaliacao.valor_brl is None:
            avisos.append(
                f"{item.ativo.simbolo or item.ativo.nome} ficou fora do cálculo (sem valor atual)."
            )
        posicoes.append(
            PosicaoPlano(
                ativo_id=item.ativo.id,
                tipo_ativo=item.ativo.tipo,
                valor=avaliacao.valor_brl or ZERO,
                custo=posicao.valores_brl.custo,
                quantidade=posicao.quantidade,
                defasado=avaliacao.defasado,
                aviso=aviso_cotacao(
                    defasado=avaliacao.defasado,
                    erro=avaliacao.erro,
                    aviso=avaliacao.aviso,
                    data_preco=avaliacao.data_preco,
                    hoje=hoje,
                ),
            )
        )
    pesos: dict[str, dict[int, Decimal]] = defaultdict(dict)
    for meta, ativo in RepositorioMetas(sessao).ativos():
        pesos[ativo.tipo][meta.ativo_id] = meta.peso
        ativos.setdefault(ativo.id, ativo)
    plano = montar_plano(
        EntradaPlano(
            posicoes=tuple(posicoes),
            metas_classe={c.tipo_ativo: c.percentual for c in metas.classes},
            pesos=pesos,
            aporte=caixa if aporte is None else aporte,
            modo=modo,
            tolerancia_pp=metas.tolerancia_pp,
        )
    )
    for tipo in plano.classes_com_pesos_invalidos:
        avisos.append(
            f"Os pesos dos ativos de {_nome_tipo(registro, tipo)} não somam mais 100% (um ativo "
            "com peso pode ter sido excluído). A sugestão ficou só no nível da classe; revise "
            "as metas."
        )
    return PlanoRebalanceamento(
        plano=plano, caixa_disponivel=caixa, ativos=ativos, avisos=tuple(avisos)
    )
