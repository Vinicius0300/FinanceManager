"""Repositórios das listas oficiais de tickers (sem regra de negócio)."""

from collections.abc import Iterable, Sequence

from sqlalchemy import delete, func, or_, select

from app.repositories.base import RepositorioBase
from app.repositories.modelos import ListaSimbolos, SimboloListado


class RepositorioListasSimbolos(RepositorioBase[ListaSimbolos]):
    modelo = ListaSimbolos

    def obter_ou_criar(self, bolsa: str) -> ListaSimbolos:
        lista = self.obter(bolsa)
        if lista is None:
            lista = self.adicionar(ListaSimbolos(bolsa=bolsa, quantidade=0))
        return lista

    def listar(self) -> Sequence[ListaSimbolos]:
        return self.sessao.scalars(select(ListaSimbolos).order_by(ListaSimbolos.bolsa)).all()


class RepositorioSimbolosListados(RepositorioBase[SimboloListado]):
    modelo = SimboloListado

    def substituir_bolsa(self, bolsa: str, itens: Iterable[SimboloListado]) -> int:
        """Troca a lista inteira da bolsa (na transação de quem chama)."""
        self.sessao.execute(delete(SimboloListado).where(SimboloListado.bolsa == bolsa))
        novos = list(itens)
        self.sessao.add_all(novos)
        self.sessao.flush()
        return len(novos)

    def por_simbolo(self, bolsa: str, simbolo: str) -> SimboloListado | None:
        consulta = select(SimboloListado).where(
            SimboloListado.bolsa == bolsa, SimboloListado.simbolo == simbolo
        )
        return self.sessao.scalars(consulta).first()

    def buscar(self, bolsa: str, ticker: str, texto: str, limite: int) -> Sequence[SimboloListado]:
        """Ticker começando por ``ticker`` ou nome contendo ``texto`` (sem diferenciar maiúsculas).

        Ticker exato primeiro, depois os que começam por ele, depois por nome.
        """
        prefixo = ticker + "%"
        contem = "%" + texto.casefold() + "%"
        exato = SimboloListado.simbolo == ticker
        comeca = SimboloListado.simbolo.like(prefixo)
        consulta = (
            select(SimboloListado)
            .where(
                SimboloListado.bolsa == bolsa,
                or_(comeca, func.casefold(SimboloListado.nome).like(contem)),
            )
            .order_by(exato.desc(), comeca.desc(), SimboloListado.simbolo)
            .limit(limite)
        )
        return self.sessao.scalars(consulta).all()
