"""Casos de uso de dados de mercado: preços e indicadores (manuais e automáticos).

**Preços** (só ativos cotados; renda fixa e poupança são calculadas):
- um preço por ativo por dia (data local de Brasília). Gravar de novo no mesmo dia
  atualiza o registro do dia (valor, instante, origem e provider);
- um preço **manual** do dia não é sobrescrito pela coleta automática do mesmo dia
  (no dia seguinte a coleta volta a valer); o manual sempre substitui o automático;
- fechamentos do histórico de uma fonte preenchem dias sem preço e corrigem preços
  automáticos de dias passados (o fechamento é mais exato que uma coleta intradiária).

**Indicadores:** o lançamento manual recusa data repetida (use a edição). A coleta
automática só grava datas sem registro, com uma exceção: uma fonte de prioridade maior
substitui o valor de uma fonte automática de prioridade menor (ex.: a PTAX do Banco
Central substitui o dólar do Yahoo do mesmo dia). Registro manual sempre prevalece.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.asset_types.base import HandlerCotado
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import OrigemPreco, TipoIndicador
from app.domain.erros import ConflitoError, NaoEncontradoError, OperacaoNaoPermitidaError, exigir
from app.domain.indicadores import NOMES_INDICADORES, Indicadores, PontoIndicador, SerieIndicador
from app.domain.moedas import MOEDA_BASE, validar_moeda
from app.domain.numeros import CASAS_CAMBIO, CASAS_PRECO, ZERO, exigir_casas
from app.domain.precos import PontoPreco, SeriePrecos, instante_fechamento
from app.domain.tempo import data_local, formatar_data
from app.repositories.mercado import RepositorioIndicadores, RepositorioPrecos
from app.repositories.modelos import Ativo, Indicador, Preco
from app.services.cadastros import handler_do_ativo, obter_ativo

FONTE_MANUAL = "manual"
PRIORIDADE_FONTES_AUTOMATICAS = {"yfinance": 1, "bcb_sgs": 2}
"""Fontes automáticas de indicadores e sua prioridade (maior substitui menor)."""
TAMANHO_FONTE = 40


# ---------------------------------------------------------------- Preços


def _exigir_cotado(ativo: Ativo, registro: RegistroTiposAtivo) -> HandlerCotado:
    handler = handler_do_ativo(ativo, registro)
    if not isinstance(handler, HandlerCotado):
        raise OperacaoNaoPermitidaError(
            f"{handler.nome} não tem cotação: o valor é calculado pelo rendimento."
        )
    return handler


def _validar_preco(valor: Decimal, origem: OrigemPreco, provider: str | None) -> None:
    exigir(valor > ZERO, "valor", "O preço deve ser maior que zero.")
    # Providers arredondam a cotação antes de gravar (valores vindos de float).
    exigir_casas(valor, CASAS_PRECO, "valor")
    exigir(
        origem is not OrigemPreco.CALCULADO,
        "origem",
        "Preço calculado não é gravado: ele é obtido na avaliação da carteira.",
    )
    exigir(
        origem is not OrigemPreco.AUTOMATICO or bool(provider),
        "provider",
        "Preço automático precisa informar o provider.",
    )


def registrar_preco(
    sessao: Session,
    ativo_id: int,
    data_hora: datetime,
    valor: Decimal,
    origem: OrigemPreco,
    provider: str | None = None,
    *,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> Preco:
    """Grava o preço do dia de ``data_hora`` (insere ou atualiza o registro do dia).

    Um preço automático não substitui o manual do mesmo dia: nesse caso o registro manual
    é devolvido sem alteração.
    """
    ativo = obter_ativo(sessao, ativo_id)
    _exigir_cotado(ativo, registro)
    exigir(data_hora.tzinfo is not None, "data_hora", "Informe a data/hora com fuso horário.")
    _validar_preco(valor, origem, provider)
    data_hora = data_hora.astimezone(UTC)  # o objeto devolvido fica igual ao relido do banco
    dia = data_local(data_hora)
    repositorio = RepositorioPrecos(sessao)
    existente = repositorio.na_data(ativo.id, dia)
    if existente is None:
        return repositorio.adicionar(
            Preco(
                ativo_id=ativo.id,
                data=dia,
                data_hora=data_hora,
                valor=valor,
                moeda=ativo.moeda,
                origem=origem,
                provider=provider if origem is OrigemPreco.AUTOMATICO else None,
            )
        )
    if existente.origem is OrigemPreco.MANUAL and origem is OrigemPreco.AUTOMATICO:
        return existente
    existente.data_hora = data_hora
    existente.valor = valor
    existente.origem = origem
    existente.provider = provider if origem is OrigemPreco.AUTOMATICO else None
    sessao.flush()
    return existente


def gravar_fechamentos(
    sessao: Session,
    ativo: Ativo,
    fechamentos: Iterable[tuple[date, Decimal]],
    provider: str,
    hoje: date,
) -> int:
    """Grava fechamentos diários de dias **anteriores** a ``hoje``; devolve quantos mudaram.

    Dia sem preço recebe o fechamento; preço automático do dia é corrigido; manual fica.
    O dia de hoje é tratado pela cotação atual (o candle de hoje ainda não fechou).
    """
    repositorio = RepositorioPrecos(sessao)
    existentes = {p.data: p for p in repositorio.do_ativo(ativo.id)}
    alterados = 0
    for dia, valor in fechamentos:
        if dia >= hoje:
            continue
        _validar_preco(valor, OrigemPreco.AUTOMATICO, provider)
        atual = existentes.get(dia)
        if atual is None:
            existentes[dia] = repositorio.adicionar(
                Preco(
                    ativo_id=ativo.id,
                    data=dia,
                    data_hora=instante_fechamento(dia).astimezone(UTC),
                    valor=valor,
                    moeda=ativo.moeda,
                    origem=OrigemPreco.AUTOMATICO,
                    provider=provider,
                )
            )
            alterados += 1
        elif atual.origem is OrigemPreco.AUTOMATICO and (
            atual.valor != valor or atual.provider != provider
        ):
            atual.valor = valor
            atual.provider = provider
            alterados += 1
    sessao.flush()
    return alterados


def obter_preco(sessao: Session, preco_id: int) -> Preco:
    preco = RepositorioPrecos(sessao).obter(preco_id)
    if preco is None:
        raise NaoEncontradoError(f"Preço {preco_id} não encontrado.")
    return preco


def excluir_preco_manual(sessao: Session, preco_id: int) -> None:
    """Remove um preço manual (a coleta automática volta a valer para aquele dia)."""
    preco = obter_preco(sessao, preco_id)
    if preco.origem is not OrigemPreco.MANUAL:
        raise OperacaoNaoPermitidaError("Só preços lançados manualmente podem ser excluídos.")
    RepositorioPrecos(sessao).remover(preco)


@dataclass(frozen=True)
class PaginaPrecos:
    itens: Sequence[Preco]
    total: int


def listar_precos(
    sessao: Session,
    ativo_id: int,
    inicio: date | None,
    fim: date | None,
    limite: int,
    deslocamento: int,
) -> PaginaPrecos:
    """Fechamentos diários do ativo, do mais recente para o mais antigo."""
    obter_ativo(sessao, ativo_id)
    itens, total = RepositorioPrecos(sessao).pagina(ativo_id, inicio, fim, limite, deslocamento)
    return PaginaPrecos(itens, total)


def carregar_precos(sessao: Session, ativo_id: int) -> SeriePrecos:
    return SeriePrecos(
        PontoPreco(p.data_hora, p.valor, p.origem)
        for p in RepositorioPrecos(sessao).do_ativo(ativo_id)
    )


# ---------------------------------------------------------------- Indicadores


def _validar_indicador(tipo: TipoIndicador, moeda: str, data: date, valor: Decimal) -> str:
    moeda = validar_moeda(moeda)
    if tipo is TipoIndicador.CAMBIO:
        exigir(moeda != MOEDA_BASE, "moeda", "Câmbio deve ser de uma moeda estrangeira.")
        exigir(valor > ZERO, "valor", "O câmbio deve ser maior que zero.")
        exigir_casas(valor, CASAS_CAMBIO, "valor")
    else:
        exigir(moeda == MOEDA_BASE, "moeda", "Selic, CDI e IPCA são indicadores em BRL.")
        exigir_casas(valor, CASAS_PRECO, "valor")
    if tipo in (TipoIndicador.SELIC, TipoIndicador.CDI):
        exigir(valor >= ZERO, "valor", "A taxa não pode ser negativa.")
    if tipo is TipoIndicador.IPCA:
        exigir(data.day == 1, "data", "O IPCA é mensal: use o dia 1º do mês de referência.")
    return moeda


def registrar_indicador(
    sessao: Session,
    tipo: TipoIndicador,
    data: date,
    valor: Decimal,
    moeda: str = MOEDA_BASE,
    fonte: str | None = FONTE_MANUAL,
) -> Indicador:
    """Lançamento de um indicador (manual por padrão). Data repetida é conflito."""
    moeda = _validar_indicador(tipo, moeda, data, valor)
    exigir(
        fonte is None or len(fonte) <= TAMANHO_FONTE,
        "fonte",
        f"Use no máximo {TAMANHO_FONTE} caracteres.",
    )
    repositorio = RepositorioIndicadores(sessao)
    if repositorio.na_data(tipo, moeda, data) is not None:
        raise ConflitoError(
            f"Já existe {NOMES_INDICADORES[tipo]} registrado para {formatar_data(data)}."
        )
    return repositorio.adicionar(
        Indicador(tipo=tipo, moeda=moeda, data=data, valor=valor, fonte=fonte)
    )


def obter_indicador(sessao: Session, indicador_id: int) -> Indicador:
    indicador = RepositorioIndicadores(sessao).obter(indicador_id)
    if indicador is None:
        raise NaoEncontradoError(f"Indicador {indicador_id} não encontrado.")
    return indicador


def editar_indicador(sessao: Session, indicador_id: int, valor: Decimal) -> Indicador:
    """Altera o valor; o registro passa a ser manual (a coleta não o sobrescreve mais)."""
    indicador = obter_indicador(sessao, indicador_id)
    _validar_indicador(indicador.tipo, indicador.moeda, indicador.data, valor)
    indicador.valor = valor
    indicador.fonte = FONTE_MANUAL
    sessao.flush()
    return indicador


def excluir_indicador(sessao: Session, indicador_id: int) -> None:
    """Exclui um indicador. Transações e eventos já gravados guardam o próprio câmbio,
    então não mudam; avaliações e accrual passam a usar o valor anterior da série."""
    RepositorioIndicadores(sessao).remover(obter_indicador(sessao, indicador_id))


def listar_indicadores(
    sessao: Session,
    tipo: TipoIndicador | None = None,
    moeda: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
) -> Sequence[Indicador]:
    moeda_limpa = validar_moeda(moeda) if moeda else None
    return RepositorioIndicadores(sessao).filtrar(tipo, moeda_limpa, inicio, fim)


def eh_fonte_automatica(fonte: str | None) -> bool:
    return fonte in PRIORIDADE_FONTES_AUTOMATICAS


def gravar_indicadores_automaticos(
    sessao: Session,
    tipo: TipoIndicador,
    moeda: str,
    pontos: Iterable[PontoIndicador],
    fonte: str,
) -> int:
    """Grava pontos vindos de uma fonte automática; devolve quantos foram gravados."""
    prioridade = PRIORIDADE_FONTES_AUTOMATICAS.get(fonte)
    if prioridade is None:
        raise ValueError(f"Fonte automática desconhecida: {fonte}.")
    repositorio = RepositorioIndicadores(sessao)
    existentes = {i.data: i for i in repositorio.filtrar(tipo, validar_moeda(moeda))}
    gravados = 0
    for ponto in pontos:
        moeda = _validar_indicador(tipo, moeda, ponto.data, ponto.valor)
        atual = existentes.get(ponto.data)
        if atual is None:
            existentes[ponto.data] = repositorio.adicionar(
                Indicador(tipo=tipo, moeda=moeda, data=ponto.data, valor=ponto.valor, fonte=fonte)
            )
            gravados += 1
        elif (
            eh_fonte_automatica(atual.fonte)
            and PRIORIDADE_FONTES_AUTOMATICAS[str(atual.fonte)] < prioridade
        ) or (atual.fonte == fonte and atual.valor != ponto.valor):
            atual.valor = ponto.valor
            atual.fonte = fonte
            gravados += 1
    sessao.flush()
    return gravados


def carregar_indicadores(sessao: Session) -> Indicadores:
    pontos: dict[tuple[TipoIndicador, str], list[PontoIndicador]] = defaultdict(list)
    for registro in RepositorioIndicadores(sessao).listar():
        pontos[(registro.tipo, registro.moeda)].append(
            PontoIndicador(registro.data, registro.valor)
        )
    return Indicadores(
        SerieIndicador(tipo, lista, moeda) for (tipo, moeda), lista in pontos.items()
    )
