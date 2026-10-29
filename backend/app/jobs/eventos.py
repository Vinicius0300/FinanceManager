"""Canal de eventos em tempo real (preço atualizado, erro de provider, fim de ciclo).

A coleta roda numa thread; a API (SSE) no loop asyncio. ``publicar`` é thread-safe: entrega
o evento ao loop com ``call_soon_threadsafe``. Cada assinante tem uma fila limitada; se um
cliente não consome (aba travada), os eventos mais antigos dele são descartados, sem
segurar a coleta nem os demais clientes.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from app.services.coleta import EventoColeta

logger = logging.getLogger(__name__)

TAMANHO_FILA = 200
INTERVALO_HEARTBEAT_S = 15.0
INTERVALO_CHECAGEM_S = 1.0


@dataclass(frozen=True)
class MensagemSse:
    evento: str
    dados: dict[str, object]

    def formatar(self) -> str:
        texto = json.dumps(self.dados, ensure_ascii=False, separators=(",", ":"))
        return f"event: {self.evento}\ndata: {texto}\n\n"


class CanalEventos:
    def __init__(self, tamanho_fila: int = TAMANHO_FILA) -> None:
        self._tamanho = tamanho_fila
        self._filas: set[asyncio.Queue[MensagemSse]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def vincular(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def assinantes(self) -> int:
        return len(self._filas)

    def assinar(self) -> asyncio.Queue[MensagemSse]:
        fila: asyncio.Queue[MensagemSse] = asyncio.Queue(self._tamanho)
        self._filas.add(fila)
        return fila

    def cancelar(self, fila: asyncio.Queue[MensagemSse]) -> None:
        self._filas.discard(fila)

    def _entregar(self, mensagem: MensagemSse) -> None:
        for fila in list(self._filas):
            if fila.full():
                fila.get_nowait()  # descarta o mais antigo desse cliente
            fila.put_nowait(mensagem)

    def publicar(self, evento: EventoColeta) -> None:
        """Publica a partir de qualquer thread (sem loop vinculado, o evento é descartado)."""
        mensagem = MensagemSse(evento.tipo, evento.dados)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._entregar, mensagem)
        except RuntimeError:  # loop encerrando
            logger.debug("Evento descartado: loop encerrado.")


async def gerar_sse(
    canal: CanalEventos,
    desconectado: Callable[[], Awaitable[bool]],
    *,
    heartbeat_s: float = INTERVALO_HEARTBEAT_S,
    checagem_s: float = INTERVALO_CHECAGEM_S,
    relogio: Callable[[], float] | None = None,
) -> AsyncIterator[str]:
    """Texto SSE: eventos do canal e ``heartbeat`` periódico até o cliente desconectar."""
    agora = relogio or asyncio.get_running_loop().time
    fila = canal.assinar()
    ultimo_envio = agora()
    try:
        yield MensagemSse("conectado", {}).formatar()
        while not await desconectado():
            try:
                mensagem = await asyncio.wait_for(fila.get(), timeout=checagem_s)
            except TimeoutError:
                if agora() - ultimo_envio >= heartbeat_s:
                    ultimo_envio = agora()
                    yield MensagemSse("heartbeat", {}).formatar()
                continue
            ultimo_envio = agora()
            yield mensagem.formatar()
    finally:
        canal.cancelar(fila)
