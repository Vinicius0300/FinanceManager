"""Repositórios de dados de mercado: preços, indicadores e estado da coleta automática."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select

from app.domain.enums import TipoIndicador
from app.repositories.base import RepositorioBase
from app.repositories.modelos import EstadoColeta, Indicador, Preco


class RepositorioPrecos(RepositorioBase[Preco]):
    modelo = Preco

    def do_ativo(
        self, ativo_id: int, inicio: date | None = None, fim: date | None = None
    ) -> Sequence[Preco]:
        consulta = select(Preco).where(Preco.ativo_id == ativo_id)
        if inicio is not None:
            consulta = consulta.where(Preco.data >= inicio)
        if fim is not None:
            consulta = consulta.where(Preco.data <= fim)
        return self.sessao.scalars(consulta.order_by(Preco.data)).all()

    def na_data(self, ativo_id: int, data: date) -> Preco | None:
        consulta = select(Preco).where(Preco.ativo_id == ativo_id, Preco.data == data)
        return self.sessao.scalars(consulta).first()

    def ultimos(self, ativo_id: int, quantidade: int) -> Sequence[Preco]:
        """Os ``quantidade`` preços mais recentes, do mais novo para o mais antigo."""
        consulta = select(Preco).where(Preco.ativo_id == ativo_id)
        return self.sessao.scalars(consulta.order_by(Preco.data.desc()).limit(quantidade)).all()

    def pagina(
        self, ativo_id: int, inicio: date | None, fim: date | None, limite: int, deslocamento: int
    ) -> tuple[Sequence[Preco], int]:
        """Página de preços do mais novo para o mais antigo e o total de registros."""
        filtros = [Preco.ativo_id == ativo_id]
        if inicio is not None:
            filtros.append(Preco.data >= inicio)
        if fim is not None:
            filtros.append(Preco.data <= fim)
        total = self.sessao.scalar(select(func.count()).select_from(Preco).where(*filtros)) or 0
        consulta = (
            select(Preco)
            .where(*filtros)
            .order_by(Preco.data.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return self.sessao.scalars(consulta).all(), total


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

    def filtrar(
        self,
        tipo: TipoIndicador | None = None,
        moeda: str | None = None,
        inicio: date | None = None,
        fim: date | None = None,
    ) -> Sequence[Indicador]:
        consulta = select(Indicador)
        if tipo is not None:
            consulta = consulta.where(Indicador.tipo == tipo)
        if moeda is not None:
            consulta = consulta.where(Indicador.moeda == moeda)
        if inicio is not None:
            consulta = consulta.where(Indicador.data >= inicio)
        if fim is not None:
            consulta = consulta.where(Indicador.data <= fim)
        return self.sessao.scalars(
            consulta.order_by(Indicador.tipo, Indicador.moeda, Indicador.data)
        ).all()

    def ultima_data(self, tipo: TipoIndicador, moeda: str) -> date | None:
        consulta = select(func.max(Indicador.data)).where(
            Indicador.tipo == tipo, Indicador.moeda == moeda
        )
        return self.sessao.scalar(consulta)


class RepositorioEstadosColeta(RepositorioBase[EstadoColeta]):
    modelo = EstadoColeta

    def obter_ou_criar(self, chave: str, ativo_id: int | None = None) -> EstadoColeta:
        estado = self.obter(chave)
        if estado is None:
            estado = self.adicionar(EstadoColeta(chave=chave, ativo_id=ativo_id))
        return estado

    def de_ativos(self) -> dict[int, EstadoColeta]:
        consulta = select(EstadoColeta).where(EstadoColeta.ativo_id.is_not(None))
        return {e.ativo_id: e for e in self.sessao.scalars(consulta) if e.ativo_id is not None}

    def listar(self) -> Sequence[EstadoColeta]:
        return self.sessao.scalars(select(EstadoColeta).order_by(EstadoColeta.chave)).all()
