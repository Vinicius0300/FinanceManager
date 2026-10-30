"""Agendador da atualização em segundo plano (asyncio, sem dependência nova).

- Ao abrir o app roda um ciclo e depois um a cada ``intervalo`` (configuração lida a cada
  volta, então mudar o intervalo vale sem reiniciar; :meth:`acordar` antecipa a volta).
- O ciclo (rede e banco) roda numa thread (``asyncio.to_thread``): a API nunca bloqueia.
- **Um ciclo por vez** (``asyncio.Lock``): a atualização forçada não duplica execuções; se já
  houver uma em andamento, é recusada com aviso. A restauração de backup usa o mesmo lock.
- Qualquer falha do ciclo é registrada no log e o agendador continua.
- **Listas oficiais de tickers** (Parte 4.1): ao iniciar, importa as bolsas que ainda não
  têm lista; "Atualizar lista" e a busca do cadastro (ticker fora da lista) pedem uma nova
  importação. Usa o mesmo lock (nunca junto com a coleta nem com a restauração de backup).
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Coroutine, Iterable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.core.banco import sessao_transacional
from app.services.coleta import Coletor, ResumoCiclo
from app.services.configuracoes import obter_intervalo
from app.services.simbolos import ImportadorListas, ResultadoImportacao

logger = logging.getLogger(__name__)

SEGUNDOS_POR_MINUTO = 60


@dataclass(frozen=True)
class Disparo:
    iniciado: bool
    mensagem: str


class Agendador:
    def __init__(
        self,
        coletor: Coletor,
        fabrica_sessoes: sessionmaker[Session],
        *,
        segundos_por_minuto: float = SEGUNDOS_POR_MINUTO,
        importador: ImportadorListas | None = None,
    ) -> None:
        self._coletor = coletor
        self._importador = importador
        self._importacao: asyncio.Task[list[ResultadoImportacao]] | None = None
        self._fabrica = fabrica_sessoes
        self._segundos_por_minuto = segundos_por_minuto
        self._trava = asyncio.Lock()
        self._acordar = asyncio.Event()
        self._tarefa: asyncio.Task[None] | None = None
        self._avulsas: set[asyncio.Task[ResumoCiclo | None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._forcada: asyncio.Task[ResumoCiclo | None] | None = None
        self.ultimo_resumo: ResumoCiclo | None = None

    @property
    def em_execucao(self) -> bool:
        """Há um ciclo rodando ou uma atualização forçada aguardando a vez."""
        forcada_pendente = self._forcada is not None and not self._forcada.done()
        return self._trava.locked() or forcada_pendente

    @property
    def ativo(self) -> bool:
        return self._tarefa is not None and not self._tarefa.done()

    def iniciar(self) -> None:
        if not self.ativo:
            self._loop = asyncio.get_running_loop()
            self._tarefa = asyncio.create_task(self._laco(), name="agendador-coleta")
            if self._importador is not None:
                self._importacao = asyncio.create_task(
                    self._importar(None, so_pendentes=True), name="agendador-listas"
                )

    async def parar(self) -> None:
        self._coletor.cancelar()
        tarefas: list[asyncio.Task[object]] = [
            t for t in (self._tarefa, self._importacao, *self._avulsas) if t is not None
        ]
        for tarefa in tarefas:
            tarefa.cancel()
        for tarefa in tarefas:
            try:
                await tarefa
            except asyncio.CancelledError:
                pass
            except Exception:  # pragma: no cover - registrado no próprio ciclo
                logger.exception("Falha ao parar a tarefa de coleta.")
        self._tarefa = None

    def acordar(self) -> None:
        """Antecipa a próxima volta (ex.: mudou o intervalo). Só no loop do agendador."""
        self._acordar.set()

    def acordar_de_outra_thread(self) -> None:
        """Mesmo que :meth:`acordar`, chamado de rotas síncronas (threadpool)."""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._acordar.set)

    async def _intervalo_s(self) -> float:
        def ler() -> int:
            with sessao_transacional(self._fabrica) as sessao:
                return obter_intervalo(sessao)

        try:
            minutos = await asyncio.to_thread(ler)
        except Exception:
            logger.exception("Não foi possível ler o intervalo; usando o padrão.")
            minutos = 5
        return minutos * self._segundos_por_minuto

    async def _laco(self) -> None:
        while True:
            await self.executar_ciclo()
            espera = await self._intervalo_s()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._acordar.wait(), timeout=espera)
            self._acordar.clear()

    async def executar_ciclo(
        self, *, forcar: bool = False, ativo_ids: Iterable[int] | None = None
    ) -> ResumoCiclo | None:
        """Roda um ciclo esperando a vez (nunca dois ao mesmo tempo)."""
        ids = list(ativo_ids) if ativo_ids is not None else None
        async with self._trava:
            try:
                resumo = await asyncio.to_thread(
                    self._coletor.executar, forcar=forcar, ativo_ids=ids
                )
            except Exception:
                logger.exception("Falha inesperada no ciclo de atualização.")
                return None
            if ids is None:
                self.ultimo_resumo = resumo
            return resumo

    def _em_segundo_plano(
        self, ciclo: Coroutine[None, None, ResumoCiclo | None]
    ) -> asyncio.Task[ResumoCiclo | None]:
        tarefa = asyncio.create_task(ciclo)
        self._avulsas.add(tarefa)
        tarefa.add_done_callback(self._avulsas.discard)
        return tarefa

    def forcar_atualizacao(self) -> Disparo:
        """Atualização manual: ignora o intervalo; recusada se já houver uma rodando."""
        if self.em_execucao:
            return Disparo(False, "Já existe uma atualização em andamento.")
        self._forcada = self._em_segundo_plano(self.executar_ciclo(forcar=True))
        return Disparo(True, "Atualização iniciada. O resultado chega pelos eventos.")

    def coletar_ativo(self, ativo_id: int) -> None:
        """Coleta (e baixa o histórico de) um ativo recém-cadastrado, em segundo plano."""
        self._em_segundo_plano(self.executar_ciclo(ativo_ids=[ativo_id]))

    # ------------------------------------------------------------ listas de tickers

    @property
    def importando_listas(self) -> bool:
        return self._importacao is not None and not self._importacao.done()

    async def _importar(
        self, bolsas: Sequence[str] | None, *, so_pendentes: bool = False
    ) -> list[ResultadoImportacao]:
        importador = self._importador
        if importador is None:
            return []
        async with self._trava:
            try:
                escolhidas = (
                    await asyncio.to_thread(importador.pendentes) if so_pendentes else bolsas
                )
                if escolhidas is not None and not escolhidas:
                    return []
                return await asyncio.to_thread(importador.executar, escolhidas)
            except Exception:
                logger.exception("Falha inesperada ao importar as listas de tickers.")
                return []

    def importar_listas(self, bolsas: Sequence[str] | None = None) -> Disparo:
        """Importa (de novo) as listas em segundo plano; recusada se já houver uma rodando."""
        if self._importador is None:
            return Disparo(False, "Importação de listas indisponível.")
        if self.importando_listas:
            return Disparo(False, "A lista de tickers já está sendo atualizada.")
        self._importacao = asyncio.create_task(self._importar(bolsas), name="agendador-listas")
        return Disparo(True, "Atualização da lista iniciada. O resultado chega pelos eventos.")

    def importar_listas_de_outra_thread(self, bolsas: Sequence[str]) -> bool:
        """Mesmo que :meth:`importar_listas`, chamado de rotas síncronas (threadpool).

        ``False`` se o agendador não está rodando (nada foi pedido).
        """
        if self._importador is None or self._loop is None or self._loop.is_closed():
            return False
        self._loop.call_soon_threadsafe(self.importar_listas, list(bolsas))
        return True

    @asynccontextmanager
    async def exclusivo(self) -> AsyncIterator[None]:
        """Bloqueia a coleta enquanto algo precisa do banco só para si (restauração)."""
        async with self._trava:
            yield
