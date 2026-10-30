"""Repositórios de transações e de eventos corporativos."""

from collections.abc import Collection, Sequence
from datetime import date

from sqlalchemy import func, or_, select

from app.domain.enums import TipoTransacao
from app.repositories.base import RepositorioBase
from app.repositories.modelos import Ativo, EventoCorporativo, Transacao


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

    def dos_ativos(self, ativo_ids: Collection[int]) -> Sequence[Transacao]:
        consulta = select(Transacao).where(Transacao.ativo_id.in_(ativo_ids))
        return self.sessao.scalars(consulta.order_by(Transacao.data, Transacao.id)).all()

    def filtradas(
        self,
        *,
        ativo_id: int | None = None,
        instituicao_id: int | None = None,
        tipos: Collection[TipoTransacao] | None = None,
        inicio: date | None = None,
        fim: date | None = None,
        tipo_ativo: str | None = None,
        moeda: str | None = None,
        busca: str | None = None,
    ) -> Sequence[Transacao]:
        """Transações que passam pelos filtros simples (os que dependem de cálculo, como
        situação e prejuízo, ficam no service). ``busca`` procura no símbolo e no nome do
        ativo, sem diferenciar maiúsculas nem acentos à parte do ``casefold``."""
        consulta = select(Transacao).join(Ativo, Ativo.id == Transacao.ativo_id)
        if ativo_id is not None:
            consulta = consulta.where(Transacao.ativo_id == ativo_id)
        if instituicao_id is not None:
            consulta = consulta.where(Transacao.instituicao_id == instituicao_id)
        if tipos is not None:
            consulta = consulta.where(Transacao.tipo.in_(list(tipos)))
        if inicio is not None:
            consulta = consulta.where(Transacao.data >= inicio)
        if fim is not None:
            consulta = consulta.where(Transacao.data <= fim)
        if tipo_ativo is not None:
            consulta = consulta.where(Ativo.tipo == tipo_ativo)
        if moeda is not None:
            consulta = consulta.where(Transacao.moeda == moeda)
        if busca:
            literal = busca.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            termo = f"%{literal}%"
            consulta = consulta.where(
                or_(
                    func.casefold(Ativo.simbolo).like(termo, escape="\\"),
                    func.casefold(Ativo.nome).like(termo, escape="\\"),
                )
            )
        return self.sessao.scalars(
            consulta.order_by(Transacao.data.desc(), Transacao.id.desc())
        ).all()

    def existe_do_ativo(self, ativo_id: int) -> bool:
        consulta = select(Transacao.id).where(Transacao.ativo_id == ativo_id).limit(1)
        return self.sessao.scalars(consulta).first() is not None

    def existe_da_instituicao(self, instituicao_id: int) -> bool:
        consulta = select(Transacao.id).where(Transacao.instituicao_id == instituicao_id).limit(1)
        return self.sessao.scalars(consulta).first() is not None

    def pagina(
        self,
        *,
        ativo_id: int | None,
        instituicao_id: int | None,
        tipo: TipoTransacao | None,
        inicio: date | None,
        fim: date | None,
        limite: int,
        deslocamento: int,
    ) -> tuple[Sequence[Transacao], int]:
        """Transações filtradas, da mais recente para a mais antiga, e o total."""
        filtros = []
        if ativo_id is not None:
            filtros.append(Transacao.ativo_id == ativo_id)
        if instituicao_id is not None:
            filtros.append(Transacao.instituicao_id == instituicao_id)
        if tipo is not None:
            filtros.append(Transacao.tipo == tipo)
        if inicio is not None:
            filtros.append(Transacao.data >= inicio)
        if fim is not None:
            filtros.append(Transacao.data <= fim)
        total = self.sessao.scalar(select(func.count()).select_from(Transacao).where(*filtros)) or 0
        consulta = (
            select(Transacao)
            .where(*filtros)
            .order_by(Transacao.data.desc(), Transacao.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return self.sessao.scalars(consulta).all(), total


class RepositorioEventos(RepositorioBase[EventoCorporativo]):
    modelo = EventoCorporativo

    def listar(self) -> Sequence[EventoCorporativo]:
        consulta = select(EventoCorporativo).order_by(
            EventoCorporativo.data.desc(), EventoCorporativo.id.desc()
        )
        return self.sessao.scalars(consulta).all()

    def existe_do_ativo(self, ativo_id: int) -> bool:
        consulta = select(EventoCorporativo.id).where(EventoCorporativo.ativo_id == ativo_id)
        return self.sessao.scalars(consulta.limit(1)).first() is not None

    def dos_ativos(self, ativo_ids: Collection[int]) -> Sequence[EventoCorporativo]:
        consulta = select(EventoCorporativo).where(EventoCorporativo.ativo_id.in_(ativo_ids))
        return self.sessao.scalars(
            consulta.order_by(EventoCorporativo.data, EventoCorporativo.id)
        ).all()

    def do_ativo(self, ativo_id: int, ate: date | None = None) -> Sequence[EventoCorporativo]:
        consulta = select(EventoCorporativo).where(EventoCorporativo.ativo_id == ativo_id)
        if ate is not None:
            consulta = consulta.where(EventoCorporativo.data <= ate)
        return self.sessao.scalars(
            consulta.order_by(EventoCorporativo.data, EventoCorporativo.id)
        ).all()
