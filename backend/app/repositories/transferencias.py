"""Repositório de transferências entre instituições."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select

from app.repositories.base import RepositorioBase
from app.repositories.modelos import Transferencia


class RepositorioTransferencias(RepositorioBase[Transferencia]):
    modelo = Transferencia

    def filtradas(
        self,
        *,
        instituicao_id: int | None = None,
        moeda: str | None = None,
        inicio: date | None = None,
        fim: date | None = None,
    ) -> Sequence[Transferencia]:
        """Transferências filtradas, da mais recente para a mais antiga.

        ``instituicao_id`` casa com a origem ou com o destino.
        """
        filtros = []
        if instituicao_id is not None:
            filtros.append(
                or_(
                    Transferencia.origem_id == instituicao_id,
                    Transferencia.destino_id == instituicao_id,
                )
            )
        if moeda is not None:
            filtros.append(Transferencia.moeda == moeda)
        if inicio is not None:
            filtros.append(Transferencia.data >= inicio)
        if fim is not None:
            filtros.append(Transferencia.data <= fim)
        consulta = (
            select(Transferencia)
            .where(*filtros)
            .order_by(Transferencia.data.desc(), Transferencia.id.desc())
        )
        return self.sessao.scalars(consulta).all()

    def existe_da_instituicao(self, instituicao_id: int) -> bool:
        return bool(self.filtradas(instituicao_id=instituicao_id))
