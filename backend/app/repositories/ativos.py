"""Repositório de ativos."""

from collections.abc import Sequence

from sqlalchemy import select

from app.repositories.base import RepositorioBase
from app.repositories.modelos import Ativo


class RepositorioAtivos(RepositorioBase[Ativo]):
    modelo = Ativo

    def por_tipo_e_simbolo(self, tipo: str, simbolo: str) -> Ativo | None:
        consulta = select(Ativo).where(Ativo.tipo == tipo, Ativo.simbolo == simbolo)
        return self.sessao.scalars(consulta).first()

    def listar(self) -> Sequence[Ativo]:
        return self.sessao.scalars(select(Ativo).order_by(Ativo.id)).all()
