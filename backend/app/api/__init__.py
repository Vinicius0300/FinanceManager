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
    movimentacoes,
    portfolio,
    precos,
    rebalanceamento,
    simbolos,
    transacoes,
    transferencias,
)

ROTEADORES: tuple[APIRouter, ...] = (
    instituicoes.router,
    ativos.router,
    transacoes.router,
    movimentacoes.router,
    simbolos.router,
    precos.router,
    indicadores.router,
    portfolio.router,
    rebalanceamento.router,
    financeiro.router,
    transferencias.router,
    configuracoes.router,
    backup.router,
    eventos.router,
)
