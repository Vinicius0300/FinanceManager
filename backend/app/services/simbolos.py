"""Listas oficiais de tickers: importação (B3 e EUA) e busca do cadastro de movimentações.

**Importação** (:class:`ImportadorListas`): roda em segundo plano na primeira abertura
(bolsas sem lista) e pelo botão "Atualizar lista". Rede **sem sessão aberta**; a lista da
bolsa é trocada inteira numa transação só (uma falha no meio mantém a anterior). Papéis
de categoria não mapeada vão para o log.

**Busca** (:func:`buscar_simbolos`), em três camadas:
1. ativos já cadastrados (de qualquer tipo) cujo ticker ou nome contém o texto;
2. a lista oficial da bolsa do tipo escolhido, com o **tipo oficial** de cada papel (o
   front avisa quando ele diverge do tipo escolhido);
3. pesquisa externa por texto: para tipos com lista, só **sugere o nome** de um ticker que
   não está na lista (tipo "não identificado"); para cripto, os resultados da CoinGecko
   (o tipo é certo e o id identifica a moeda).

Ticker não encontrado na lista e lista não tentada hoje: a busca pede uma atualização em
segundo plano (no máximo uma por dia e por bolsa); o front refaz a busca quando o evento
``lista_atualizada`` chega.
"""

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.asset_types.base import HandlerTipoAtivo
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.core.banco import sessao_transacional
from app.domain.listas import BOLSA_B3, BOLSA_EUA, SUFIXO_YAHOO_B3, ItemListado
from app.domain.tempo import agora_utc, data_local
from app.providers.base import ListaBaixada, ProviderError
from app.providers.registry import RegistroProviders
from app.repositories import modelos as m
from app.repositories.simbolos import RepositorioListasSimbolos, RepositorioSimbolosListados
from app.services.coleta import EventoColeta, Publicar

logger = logging.getLogger(__name__)

LIMITE_BUSCA = 20
TAMANHO_ERRO = 500
TAMANHO_MAXIMO_TEXTO = 60
_CARACTERES_PERMITIDOS = re.compile(r"[^\w .&/-]", re.UNICODE)

# Bolsas americanas na pesquisa do Yahoo (para filtrar papéis de outros países).
BOLSAS_YAHOO_EUA = frozenset({"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS", "NAS", "NYS"})


def _sem_publicacao(_: EventoColeta) -> None:
    return None


# ------------------------------------------------------------------ importação


@dataclass(frozen=True)
class ResultadoImportacao:
    bolsa: str
    sucesso: bool
    quantidade: int = 0
    mensagem: str | None = None


def _registros(itens: Sequence[ItemListado]) -> list[m.SimboloListado]:
    return [
        m.SimboloListado(
            bolsa=item.bolsa,
            simbolo=item.simbolo[:30],
            nome=item.nome[:150],
            tipo=item.tipo,
            tipo_papel=item.tipo_papel,
            bolsa_eua=item.bolsa_eua,
            categoria=item.categoria[:60],
            simbolo_yahoo=item.simbolo_yahoo[:60],
        )
        for item in itens
    ]


def bolsas_sem_lista(sessao: Session, bolsas: Sequence[str]) -> list[str]:
    """Bolsas que nunca tiveram uma importação bem-sucedida."""
    listas = RepositorioListasSimbolos(sessao)
    return [b for b in bolsas if (lista := listas.obter(b)) is None or lista.atualizado_em is None]


def tentou_hoje(sessao: Session, bolsa: str, hoje: date) -> bool:
    lista = RepositorioListasSimbolos(sessao).obter(bolsa)
    return (
        lista is not None
        and lista.ultima_tentativa is not None
        and data_local(lista.ultima_tentativa) == hoje
    )


class ImportadorListas:
    """Importa as listas oficiais. Quem chama garante uma importação por vez."""

    def __init__(
        self,
        fabrica_sessoes: sessionmaker[Session],
        providers: RegistroProviders,
        *,
        relogio: Callable[[], datetime] = agora_utc,
        publicar: Publicar = _sem_publicacao,
    ) -> None:
        self._fabrica = fabrica_sessoes
        self._providers = providers
        self._relogio = relogio
        self._publicar = publicar

    @property
    def bolsas(self) -> list[str]:
        return self._providers.bolsas

    def pendentes(self) -> list[str]:
        with sessao_transacional(self._fabrica) as sessao:
            return bolsas_sem_lista(sessao, self.bolsas)

    def executar(self, bolsas: Sequence[str] | None = None) -> list[ResultadoImportacao]:
        escolhidas = [
            b for b in (bolsas if bolsas is not None else self.bolsas) if b in self.bolsas
        ]
        return [self._importar(bolsa) for bolsa in escolhidas]

    def _importar(self, bolsa: str) -> ResultadoImportacao:
        fonte = self._providers.lista(bolsa)
        if fonte is None:  # pragma: no cover - filtrado em executar
            return ResultadoImportacao(bolsa, False, mensagem="Fonte não registrada.")
        agora = self._relogio()
        with sessao_transacional(self._fabrica) as sessao:
            RepositorioListasSimbolos(sessao).obter_ou_criar(bolsa).ultima_tentativa = agora
        try:
            baixada = fonte.baixar(data_local(agora))  # rede sem sessão aberta
        except ProviderError as erro:
            return self._falhou(bolsa, erro.mensagem)
        except Exception:
            logger.exception("Falha inesperada ao importar a lista de %s.", bolsa)
            return self._falhou(bolsa, f"Erro inesperado ao importar a lista de {bolsa}.")
        try:
            quantidade = self._gravar(baixada)
        except Exception:
            logger.exception("Falha ao gravar a lista de %s.", bolsa)
            return self._falhou(bolsa, f"Erro ao gravar a lista de {bolsa}.")
        if baixada.nao_mapeados:
            exemplos = ", ".join(f"{t} ({c})" for t, c in baixada.nao_mapeados[:10])
            logger.warning(
                "Lista %s: %d papéis com categoria não mapeada ficaram fora: %s.",
                bolsa,
                len(baixada.nao_mapeados),
                exemplos,
            )
        logger.info("Lista %s importada: %d papéis.", bolsa, quantidade)
        self._publicar(EventoColeta("lista_atualizada", {"bolsa": bolsa, "quantidade": quantidade}))
        return ResultadoImportacao(bolsa, True, quantidade)

    def _gravar(self, baixada: ListaBaixada) -> int:
        with sessao_transacional(self._fabrica) as sessao:
            quantidade = RepositorioSimbolosListados(sessao).substituir_bolsa(
                baixada.bolsa, _registros(baixada.itens)
            )
            lista = RepositorioListasSimbolos(sessao).obter_ou_criar(baixada.bolsa)
            lista.atualizado_em = self._relogio()
            lista.quantidade = quantidade
            lista.status_arquivo = baixada.status_arquivo
            lista.data_arquivo = baixada.data_arquivo
            lista.ultimo_erro = None
        return quantidade

    def _falhou(self, bolsa: str, mensagem: str) -> ResultadoImportacao:
        logger.warning("Lista %s não importada: %s", bolsa, mensagem)
        with sessao_transacional(self._fabrica) as sessao:
            RepositorioListasSimbolos(sessao).obter_ou_criar(bolsa).ultimo_erro = mensagem[
                :TAMANHO_ERRO
            ]
        self._publicar(EventoColeta("erro_lista", {"bolsa": bolsa, "mensagem": mensagem}))
        return ResultadoImportacao(bolsa, False, mensagem=mensagem)


def situacao_listas(sessao: Session, bolsas: Sequence[str]) -> list[m.ListaSimbolos]:
    """Situação de cada bolsa registrada (as nunca tentadas aparecem vazias)."""
    listas = RepositorioListasSimbolos(sessao)
    return [listas.obter(b) or m.ListaSimbolos(bolsa=b, quantidade=0) for b in bolsas]


# ------------------------------------------------------------------ busca


@dataclass(frozen=True)
class ItemBusca:
    """Um resultado da busca do cadastro.

    ``tipo``: tipo do app (oficial, para itens da lista); ``None`` = não identificado.
    ``origem``: ``carteira`` (já cadastrado), ``lista`` (lista oficial) ou ``pesquisa``.
    """

    simbolo: str | None
    nome: str
    tipo: str | None
    origem: str
    ativo_id: int | None = None
    simbolo_externo: str | None = None
    categoria: str | None = None
    campos_sugeridos: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoBusca:
    itens: list[ItemBusca]
    bolsa: str | None = None
    lista_disponivel: bool = True  # a bolsa já tem lista importada
    lista_desatualizada: bool = False  # ticker fora da lista: pedir atualização em 2º plano
    aviso: str | None = None


def limpar_texto_busca(texto: str) -> str:
    """Tira caracteres que não aparecem em tickers e nomes (inclusive os curingas % e _)."""
    limpo = _CARACTERES_PERMITIDOS.sub(" ", texto.replace("_", " "))
    return " ".join(limpo.split())[:TAMANHO_MAXIMO_TEXTO]


def _parece_ticker(texto: str) -> bool:
    return " " not in texto and 1 <= len(texto) <= 12


def _campos_validos(handler: HandlerTipoAtivo | None, sugeridos: dict[str, str]) -> dict[str, str]:
    """Só os campos que o tipo tem, com valores entre as opções dele."""
    if handler is None:
        return {}
    validos: dict[str, str] = {}
    for campo in handler.campos:
        valor = sugeridos.get(campo.nome)
        if valor is not None and (not campo.opcoes or valor in {o.valor for o in campo.opcoes}):
            validos[campo.nome] = valor
    return validos


def _da_carteira(sessao: Session, texto: str) -> list[m.Ativo]:
    contem = "%" + texto.casefold() + "%"
    consulta = (
        select(m.Ativo)
        .where(
            or_(
                func.casefold(m.Ativo.simbolo).like(contem),
                func.casefold(m.Ativo.nome).like(contem),
            )
        )
        .order_by(m.Ativo.simbolo, m.Ativo.nome)
        .limit(LIMITE_BUSCA)
    )
    return list(sessao.scalars(consulta))


def _pesquisa_externa(
    providers: RegistroProviders, handler: HandlerTipoAtivo, texto: str
) -> tuple[list[ItemBusca], str | None]:
    busca = providers.busca(handler.provider)
    if busca is None:
        return [], None
    try:
        sugestoes = busca.buscar(texto)
    except ProviderError as erro:
        return [], f"Pesquisa externa indisponível: {erro.mensagem}"
    itens: list[ItemBusca] = []
    for sugestao in sugestoes:
        if handler.lista_simbolos == BOLSA_B3:
            if not sugestao.simbolo.endswith(SUFIXO_YAHOO_B3):
                continue
            simbolo = handler.normalizar_simbolo(sugestao.simbolo)
            tipo = None  # fora da lista oficial: não identificado
        elif handler.lista_simbolos == BOLSA_EUA:
            if sugestao.bolsa not in BOLSAS_YAHOO_EUA:
                continue
            simbolo = handler.normalizar_simbolo(sugestao.simbolo)
            tipo = None
        else:  # pesquisa da própria fonte do tipo (ex.: cripto na CoinGecko)
            simbolo = sugestao.simbolo
            tipo = handler.slug
        itens.append(
            ItemBusca(
                simbolo=simbolo,
                nome=sugestao.nome,
                tipo=tipo,
                origem="pesquisa",
                simbolo_externo=sugestao.simbolo_externo,
            )
        )
    return itens, None


def buscar_simbolos(
    sessao: Session,
    tipo: str,
    texto: str,
    providers: RegistroProviders,
    hoje: date,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> ResultadoBusca:
    handler = registro.obter(tipo)
    limpo = limpar_texto_busca(texto)
    if not limpo:
        return ResultadoBusca(itens=[], bolsa=handler.lista_simbolos)

    itens: list[ItemBusca] = [
        ItemBusca(
            simbolo=a.simbolo,
            nome=a.nome,
            tipo=a.tipo,
            origem="carteira",
            ativo_id=a.id,
            simbolo_externo=a.simbolo_externo,
        )
        for a in _da_carteira(sessao, limpo)
    ]
    ja_cadastrados = {(a.tipo, a.simbolo) for a in itens if a.simbolo}

    bolsa = handler.lista_simbolos
    if bolsa is None:
        externos, aviso_externo = (
            _pesquisa_externa(providers, handler, limpo) if handler.busca_por_ticker else ([], None)
        )
        cadastrados_externos = {(a.tipo, (a.simbolo_externo or "").lower()) for a in itens}
        itens += [
            e
            for e in externos
            if (e.tipo, (e.simbolo_externo or "").lower()) not in cadastrados_externos
        ]
        return ResultadoBusca(itens=itens[: LIMITE_BUSCA * 2], aviso=aviso_externo)

    lista = RepositorioListasSimbolos(sessao).obter(bolsa)
    disponivel = lista is not None and lista.atualizado_em is not None
    ticker = handler.normalizar_simbolo(limpo)  # "brk.b" → "BRK-B", "petr4.sa" → "PETR4"
    listados = RepositorioSimbolosListados(sessao).buscar(bolsa, ticker, limpo, LIMITE_BUSCA)
    for listado in listados:
        if (listado.tipo, listado.simbolo) in ja_cadastrados:
            continue
        handler_oficial = registro.obter(listado.tipo) if listado.tipo in registro else None
        sugeridos = {"tipo_papel": listado.tipo_papel, "bolsa": listado.bolsa_eua}
        itens.append(
            ItemBusca(
                simbolo=listado.simbolo,
                nome=listado.nome,
                tipo=listado.tipo,
                origem="lista",
                simbolo_externo=listado.simbolo_yahoo,
                categoria=listado.categoria,
                campos_sugeridos=_campos_validos(
                    handler_oficial, {k: v for k, v in sugeridos.items() if v}
                ),
            )
        )

    # Digitando "PETR", PETR3/PETR4 já respondem: só um ticker sem nenhum papel que comece
    # por ele conta como "fora da lista" (pesquisa externa e pedido de atualização).
    encontrado = any(i.simbolo and i.simbolo.startswith(ticker) for i in itens)
    aviso: str | None = None
    desatualizada = not disponivel and not tentou_hoje(sessao, bolsa, hoje)
    if _parece_ticker(limpo) and not encontrado:
        desatualizada = not tentou_hoje(sessao, bolsa, hoje)
        externos, aviso = _pesquisa_externa(providers, handler, limpo)
        itens += [e for e in externos if e.simbolo not in {i.simbolo for i in itens}]
    return ResultadoBusca(
        itens=itens[: LIMITE_BUSCA * 2],
        bolsa=bolsa,
        lista_disponivel=disponivel,
        lista_desatualizada=desatualizada,
        aviso=aviso,
    )
