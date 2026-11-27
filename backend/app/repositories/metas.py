"""Repositório das metas de alocação (classes e pesos por ativo), sem regra de negócio."""

from collections.abc import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.repositories.modelos import Ativo, MetaAtivo, MetaClasse


class RepositorioMetas:
    def __init__(self, sessao: Session) -> None:
        self.sessao = sessao

    def classes(self) -> Sequence[MetaClasse]:
        return self.sessao.scalars(select(MetaClasse).order_by(MetaClasse.tipo_ativo)).all()

    def ativos(self) -> Sequence[tuple[MetaAtivo, Ativo]]:
        """Pesos com o ativo de cada um (para saber a classe)."""
        consulta = (
            select(MetaAtivo, Ativo)
            .join(Ativo, Ativo.id == MetaAtivo.ativo_id)
            .order_by(MetaAtivo.ativo_id)
        )
        return [(meta, ativo) for meta, ativo in self.sessao.execute(consulta).all()]

    def substituir(self, classes: Iterable[MetaClasse], ativos: Iterable[MetaAtivo]) -> None:
        """Apaga todas as metas e grava as novas (na transação de quem chama)."""
        self.sessao.execute(delete(MetaAtivo))
        self.sessao.execute(delete(MetaClasse))
        self.sessao.add_all(list(classes))
        self.sessao.add_all(list(ativos))
        self.sessao.flush()
