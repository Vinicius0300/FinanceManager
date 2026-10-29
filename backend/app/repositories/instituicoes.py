"""Repositório de instituições (onde o dinheiro está alocado)."""

from collections.abc import Sequence

from sqlalchemy import func, select

from app.repositories.base import RepositorioBase
from app.repositories.modelos import Instituicao


class RepositorioInstituicoes(RepositorioBase[Instituicao]):
    modelo = Instituicao

    def por_nome(self, nome: str) -> Instituicao | None:
        consulta = select(Instituicao).where(func.casefold(Instituicao.nome) == nome.casefold())
        return self.sessao.scalars(consulta).first()

    def listar(self) -> Sequence[Instituicao]:
        return self.sessao.scalars(select(Instituicao).order_by(Instituicao.nome)).all()
