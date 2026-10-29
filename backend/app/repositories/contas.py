"""Repositórios de contas correntes e de seus movimentos."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select

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

    def da_instituicao_todas(self, instituicao_id: int) -> Sequence[ContaCorrente]:
        consulta = select(ContaCorrente).where(ContaCorrente.instituicao_id == instituicao_id)
        return self.sessao.scalars(consulta.order_by(ContaCorrente.moeda)).all()


class RepositorioMovimentos(RepositorioBase[MovimentoConta]):
    modelo = MovimentoConta

    def da_conta(self, conta_id: int, ate: date | None = None) -> Sequence[MovimentoConta]:
        consulta = select(MovimentoConta).where(MovimentoConta.conta_id == conta_id)
        if ate is not None:
            consulta = consulta.where(MovimentoConta.data <= ate)
        return self.sessao.scalars(consulta.order_by(MovimentoConta.data, MovimentoConta.id)).all()

    def existe_na_conta(self, conta_id: int) -> bool:
        consulta = select(MovimentoConta.id).where(MovimentoConta.conta_id == conta_id).limit(1)
        return self.sessao.scalars(consulta).first() is not None

    def pagina(
        self,
        conta_id: int,
        inicio: date | None,
        fim: date | None,
        limite: int,
        deslocamento: int,
    ) -> tuple[Sequence[MovimentoConta], int]:
        """Movimentos da conta, do mais recente para o mais antigo, e o total."""
        filtros = [MovimentoConta.conta_id == conta_id]
        if inicio is not None:
            filtros.append(MovimentoConta.data >= inicio)
        if fim is not None:
            filtros.append(MovimentoConta.data <= fim)
        total = (
            self.sessao.scalar(select(func.count()).select_from(MovimentoConta).where(*filtros))
            or 0
        )
        consulta = (
            select(MovimentoConta)
            .where(*filtros)
            .order_by(MovimentoConta.data.desc(), MovimentoConta.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return self.sessao.scalars(consulta).all(), total

    def da_transacao(self, transacao_id: int) -> Sequence[MovimentoConta]:
        consulta = select(MovimentoConta).where(MovimentoConta.transacao_id == transacao_id)
        return self.sessao.scalars(consulta.order_by(MovimentoConta.id)).all()
