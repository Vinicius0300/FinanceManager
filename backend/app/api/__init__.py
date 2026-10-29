"""Camada HTTP: só valida, orquestra e serializa (sem regra de negócio)."""

from fastapi import APIRouter

from app.api import (
    ativos,
    backup,
    configuracoes,
    eventos,
    financeiro,
    indicadores,
    instituicoes,
    portfolio,
    precos,
    transacoes,
)

ROTEADORES: tuple[APIRouter, ...] = (
    instituicoes.router,
    ativos.router,
    transacoes.router,
    precos.router,
    indicadores.router,
    portfolio.router,
    financeiro.router,
    configuracoes.router,
    backup.router,
    eventos.router,
)
