"""Backup e restauração do banco (a tela, com confirmação, fica para a Parte 4)."""

import asyncio
from datetime import datetime

from fastapi import APIRouter, status

from app.api.dependencias import PROTEGIDO, AgendadorDep, EngineDep, respostas
from app.api.schemas import Modelo
from app.core import paths
from app.services import backup

router = APIRouter(prefix="/api/backups", tags=["backup"], dependencies=PROTEGIDO)


class BackupSaida(Modelo):
    nome: str
    tamanho_bytes: int
    criado_em: datetime


class RestauracaoEntrada(Modelo):
    nome: str | None = None  # um backup da lista
    caminho: str | None = None  # ou um arquivo .db em outro lugar (caminho absoluto)


class RestauracaoSaida(Modelo):
    restaurado: str
    backup_seguranca: BackupSaida


def _backup(info: backup.InfoBackup) -> BackupSaida:
    return BackupSaida(nome=info.nome, tamanho_bytes=info.tamanho_bytes, criado_em=info.criado_em)


@router.get(
    "",
    response_model=list[BackupSaida],
    summary="Backups disponíveis (mais recentes primeiro)",
    responses=respostas(),
)
def listar_backups() -> list[BackupSaida]:
    return [_backup(i) for i in backup.listar_backups(paths.diretorio_backups())]


@router.post(
    "",
    response_model=BackupSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um backup agora (API de backup do SQLite, validado)",
    responses=respostas(422),
)
def criar_backup() -> BackupSaida:
    return _backup(backup.criar_backup_manual(paths.caminho_banco(), paths.diretorio_backups()))


@router.post(
    "/restaurar",
    response_model=RestauracaoSaida,
    summary="Restaura um backup (com backup de segurança antes)",
    description=(
        "Valida o arquivo (banco íntegro do Finanças, de versão conhecida), faz um backup de "
        "segurança do banco atual, restaura e aplica as migrações. Em caso de falha, o banco "
        "anterior volta. A atualização automática fica pausada durante a restauração."
    ),
    responses=respostas(404, 422),
)
async def restaurar_backup(
    dados: RestauracaoEntrada, agendador: AgendadorDep, engine: EngineDep
) -> RestauracaoSaida:
    pasta = paths.diretorio_backups()
    arquivo = backup.localizar_backup(pasta, dados.nome, dados.caminho)
    async with agendador.exclusivo():
        resultado = await asyncio.to_thread(
            backup.restaurar, arquivo, paths.caminho_banco(), pasta, engine
        )
    return RestauracaoSaida(
        restaurado=resultado.restaurado, backup_seguranca=_backup(resultado.backup_seguranca)
    )
