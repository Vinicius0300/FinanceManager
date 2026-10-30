"""Registry de providers: cotação por nome (``ativos.provider``) e indicadores por prioridade."""

from collections.abc import Callable

from app.domain.enums import TipoIndicador
from app.providers.base import (
    FonteListaSimbolos,
    ProviderBusca,
    ProviderCotacao,
    ProviderIndicador,
)


class RegistroProviders:
    def __init__(self) -> None:
        self._cotacao: dict[str, ProviderCotacao] = {}
        self._indicadores: list[ProviderIndicador] = []
        self._cambio_intradiario: ProviderIndicador | None = None
        self._ao_fechar: list[Callable[[], None]] = []
        self._listas: dict[str, FonteListaSimbolos] = {}
        self._buscas: dict[str, ProviderBusca] = {}

    def registrar_cotacao(self, provider: ProviderCotacao) -> None:
        if provider.nome in self._cotacao:
            raise ValueError(f"Provider de cotação já registrado: {provider.nome}.")
        self._cotacao[provider.nome] = provider

    def registrar_indicador(self, provider: ProviderIndicador) -> None:
        """Registra uma fonte de indicadores; a ordem de registro é a ordem de preferência."""
        if any(p.nome == provider.nome for p in self._indicadores):
            raise ValueError(f"Provider de indicadores já registrado: {provider.nome}.")
        self._indicadores.append(provider)

    def registrar_cambio_intradiario(self, provider: ProviderIndicador) -> None:
        """Fonte do câmbio ao longo do dia (a PTAX oficial só sai uma vez por dia)."""
        self._cambio_intradiario = provider

    @property
    def cambio_intradiario(self) -> ProviderIndicador | None:
        return self._cambio_intradiario

    def registrar_lista(self, fonte: FonteListaSimbolos) -> None:
        """Fonte da lista oficial de tickers de uma bolsa (uma por bolsa)."""
        if fonte.bolsa in self._listas:
            raise ValueError(f"Lista de símbolos já registrada: {fonte.bolsa}.")
        self._listas[fonte.bolsa] = fonte

    def lista(self, bolsa: str) -> FonteListaSimbolos | None:
        return self._listas.get(bolsa)

    @property
    def bolsas(self) -> list[str]:
        return sorted(self._listas)

    def registrar_busca(self, busca: ProviderBusca) -> None:
        """Pesquisa por texto da fonte ``busca.nome`` (mesmo nome do provider de cotação)."""
        if busca.nome in self._buscas:
            raise ValueError(f"Pesquisa já registrada: {busca.nome}.")
        self._buscas[busca.nome] = busca

    def busca(self, nome: str | None) -> ProviderBusca | None:
        return self._buscas.get(nome) if nome else None

    def ao_fechar(self, acao: Callable[[], None]) -> None:
        self._ao_fechar.append(acao)

    def cotacao(self, nome: str) -> ProviderCotacao | None:
        return self._cotacao.get(nome)

    @property
    def nomes_cotacao(self) -> list[str]:
        return sorted(self._cotacao)

    def fontes_indicador(self, tipo: TipoIndicador, moeda: str) -> list[ProviderIndicador]:
        """Fontes que fornecem o indicador, da preferida para a reserva (fallback)."""
        return [p for p in self._indicadores if p.suporta(tipo, moeda)]

    def fechar(self) -> None:
        for acao in self._ao_fechar:
            acao()
