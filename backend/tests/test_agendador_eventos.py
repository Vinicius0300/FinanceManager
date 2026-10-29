"""Agendador (asyncio + thread), canal de eventos e gerador SSE (sem rede, sem espera real)."""

import asyncio
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import Engine

from app.core.banco import criar_fabrica_sessoes, sessao_transacional
from app.jobs.agendador import Agendador
from app.jobs.eventos import CanalEventos, MensagemSse, gerar_sse
from app.services.coleta import Coletor, EventoColeta, ResumoCiclo
from app.services.configuracoes import alterar_configuracoes

INSTANTE = datetime(2026, 10, 29, 17, tzinfo=UTC)


class ColetorFalso:
    """Conta ciclos e pode segurar a execução para testar a trava."""

    def __init__(self, falhar: bool = False) -> None:
        self.ciclos: list[tuple[bool, list[int] | None]] = []
        self.liberar = threading.Event()
        self.liberar.set()
        self.cancelado = False
        self.falhar = falhar

    def executar(
        self, *, forcar: bool = False, ativo_ids: Iterable[int] | None = None
    ) -> ResumoCiclo:
        self.liberar.wait(timeout=5)
        if self.falhar:
            raise RuntimeError("bug")
        self.ciclos.append((forcar, list(ativo_ids) if ativo_ids is not None else None))
        return ResumoCiclo(INSTANTE, INSTANTE, forcar, 1, 0, 0)

    def cancelar(self) -> None:
        self.cancelado = True


def agendador(engine: Engine, coletor: ColetorFalso, segundos_por_minuto: float = 60) -> Agendador:
    return Agendador(
        cast(Coletor, coletor),
        criar_fabrica_sessoes(engine),
        segundos_por_minuto=segundos_por_minuto,
    )


def test_ciclo_ao_abrir_e_intervalo_da_configuracao(engine: Engine) -> None:
    async def cenario() -> None:
        coletor = ColetorFalso()
        # 1 "minuto" = 0,01 s: o intervalo padrão (5) vira 0,05 s.
        ag = agendador(engine, coletor, segundos_por_minuto=0.01)
        ag.iniciar()
        ag.iniciar()  # idempotente
        await asyncio.sleep(0.2)
        assert ag.ativo
        await ag.parar()
        assert not ag.ativo
        assert coletor.cancelado
        assert len(coletor.ciclos) >= 3
        assert coletor.ciclos[0] == (False, None)
        assert ag.ultimo_resumo is not None

    asyncio.run(cenario())


def test_acordar_antecipa_a_proxima_volta(engine: Engine) -> None:
    with sessao_transacional(criar_fabrica_sessoes(engine)) as sessao:
        alterar_configuracoes(sessao, 15)  # 15 min reais: só volta se for acordado

    async def cenario() -> None:
        coletor = ColetorFalso()
        ag = agendador(engine, coletor)
        ag.iniciar()
        await asyncio.sleep(0.05)
        assert len(coletor.ciclos) == 1
        await asyncio.to_thread(ag.acordar_de_outra_thread)  # como numa rota síncrona
        await asyncio.sleep(0.05)
        assert len(coletor.ciclos) == 2
        ag.acordar()
        await asyncio.sleep(0.05)
        assert len(coletor.ciclos) == 3
        await ag.parar()

    asyncio.run(cenario())


def test_forcar_nao_duplica_execucao_e_coleta_de_um_ativo(engine: Engine) -> None:
    async def cenario() -> None:
        coletor = ColetorFalso()
        coletor.liberar.clear()  # segura o primeiro ciclo
        ag = agendador(engine, coletor)
        primeiro = ag.forcar_atualizacao()
        assert primeiro.iniciado
        # Antes mesmo de a tarefa pegar a trava, um segundo pedido já é recusado.
        assert ag.em_execucao
        assert not ag.forcar_atualizacao().iniciado
        await asyncio.sleep(0.02)
        assert ag.em_execucao
        segundo = ag.forcar_atualizacao()
        assert (segundo.iniciado, segundo.mensagem) == (
            False,
            "Já existe uma atualização em andamento.",
        )
        coletor.liberar.set()
        await asyncio.sleep(0.05)
        assert coletor.ciclos == [(True, None)]
        ag.coletar_ativo(7)  # espera a vez; não conta como ciclo completo
        await asyncio.sleep(0.05)
        assert coletor.ciclos[-1] == (False, [7])
        assert ag.ultimo_resumo is not None
        assert ag.ultimo_resumo.forcado is True
        await ag.parar()

    asyncio.run(cenario())


def test_falha_no_ciclo_nao_derruba_o_agendador(engine: Engine) -> None:
    async def cenario() -> None:
        ag = agendador(engine, ColetorFalso(falhar=True))
        assert await ag.executar_ciclo() is None
        async with ag.exclusivo():
            assert ag.em_execucao
        assert not ag.em_execucao

    asyncio.run(cenario())


def test_acordar_de_outra_thread_sem_iniciar_nao_faz_nada(engine: Engine) -> None:
    async def cenario() -> None:
        ag = agendador(engine, ColetorFalso())
        ag.acordar_de_outra_thread()
        await ag.parar()

    asyncio.run(cenario())


# ---------------------------------------------------------------- canal e SSE


def test_mensagem_sse_formatada() -> None:
    mensagem = MensagemSse("preco_atualizado", {"ativo_id": 1, "valor": "52.2", "nome": "Ação"})
    assert mensagem.formatar() == (
        'event: preco_atualizado\ndata: {"ativo_id":1,"valor":"52.2","nome":"Ação"}\n\n'
    )


def test_canal_entrega_de_outra_thread_e_descarta_excesso() -> None:
    async def cenario() -> None:
        canal = CanalEventos(tamanho_fila=2)
        canal.publicar(EventoColeta("fim_ciclo", {}))  # sem loop: descartado sem erro
        canal.vincular(asyncio.get_running_loop())
        fila = canal.assinar()
        assert canal.assinantes == 1
        for indice in range(3):
            await asyncio.to_thread(canal.publicar, EventoColeta("fim_ciclo", {"n": indice}))
        await asyncio.sleep(0.01)
        recebidos = [fila.get_nowait().dados["n"] for _ in range(fila.qsize())]
        assert recebidos == [1, 2]  # o mais antigo foi descartado
        canal.cancelar(fila)
        assert canal.assinantes == 0

    asyncio.run(cenario())


def test_gerador_sse_eventos_heartbeat_e_desconexao() -> None:
    async def cenario() -> None:
        canal = CanalEventos()
        canal.vincular(asyncio.get_running_loop())
        tempo = [0.0]
        voltas = [0]

        async def desconectado() -> bool:
            voltas[0] += 1
            tempo[0] += 10  # cada volta "passa" 10 s
            return voltas[0] > 4

        gerador = gerar_sse(
            canal, desconectado, heartbeat_s=15, checagem_s=0.01, relogio=lambda: tempo[0]
        )
        recebido = [await gerador.__anext__()]
        assert canal.assinantes == 1
        canal.publicar(EventoColeta("preco_atualizado", {"ativo_id": 1}))
        recebido += [texto async for texto in gerador]
        assert recebido[0] == "event: conectado\ndata: {}\n\n"
        assert recebido[1] == 'event: preco_atualizado\ndata: {"ativo_id":1}\n\n'
        assert "event: heartbeat\ndata: {}\n\n" in recebido[2:]
        assert canal.assinantes == 0  # cancelou a assinatura ao desconectar

    asyncio.run(cenario())


@pytest.mark.parametrize("tipo", ["preco_atualizado", "erro_provider", "fim_ciclo"])
def test_tipos_de_evento_viram_mensagens(tipo: str) -> None:
    async def cenario() -> None:
        canal = CanalEventos()
        canal.vincular(asyncio.get_running_loop())
        fila = canal.assinar()
        canal.publicar(EventoColeta(tipo, {"x": 1}))  # type: ignore[arg-type]
        mensagem = await asyncio.wait_for(fila.get(), timeout=1)
        assert (mensagem.evento, mensagem.dados) == (tipo, {"x": 1})

    asyncio.run(cenario())
