"""Tempo real: stream SSE (``text/event-stream``) da atualização em segundo plano.

Por que SSE via ``fetch`` (e não ``EventSource`` nem WebSocket): o ``EventSource`` nativo não
envia o header ``Authorization`` e o token não pode ir na URL; WebSocket exigiria mudar a
CSP (``connect-src ws://``). Um ``fetch`` com ``Authorization: Bearer`` lendo o corpo em
streaming funciona com a CSP atual (``connect-src http://127.0.0.1:*``).

Eventos: ``conectado``, ``preco_atualizado``, ``indicador_atualizado``, ``erro_provider``,
``fim_ciclo`` e ``heartbeat`` (a cada 15 s sem outros eventos). ``data`` é JSON.
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.dependencias import PROTEGIDO, CanalDep, respostas
from app.jobs.eventos import gerar_sse

router = APIRouter(prefix="/api", tags=["tempo real"], dependencies=PROTEGIDO)

DESCRICAO = (
    "Stream de eventos (SSE). Consuma com `fetch` + `Authorization: Bearer` e leia o corpo "
    "em streaming. Cada mensagem tem `event:` (conectado, preco_atualizado, "
    "indicador_atualizado, erro_provider, fim_ciclo, heartbeat) e `data:` em JSON."
)


@router.get(
    "/eventos",
    summary="Eventos da atualização em tempo real (SSE)",
    description=DESCRICAO,
    response_class=StreamingResponse,
    responses={
        **respostas(),
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
    },
)
async def stream_eventos(request: Request, canal: CanalDep) -> StreamingResponse:
    return StreamingResponse(
        gerar_sse(canal, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
