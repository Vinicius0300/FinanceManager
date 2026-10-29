"""Repositórios de categorias e lançamentos (receitas e despesas)."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select

from app.domain.enums import TipoLancamento
from app.domain.tempo import primeiro_dia_do_proximo_mes
from app.repositories.base import RepositorioBase
from app.repositories.modelos import Categoria, Lancamento


class RepositorioCategorias(RepositorioBase[Categoria]):
    modelo = Categoria

    def por_nome(self, nome: str, tipo: TipoLancamento) -> Categoria | None:
        consulta = select(Categoria).where(
            func.casefold(Categoria.nome) == nome.casefold(), Categoria.tipo == tipo
        )
        return self.sessao.scalars(consulta).first()

    def listar(self) -> Sequence[Categoria]:
        consulta = select(Categoria).order_by(Categoria.tipo, Categoria.nome)
        return self.sessao.scalars(consulta).all()


class RepositorioLancamentos(RepositorioBase[Lancamento]):
    modelo = Lancamento

    def do_mes(self, ano: int, mes: int) -> Sequence[Lancamento]:
        inicio = date(ano, mes, 1)
        consulta = select(Lancamento).where(
            Lancamento.data >= inicio, Lancamento.data < primeiro_dia_do_proximo_mes(inicio)
        )
        return self.sessao.scalars(consulta.order_by(Lancamento.data, Lancamento.id)).all()

    def existe_na_categoria(self, categoria_id: int) -> bool:
        consulta = select(Lancamento.id).where(Lancamento.categoria_id == categoria_id).limit(1)
        return self.sessao.scalars(consulta).first() is not None
