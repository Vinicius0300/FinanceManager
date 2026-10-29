"""Criptomoedas (cotadas em BRL ou USD, quantidade com até 8 casas na apresentação)."""

from datetime import timedelta
from typing import ClassVar

from app.asset_types.base import HandlerCotado
from app.domain.enums import TipoTransacao


class Cripto(HandlerCotado):
    slug = "cripto"
    nome = "Criptomoeda"
    descricao = "Criptoativos como bitcoin e ethereum; negociados 24 horas por dia."
    moedas_aceitas = ("BRL", "USD")
    provider = "coingecko"
    tipos_transacao: ClassVar[frozenset[TipoTransacao]] = frozenset(
        {TipoTransacao.COMPRA, TipoTransacao.VENDA}
    )
    # Mercado sem fechamento: preço com mais de um dia já é considerado defasado.
    tolerancia_defasagem: ClassVar[timedelta] = timedelta(days=1)
