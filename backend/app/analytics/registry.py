"""Registry de modelos versionados (preditores e estratégias).

Um modelo é registrado por ``(nome, versão)`` com uma **fábrica** (callable sem
argumentos). A fábrica só roda ao pedir o modelo, então uma implementação que dependa
de bibliotecas pesadas e opcionais pode importá-las dentro da fábrica: se a biblioteca
não estiver instalada, só aquele modelo fica indisponível, com mensagem em pt-BR.

Versões seguem ``MAJOR.MINOR.PATCH`` (números inteiros) e "a mais recente" é a maior.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.analytics.protocolos import Predictor, Strategy

ModeloAnalitico = Predictor | Strategy
FabricaModelo = Callable[[], ModeloAnalitico]

_PADRAO_VERSAO = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class ModeloIndisponivelError(Exception):
    """Modelo não registrado ou com dependência opcional ausente."""


def chave_versao(versao: str) -> tuple[int, int, int]:
    combinacao = _PADRAO_VERSAO.match(versao)
    if combinacao is None:
        raise ValueError(f"Versão inválida: {versao!r}. Use MAJOR.MINOR.PATCH (ex.: 1.0.0).")
    major, minor, patch = (int(parte) for parte in combinacao.groups())
    return (major, minor, patch)


@dataclass(frozen=True)
class RegistroModelo:
    nome: str
    versao: str
    descricao: str
    fabrica: FabricaModelo


class RegistroModelos:
    def __init__(self) -> None:
        self._modelos: dict[tuple[str, str], RegistroModelo] = {}

    def registrar(
        self, nome: str, versao: str, fabrica: FabricaModelo, descricao: str = ""
    ) -> None:
        chave_versao(versao)
        if (nome, versao) in self._modelos:
            raise ValueError(f"Modelo {nome} {versao} já registrado.")
        self._modelos[(nome, versao)] = RegistroModelo(nome, versao, descricao, fabrica)

    def versoes(self, nome: str) -> list[str]:
        return sorted((v for n, v in self._modelos if n == nome), key=chave_versao)

    def listar(self) -> list[RegistroModelo]:
        return sorted(self._modelos.values(), key=lambda r: (r.nome, chave_versao(r.versao)))

    def obter(self, nome: str, versao: str | None = None) -> ModeloAnalitico:
        """Instancia o modelo pedido (ou a versão mais recente)."""
        versoes = self.versoes(nome)
        if not versoes:
            raise ModeloIndisponivelError(f"Modelo {nome!r} não registrado.")
        escolhida = versao or versoes[-1]
        registro = self._modelos.get((nome, escolhida))
        if registro is None:
            raise ModeloIndisponivelError(f"Versão {escolhida} do modelo {nome!r} não existe.")
        try:
            return registro.fabrica()
        except ImportError as erro:
            raise ModeloIndisponivelError(
                f"O modelo {nome} {escolhida} precisa de um componente opcional que não está "
                f"instalado ({erro.name or erro})."
            ) from erro


REGISTRO_MODELOS = RegistroModelos()
"""Registro global: vazio nesta fase (nenhum modelo implementado)."""
