"""Edição e exclusão de ativos.

- **Editar:** só nome, símbolo externo e campos específicos. Tipo e moeda não mudam (eles
  definem como as posições são calculadas). Mudança nos campos específicos que afete o
  cálculo (ex.: taxa ou data de aplicação da renda fixa) reprocessa as posições e é
  recusada se alguma transação ficar inválida.
- Mudança na **identificação na fonte** de um ativo cotado (símbolo externo ou campos de
  ``campos_identificacao``, como o CNPJ do fundo) apaga os preços automáticos e o estado
  da coleta: os preços antigos eram de outro papel, e o histórico é baixado de novo.
  Preços manuais ficam.
- **Excluir:** só sem transações nem eventos corporativos (preços e estado da coleta vão
  junto, por ``ON DELETE CASCADE``).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.asset_types.base import HandlerCotado
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import OrigemPreco
from app.domain.erros import DominioError, OperacaoNaoPermitidaError
from app.repositories import modelos as m
from app.repositories.ativos import RepositorioAtivos
from app.repositories.mercado import RepositorioEstadosColeta, RepositorioPrecos
from app.repositories.transacoes import RepositorioEventos, RepositorioTransacoes
from app.services.cadastros import (
    TAMANHO_NOME_ATIVO,
    TAMANHO_SIMBOLO_EXTERNO,
    _texto_obrigatorio,
    _texto_opcional,
    handler_do_ativo,
    obter_ativo,
    simbolo_externo_efetivo,
)
from app.services.coleta import chave_ativo
from app.services.mercado import carregar_indicadores
from app.services.posicoes import reprocessar_ativo


@dataclass(frozen=True)
class EdicaoAtivo:
    nome: str
    simbolo_externo: str | None = None
    metadados: Mapping[str, object] = field(default_factory=dict)


def _validar_operacoes(
    sessao: Session, ativo: m.Ativo, metadados: dict[str, str | int], registro: RegistroTiposAtivo
) -> None:
    handler = handler_do_ativo(ativo, registro)
    transacoes = list(RepositorioTransacoes(sessao).do_ativo(ativo.id))
    eventos = list(RepositorioEventos(sessao).do_ativo(ativo.id))
    simulado = m.Ativo(id=ativo.id, tipo=ativo.tipo, moeda=ativo.moeda, metadados=metadados)
    try:
        for transacao in transacoes:
            handler.validar_transacao(metadados, transacao.tipo, transacao.data)
        reprocessar_ativo(simulado, handler, transacoes, eventos, carregar_indicadores(sessao))
    except DominioError as erro:
        raise OperacaoNaoPermitidaError(
            f"Não é possível alterar os dados do ativo: {erro.mensagem}"
        ) from erro


def _reiniciar_coleta(sessao: Session, ativo: m.Ativo) -> None:
    precos = RepositorioPrecos(sessao)
    for preco in precos.do_ativo(ativo.id):
        if preco.origem is OrigemPreco.AUTOMATICO:
            precos.remover(preco)
    estados = RepositorioEstadosColeta(sessao)
    estado = estados.obter(chave_ativo(ativo.id))
    if estado is not None:
        estados.remover(estado)


def editar_ativo(
    sessao: Session,
    ativo_id: int,
    dados: EdicaoAtivo,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> m.Ativo:
    ativo = obter_ativo(sessao, ativo_id)
    handler = handler_do_ativo(ativo, registro)
    nome = _texto_obrigatorio(dados.nome, "nome", "O nome do ativo", TAMANHO_NOME_ATIVO)
    informado = _texto_opcional(
        dados.simbolo_externo, "simbolo_externo", "O símbolo externo", TAMANHO_SIMBOLO_EXTERNO
    )
    externo = simbolo_externo_efetivo(handler, informado, ativo.simbolo)
    anterior = simbolo_externo_efetivo(handler, ativo.simbolo_externo, ativo.simbolo)
    metadados = dict(handler.validar_metadados(dados.metadados))
    if metadados != ativo.metadados:
        _validar_operacoes(sessao, ativo, metadados, registro)
    identificacao_mudou = externo != anterior or any(
        metadados.get(campo) != ativo.metadados.get(campo) for campo in handler.campos_identificacao
    )
    ativo.nome = nome
    ativo.simbolo_externo = externo
    ativo.metadados = metadados
    if identificacao_mudou and isinstance(handler, HandlerCotado):
        _reiniciar_coleta(sessao, ativo)
    sessao.flush()
    return ativo


def excluir_ativo(sessao: Session, ativo_id: int) -> None:
    ativo = obter_ativo(sessao, ativo_id)
    if RepositorioTransacoes(sessao).existe_do_ativo(ativo.id):
        raise OperacaoNaoPermitidaError(
            "O ativo tem transações. Exclua-as antes de excluir o ativo."
        )
    if RepositorioEventos(sessao).existe_do_ativo(ativo.id):
        raise OperacaoNaoPermitidaError(
            "O ativo tem eventos corporativos. Exclua-os antes de excluir o ativo."
        )
    RepositorioAtivos(sessao).remover(ativo)
