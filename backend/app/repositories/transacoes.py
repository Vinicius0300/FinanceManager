"""Repositórios de transações e de eventos corporativos."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select

from app.repositories.base import RepositorioBase
from app.repositories.modelos import EventoCorporativo, Transacao


class RepositorioTransacoes(RepositorioBase[Transacao]):
    modelo = Transacao

    def da_posicao(
        self, ativo_id: int, instituicao_id: int, ate: date | None = None
    ) -> Sequence[Transacao]:
        consulta = select(Transacao).where(
            Transacao.ativo_id == ativo_id, Transacao.instituicao_id == instituicao_id
        )
        if ate is not None:
            consulta = consulta.where(Transacao.data <= ate)
        return self.sessao.scalars(consulta.order_by(Transacao.data, Transacao.id)).all()

    def listar_ate(self, ate: date | None = None) -> Sequence[Transacao]:
        consulta = select(Transacao)
        if ate is not None:
            consulta = consulta.where(Transacao.data <= ate)
        return self.sessao.scalars(consulta.order_by(Transacao.data, Transacao.id)).all()

    def do_ativo(self, ativo_id: int) -> Sequence[Transacao]:
        consulta = select(Transacao).where(Transacao.ativo_id == ativo_id)
        return self.sessao.scalars(consulta.order_by(Transacao.data, Transacao.id)).all()


class RepositorioEventos(RepositorioBase[EventoCorporativo]):
    modelo = EventoCorporativo

    def do_ativo(self, ativo_id: int, ate: date | None = None) -> Sequence[EventoCorporativo]:
        consulta = select(EventoCorporativo).where(EventoCorporativo.ativo_id == ativo_id)
        if ate is not None:
            consulta = consulta.where(EventoCorporativo.data <= ate)
        return self.sessao.scalars(
            consulta.order_by(EventoCorporativo.data, EventoCorporativo.id)
        ).all()
