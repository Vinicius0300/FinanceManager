"""Casos de uso de cadastro: instituições e ativos (criação, consulta e edição simples).

Edição e exclusão de ativos, que podem exigir reprocessar posições, ficam em
``services/ativos.py``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.asset_types.base import HandlerTipoAtivo
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import TipoInstituicao
from app.domain.erros import (
    ConflitoError,
    DetalheCampo,
    NaoEncontradoError,
    OperacaoNaoPermitidaError,
    ValidacaoError,
)
from app.repositories.ativos import RepositorioAtivos
from app.repositories.contas import RepositorioContas, RepositorioMovimentos
from app.repositories.instituicoes import RepositorioInstituicoes
from app.repositories.modelos import Ativo, Instituicao
from app.repositories.transacoes import RepositorioTransacoes

TAMANHO_NOME_INSTITUICAO = 100
TAMANHO_NOME_ATIVO = 150
TAMANHO_SIMBOLO = 30
TAMANHO_SIMBOLO_EXTERNO = 60


def _texto_obrigatorio(valor: str, campo: str, rotulo: str, tamanho: int) -> str:
    texto = valor.strip()
    if not texto:
        raise ValidacaoError(
            f"{rotulo} é obrigatório.", [DetalheCampo(campo, "Campo obrigatório.")]
        )
    if len(texto) > tamanho:
        mensagem = f"Use no máximo {tamanho} caracteres."
        raise ValidacaoError(f"{rotulo}: {mensagem}", [DetalheCampo(campo, mensagem)])
    return texto


def _texto_opcional(valor: str | None, campo: str, rotulo: str, tamanho: int) -> str | None:
    if valor is None or not valor.strip():
        return None
    return _texto_obrigatorio(valor, campo, rotulo, tamanho)


def criar_instituicao(sessao: Session, nome: str, tipo: TipoInstituicao) -> Instituicao:
    repositorio = RepositorioInstituicoes(sessao)
    nome_limpo = _texto_obrigatorio(nome, "nome", "O nome da instituição", TAMANHO_NOME_INSTITUICAO)
    if repositorio.por_nome(nome_limpo) is not None:
        raise ConflitoError(f"Já existe uma instituição chamada {nome_limpo!r}.")
    return repositorio.adicionar(Instituicao(nome=nome_limpo, tipo=tipo))


def obter_instituicao(sessao: Session, instituicao_id: int) -> Instituicao:
    instituicao = RepositorioInstituicoes(sessao).obter(instituicao_id)
    if instituicao is None:
        raise NaoEncontradoError(f"Instituição {instituicao_id} não encontrada.")
    return instituicao


def listar_instituicoes(sessao: Session) -> Sequence[Instituicao]:
    return RepositorioInstituicoes(sessao).listar()


def editar_instituicao(
    sessao: Session, instituicao_id: int, nome: str, tipo: TipoInstituicao
) -> Instituicao:
    instituicao = obter_instituicao(sessao, instituicao_id)
    nome_limpo = _texto_obrigatorio(nome, "nome", "O nome da instituição", TAMANHO_NOME_INSTITUICAO)
    outra = RepositorioInstituicoes(sessao).por_nome(nome_limpo)
    if outra is not None and outra.id != instituicao.id:
        raise ConflitoError(f"Já existe uma instituição chamada {nome_limpo!r}.")
    instituicao.nome = nome_limpo
    instituicao.tipo = tipo
    sessao.flush()
    return instituicao


def excluir_instituicao(sessao: Session, instituicao_id: int) -> None:
    """Exclui a instituição só se não houver transações nem movimentos de caixa.

    Contas correntes vazias (sem movimentos) são removidas junto.
    """
    instituicao = obter_instituicao(sessao, instituicao_id)
    if RepositorioTransacoes(sessao).existe_da_instituicao(instituicao.id):
        raise OperacaoNaoPermitidaError(
            "A instituição tem transações. Exclua-as antes de excluir a instituição."
        )
    contas = RepositorioContas(sessao)
    movimentos = RepositorioMovimentos(sessao)
    vazias = contas.da_instituicao_todas(instituicao.id)
    if any(movimentos.existe_na_conta(conta.id) for conta in vazias):
        raise OperacaoNaoPermitidaError(
            "A instituição tem depósitos ou saques. Exclua-os antes de excluir a instituição."
        )
    for conta in vazias:
        contas.remover(conta)
    RepositorioInstituicoes(sessao).remover(instituicao)


@dataclass(frozen=True)
class NovoAtivo:
    tipo: str
    nome: str
    simbolo: str | None = None
    moeda: str | None = None  # padrão do tipo se omitida
    simbolo_externo: str | None = None  # símbolo na fonte de cotação (ex.: PETR4.SA)
    metadados: Mapping[str, object] = field(default_factory=dict)


def criar_ativo(
    sessao: Session, dados: NovoAtivo, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> Ativo:
    handler = registro.obter(dados.tipo)
    simbolo = _texto_opcional(dados.simbolo, "simbolo", "O símbolo", TAMANHO_SIMBOLO)
    simbolo = simbolo.upper() if simbolo else None
    repositorio = RepositorioAtivos(sessao)
    if simbolo is not None and repositorio.por_tipo_e_simbolo(handler.slug, simbolo) is not None:
        raise ConflitoError(f"Já existe um ativo {simbolo} do tipo {handler.nome}.")
    ativo = Ativo(
        tipo=handler.slug,
        simbolo=simbolo,
        nome=_texto_obrigatorio(dados.nome, "nome", "O nome do ativo", TAMANHO_NOME_ATIVO),
        moeda=handler.validar_moeda(dados.moeda),
        provider=handler.provider,
        simbolo_externo=_texto_opcional(
            dados.simbolo_externo, "simbolo_externo", "O símbolo externo", TAMANHO_SIMBOLO_EXTERNO
        ),
        metadados=dict(handler.validar_metadados(dados.metadados)),
    )
    return repositorio.adicionar(ativo)


def obter_ativo(sessao: Session, ativo_id: int) -> Ativo:
    ativo = RepositorioAtivos(sessao).obter(ativo_id)
    if ativo is None:
        raise NaoEncontradoError(f"Ativo {ativo_id} não encontrado.")
    return ativo


def listar_ativos(sessao: Session, tipo: str | None = None) -> Sequence[Ativo]:
    ativos = RepositorioAtivos(sessao).listar()
    return [a for a in ativos if a.tipo == tipo] if tipo else ativos


def handler_do_ativo(
    ativo: Ativo, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> HandlerTipoAtivo:
    return registro.obter(ativo.tipo)
