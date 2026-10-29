"""Formato padrão de erro da API: ``{"codigo", "mensagem", "detalhes"}`` em pt-BR.

Nunca devolve stack trace ao cliente; o detalhe técnico vai só para o log.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.erros import ConflitoError, DominioError, NaoEncontradoError

logger = logging.getLogger(__name__)

MENSAGENS_HTTP = {
    400: "Requisição inválida.",
    401: "Não autorizado.",
    403: "Acesso negado.",
    404: "Recurso não encontrado.",
    405: "Método não permitido.",
    409: "Conflito com o estado atual dos dados.",
    422: "Dados inválidos.",
}


class DetalheErro(BaseModel):
    campo: str
    mensagem: str


class ErroApi(BaseModel):
    codigo: str
    mensagem: str
    detalhes: list[DetalheErro] | None = None


class AplicacaoError(Exception):
    """Erro de negócio/aplicação com código e mensagem já em pt-BR."""

    def __init__(self, status_code: int, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status_code = status_code
        self.codigo = codigo
        self.mensagem = mensagem


def _resposta(
    status_code: int, erro: ErroApi, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=erro.model_dump(exclude_none=True),
        headers=headers,
    )


async def _tratar_aplicacao(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AplicacaoError)  # noqa: S101 - garantido pelo registro do handler
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return _resposta(exc.status_code, ErroApi(codigo=exc.codigo, mensagem=exc.mensagem), headers)


def status_do_dominio(exc: DominioError) -> int:
    if isinstance(exc, NaoEncontradoError):
        return 404
    if isinstance(exc, ConflitoError):
        return 409
    return 422


async def _tratar_dominio(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DominioError)  # noqa: S101
    detalhes = [DetalheErro(campo=d.campo, mensagem=d.mensagem) for d in exc.detalhes] or None
    return _resposta(
        status_do_dominio(exc),
        ErroApi(codigo=exc.codigo, mensagem=exc.mensagem, detalhes=detalhes),
    )


async def _tratar_http(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    mensagem = MENSAGENS_HTTP.get(exc.status_code, "Erro na requisição.")
    return _resposta(exc.status_code, ErroApi(codigo=f"http_{exc.status_code}", mensagem=mensagem))


async def _tratar_validacao(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    detalhes = [
        DetalheErro(
            campo=".".join(str(parte) for parte in erro.get("loc", ())),
            mensagem=str(erro.get("msg", "valor inválido")),
        )
        for erro in exc.errors()
    ]
    return _resposta(
        422, ErroApi(codigo="validacao", mensagem="Dados inválidos.", detalhes=detalhes)
    )


async def _tratar_inesperado(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Erro inesperado em %s %s", request.method, request.url.path, exc_info=exc)
    return _resposta(
        500,
        ErroApi(
            codigo="erro_interno",
            mensagem="Ocorreu um erro interno inesperado. Os detalhes foram registrados no log.",
        ),
    )


def registrar_tratadores(app: FastAPI) -> None:
    app.add_exception_handler(AplicacaoError, _tratar_aplicacao)
    app.add_exception_handler(DominioError, _tratar_dominio)
    app.add_exception_handler(StarletteHTTPException, _tratar_http)
    app.add_exception_handler(RequestValidationError, _tratar_validacao)
    app.add_exception_handler(Exception, _tratar_inesperado)
