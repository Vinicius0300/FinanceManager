"""Criptomoedas (cotadas em BRL ou USD, quantidade com até 8 casas na apresentação)."""

from datetime import timedelta
from typing import ClassVar

from app.asset_types.base import HandlerCotado, Identidade
from app.domain.agenda import AGENDA_CONTINUA, Agenda
from app.domain.enums import TipoTransacao


class Cripto(HandlerCotado):
    slug = "cripto"
    nome = "Criptomoeda"
    descricao = "Criptoativos como bitcoin e ethereum; negociados 24 horas por dia."
    moedas_aceitas = ("BRL", "USD")
    agenda: ClassVar[Agenda] = AGENDA_CONTINUA
    provider = "coingecko"
    tipos_transacao: ClassVar[frozenset[TipoTransacao]] = frozenset(
        {TipoTransacao.COMPRA, TipoTransacao.VENDA}
    )
    # Mercado sem fechamento: preço com mais de um dia já é considerado defasado.
    tolerancia_defasagem: ClassVar[timedelta] = timedelta(days=1)
    busca_por_ticker: ClassVar[bool] = True

    def mesma_identidade(self, a: Identidade, b: Identidade) -> bool:
        """Mesmo id da CoinGecko; se algum ainda não tem id, o mesmo símbolo (BTC = btc)."""
        id_a = (a.simbolo_externo or "").strip().lower()
        id_b = (b.simbolo_externo or "").strip().lower()
        if id_a and id_b:
            return id_a == id_b
        if a.simbolo and b.simbolo:
            return self.normalizar_simbolo(a.simbolo) == self.normalizar_simbolo(b.simbolo)
        return False
