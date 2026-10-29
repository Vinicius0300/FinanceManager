"""Datas e fuso horário do domínio.

Instantes (``datetime``) são guardados em UTC; a "data" de um preço é a data local
de Brasília (``America/Sao_Paulo``), que é como o usuário enxerga o dia.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

FUSO_LOCAL = ZoneInfo("America/Sao_Paulo")


def data_local(instante: datetime) -> date:
    """Data (no fuso de Brasília) de um instante com fuso definido."""
    if instante.tzinfo is None:
        raise ValueError("O instante precisa ter fuso horário definido.")
    return instante.astimezone(FUSO_LOCAL).date()


def agora_utc() -> datetime:
    """Relógio real (padrão das dependências injetáveis; testes passam o próprio)."""
    return datetime.now(UTC)


def hoje_local() -> date:
    """Data de hoje em Brasília pelo relógio real."""
    return data_local(agora_utc())


def formatar_data(dia: date) -> str:
    """Data no formato brasileiro para mensagens (dd/mm/aaaa)."""
    return dia.strftime("%d/%m/%Y")


def primeiro_dia_do_mes(dia: date) -> date:
    return dia.replace(day=1)


def primeiro_dia_do_proximo_mes(dia: date) -> date:
    return (dia.replace(day=28) + timedelta(days=4)).replace(day=1)


def somar_meses(dia: date, meses: int) -> date:
    """Soma meses mantendo o dia (exige dia ≤ 28 para existir em todos os meses)."""
    if dia.day > 28:
        raise ValueError("somar_meses exige dia do mês até 28.")
    indice = dia.year * 12 + (dia.month - 1) + meses
    return date(indice // 12, indice % 12 + 1, dia.day)


def dias_corridos(inicio: date, fim: date) -> list[date]:
    """Todos os dias de ``inicio`` a ``fim`` (inclusive)."""
    return [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]
