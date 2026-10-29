"""Ponto único de registro dos providers (fontes de cotação e de indicadores).

Para adicionar uma fonte, crie a classe em um arquivo próprio implementando
``ProviderCotacao`` e/ou ``ProviderIndicador`` e registre-a aqui. O nome
(``provider.nome``) é o mesmo gravado em ``ativos.provider`` pelo tipo de ativo.

Fallback de indicadores pela ordem de registro: **câmbio** PTAX (SGS) → Yahoo.
O Yahoo também fornece o dólar **ao longo do dia** (a PTAX sai uma vez por dia).
"""

import time
from collections.abc import Callable
from datetime import date

import httpx2

from app.domain.tempo import hoje_local
from app.providers.coingecko import ProviderCoinGecko
from app.providers.cvm import ProviderCvm
from app.providers.http import ClienteHttp
from app.providers.registry import RegistroProviders
from app.providers.sgs import ProviderSgs
from app.providers.tesouro import ProviderTesouro
from app.providers.yahoo import ProviderYahoo

INTERVALO_COINGECKO_S = 4.0  # plano público: poucas chamadas por minuto
INTERVALO_YAHOO_S = 0.3
INTERVALO_PADRAO_S = 0.2


def criar_registro_providers(
    *,
    transporte: httpx2.BaseTransport | None = None,
    dormir: Callable[[float], None] = time.sleep,
    relogio: Callable[[], float] = time.monotonic,
    hoje: Callable[[], date] = hoje_local,
) -> RegistroProviders:
    """Cria o registro padrão. ``transporte``/``dormir``/``relogio``/``hoje`` são para testes."""

    def cliente(fonte: str, intervalo: float) -> ClienteHttp:
        http = ClienteHttp(
            fonte,
            transporte=transporte,
            intervalo_minimo=intervalo,
            dormir=dormir,
            relogio=relogio,
        )
        registro.ao_fechar(http.fechar)
        return http

    registro = RegistroProviders()
    yahoo = ProviderYahoo(cliente("Yahoo Finance", INTERVALO_YAHOO_S))
    registro.registrar_cotacao(yahoo)
    registro.registrar_cotacao(ProviderCoinGecko(cliente("CoinGecko", INTERVALO_COINGECKO_S)))
    registro.registrar_cotacao(ProviderTesouro(cliente("Tesouro Transparente", INTERVALO_PADRAO_S)))
    registro.registrar_cotacao(
        ProviderCvm(cliente("CVM", INTERVALO_PADRAO_S), hoje=hoje, relogio=relogio)
    )
    registro.registrar_indicador(ProviderSgs(cliente("Banco Central (SGS)", INTERVALO_PADRAO_S)))
    registro.registrar_indicador(yahoo)  # reserva do câmbio
    registro.registrar_cambio_intradiario(yahoo)  # dólar ao longo do dia
    return registro
