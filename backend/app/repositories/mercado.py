"""Repositórios de dados de mercado: preços e indicadores."""

from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select

from app.domain.enums import TipoIndicador
from app.repositories.base import RepositorioBase
from app.repositories.modelos import Indicador, Preco


class RepositorioPrecos(RepositorioBase[Preco]):
    modelo = Preco

    def do_ativo(self, ativo_id: int) -> Sequence[Preco]:
        consulta = select(Preco).where(Preco.ativo_id == ativo_id)
        return self.sessao.scalars(consulta.order_by(Preco.data_hora)).all()

    def no_instante(self, ativo_id: int, data_hora: datetime) -> Preco | None:
        consulta = select(Preco).where(Preco.ativo_id == ativo_id, Preco.data_hora == data_hora)
        return self.sessao.scalars(consulta).first()


class RepositorioIndicadores(RepositorioBase[Indicador]):
    modelo = Indicador

    def na_data(self, tipo: TipoIndicador, moeda: str, data: date) -> Indicador | None:
        consulta = select(Indicador).where(
            Indicador.tipo == tipo, Indicador.moeda == moeda, Indicador.data == data
        )
        return self.sessao.scalars(consulta).first()

    def listar(self) -> Sequence[Indicador]:
        consulta = select(Indicador).order_by(Indicador.tipo, Indicador.moeda, Indicador.data)
        return self.sessao.scalars(consulta).all()
