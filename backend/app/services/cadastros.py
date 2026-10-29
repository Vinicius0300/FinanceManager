"""Casos de uso de cadastro: instituições e ativos."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.asset_types.base import HandlerTipoAtivo
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import TipoInstituicao
from app.domain.erros import ConflitoError, DetalheCampo, NaoEncontradoError, ValidacaoError
from app.repositories.ativos import RepositorioAtivos
from app.repositories.instituicoes import RepositorioInstituicoes
from app.repositories.modelos import Ativo, Instituicao

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


def handler_do_ativo(
    ativo: Ativo, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> HandlerTipoAtivo:
    return registro.obter(ativo.tipo)
