"""Repositórios de contas correntes e de seus movimentos."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select

from app.repositories.base import RepositorioBase
from app.repositories.modelos import ContaCorrente, MovimentoConta


class RepositorioContas(RepositorioBase[ContaCorrente]):
    modelo = ContaCorrente

    def da_instituicao(self, instituicao_id: int, moeda: str) -> ContaCorrente | None:
        consulta = select(ContaCorrente).where(
            ContaCorrente.instituicao_id == instituicao_id, ContaCorrente.moeda == moeda
        )
        return self.sessao.scalars(consulta).first()

    def listar(self) -> Sequence[ContaCorrente]:
        consulta = select(ContaCorrente).order_by(ContaCorrente.instituicao_id, ContaCorrente.moeda)
        return self.sessao.scalars(consulta).all()


class RepositorioMovimentos(RepositorioBase[MovimentoConta]):
    modelo = MovimentoConta

    def da_conta(self, conta_id: int, ate: date | None = None) -> Sequence[MovimentoConta]:
        consulta = select(MovimentoConta).where(MovimentoConta.conta_id == conta_id)
        if ate is not None:
            consulta = consulta.where(MovimentoConta.data <= ate)
        return self.sessao.scalars(consulta.order_by(MovimentoConta.data, MovimentoConta.id)).all()

    def da_transacao(self, transacao_id: int) -> Sequence[MovimentoConta]:
        consulta = select(MovimentoConta).where(MovimentoConta.transacao_id == transacao_id)
        return self.sessao.scalars(consulta.order_by(MovimentoConta.id)).all()
