"""Base dos repositórios: acesso ao banco sem regra de negócio.

Buscas por nome usam a função SQL ``casefold`` registrada em ``core/banco.py``.
Repositórios não fazem ``commit``: quem controla a transação é quem chama
(services dentro de ``sessao_transacional`` ou, na API, a dependência de sessão).
"""

from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.modelos import Base

M = TypeVar("M", bound=Base)


class RepositorioBase(Generic[M]):
    modelo: type[M]

    def __init__(self, sessao: Session) -> None:
        self.sessao = sessao

    def adicionar(self, objeto: M) -> M:
        self.sessao.add(objeto)
        self.sessao.flush()
        return objeto

    def obter(self, identificador: int | str) -> M | None:
        return self.sessao.get(self.modelo, identificador)

    def remover(self, objeto: M) -> None:
        self.sessao.delete(objeto)
        self.sessao.flush()

    def listar(self) -> Sequence[M]:
        return self.sessao.scalars(select(self.modelo)).all()
