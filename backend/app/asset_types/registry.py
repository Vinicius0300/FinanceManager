"""Registry de handlers de tipo de ativo (consulta por slug)."""

import re

from app.asset_types.base import HandlerCotado, HandlerMontante, HandlerTipoAtivo
from app.domain.erros import DetalheCampo, ValidacaoError

_PADRAO_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class RegistroTiposAtivo:
    def __init__(self) -> None:
        self._handlers: dict[str, HandlerTipoAtivo] = {}

    def registrar(self, handler: HandlerTipoAtivo) -> HandlerTipoAtivo:
        slug = handler.slug
        if not _PADRAO_SLUG.match(slug):
            raise ValueError(f"Slug de tipo de ativo inválido: {slug!r}.")
        if slug in self._handlers:
            raise ValueError(f"Tipo de ativo já registrado: {slug!r}.")
        if not isinstance(handler, HandlerCotado | HandlerMontante):
            raise ValueError(f"O tipo {slug!r} deve herdar de HandlerCotado ou HandlerMontante.")
        if not handler.moedas_aceitas:
            raise ValueError(f"O tipo {slug!r} precisa aceitar ao menos uma moeda.")
        self._handlers[slug] = handler
        return handler

    def obter(self, slug: str) -> HandlerTipoAtivo:
        handler = self._handlers.get(slug)
        if handler is None:
            mensagem = f"Tipo de ativo desconhecido: {slug!r}."
            raise ValidacaoError(mensagem, [DetalheCampo("tipo", mensagem)])
        return handler

    def __contains__(self, slug: object) -> bool:
        return slug in self._handlers

    @property
    def slugs(self) -> list[str]:
        return sorted(self._handlers)

    def todos(self) -> list[HandlerTipoAtivo]:
        return [self._handlers[slug] for slug in self.slugs]
