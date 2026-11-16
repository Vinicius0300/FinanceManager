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

    def do_mes(self, ano: int, mes: int, instituicao_id: int | None = None) -> Sequence[Lancamento]:
        inicio = date(ano, mes, 1)
        consulta = select(Lancamento).where(
            Lancamento.data >= inicio, Lancamento.data < primeiro_dia_do_proximo_mes(inicio)
        )
        if instituicao_id is not None:
            consulta = consulta.where(Lancamento.instituicao_id == instituicao_id)
        return self.sessao.scalars(consulta.order_by(Lancamento.data, Lancamento.id)).all()

    def filtrados(
        self,
        *,
        tipo: TipoLancamento | None,
        categoria_id: int | None,
        instituicao_id: int | None,
        inicio: date | None,
        fim: date | None,
    ) -> Sequence[Lancamento]:
        """Lançamentos filtrados, do mais recente para o mais antigo (sem paginar)."""
        filtros = []
        if tipo is not None:
            filtros.append(Lancamento.tipo == tipo)
        if categoria_id is not None:
            filtros.append(Lancamento.categoria_id == categoria_id)
        if instituicao_id is not None:
            filtros.append(Lancamento.instituicao_id == instituicao_id)
        if inicio is not None:
            filtros.append(Lancamento.data >= inicio)
        if fim is not None:
            filtros.append(Lancamento.data <= fim)
        consulta = (
            select(Lancamento)
            .where(*filtros)
            .order_by(Lancamento.data.desc(), Lancamento.id.desc())
        )
        return self.sessao.scalars(consulta).all()

    def existe_na_categoria(self, categoria_id: int) -> bool:
        consulta = select(Lancamento.id).where(Lancamento.categoria_id == categoria_id).limit(1)
        return self.sessao.scalars(consulta).first() is not None

    def existe_da_instituicao(self, instituicao_id: int) -> bool:
        """Só lançamentos do usuário (tarifas de transferência contam pela transferência)."""
        consulta = (
            select(Lancamento.id)
            .where(Lancamento.instituicao_id == instituicao_id)
            .where(Lancamento.transferencia_id.is_(None))
            .limit(1)
        )
        return self.sessao.scalars(consulta).first() is not None
