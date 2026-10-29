"""Quando coletar cada alvo da atualização automática (regras puras, relógio injetado).

Regras (decididas com o dono, Parte 3):
- **Intradiária** (ações e cripto): coleta se ``agora − último sucesso ≥ intervalo``
  (1 a 15 min, padrão 5). Uma coleta que falhou não conta como sucesso, então é tentada
  de novo no ciclo seguinte.
- **Fora do pregão**, ações só coletam se o último sucesso foi antes do último
  fechamento (para gravar o preço final do dia). O fechamento considera uma margem de
  :data:`MARGEM_FECHAMENTO` (leilão de fechamento e consolidação do preço na fonte).
  Pregões: B3 10h–17h (Brasília, dias úteis sem feriados nacionais); bolsa dos EUA
  9h30–16h (Nova York, dias de semana; feriados americanos não são considerados e só
  geram coletas extras sem efeito).
- **Cripto** não tem pregão: roda 24 h.
- **Diária** (indicadores, Tesouro, fundos): coleta se o último sucesso não foi hoje
  (data de Brasília), ao abrir o app e nos ciclos seguintes até conseguir.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.domain.calendario import feriados_nacionais
from app.domain.tempo import data_local

MARGEM_FECHAMENTO = timedelta(minutes=30)
FOLGA_CICLO = timedelta(seconds=30)
"""Tolerância para o ciclo que acorda um pouco antes de completar o intervalo."""

INTERVALO_MINIMO_MIN = 1
INTERVALO_MAXIMO_MIN = 15
INTERVALO_PADRAO_MIN = 5
DIAS_BUSCA_FECHAMENTO = 15


class Frequencia(StrEnum):
    INTRADIARIA = "intradiaria"
    DIARIA = "diaria"


def _sem_feriados(_ano: int) -> frozenset[date]:
    return frozenset()


@dataclass(frozen=True)
class Pregao:
    nome: str
    fuso: ZoneInfo
    abertura: time
    fechamento: time
    feriados: Callable[[int], frozenset[date]] = _sem_feriados

    def eh_dia_de_pregao(self, dia: date) -> bool:
        return dia.weekday() < 5 and dia not in self.feriados(dia.year)

    def _fechamento_em(self, dia: date) -> datetime:
        return datetime.combine(dia, self.fechamento, tzinfo=self.fuso) + MARGEM_FECHAMENTO

    def aberto(self, agora: datetime) -> bool:
        """Pregão aberto (incluindo a margem depois do fechamento)."""
        local = agora.astimezone(self.fuso)
        if not self.eh_dia_de_pregao(local.date()):
            return False
        inicio = datetime.combine(local.date(), self.abertura, tzinfo=self.fuso)
        return inicio <= local < self._fechamento_em(local.date())

    def ultimo_fechamento(self, agora: datetime) -> datetime:
        """Instante (com margem) do fechamento mais recente que já passou."""
        dia = agora.astimezone(self.fuso).date()
        for _ in range(DIAS_BUSCA_FECHAMENTO):
            if self.eh_dia_de_pregao(dia) and self._fechamento_em(dia) <= agora:
                return self._fechamento_em(dia)
            dia -= timedelta(days=1)
        return self._fechamento_em(dia)


PREGAO_B3 = Pregao(
    nome="B3",
    fuso=ZoneInfo("America/Sao_Paulo"),
    abertura=time(10),
    fechamento=time(17),
    feriados=feriados_nacionais,
)
PREGAO_EUA = Pregao(
    nome="Bolsa dos EUA",
    fuso=ZoneInfo("America/New_York"),
    abertura=time(9, 30),
    fechamento=time(16),
)


@dataclass(frozen=True)
class Agenda:
    frequencia: Frequencia
    pregao: Pregao | None = None  # intradiária sem pregão = 24 h (cripto)


AGENDA_DIARIA = Agenda(Frequencia.DIARIA)
AGENDA_CONTINUA = Agenda(Frequencia.INTRADIARIA)
AGENDA_B3 = Agenda(Frequencia.INTRADIARIA, PREGAO_B3)
AGENDA_EUA = Agenda(Frequencia.INTRADIARIA, PREGAO_EUA)


def precisa_coletar(
    agenda: Agenda, ultimo_sucesso: datetime | None, agora: datetime, intervalo: timedelta
) -> bool:
    """Se o alvo deve ser coletado agora (ver regras no topo do módulo)."""
    if ultimo_sucesso is None:
        return True
    if agenda.frequencia is Frequencia.DIARIA:
        return data_local(ultimo_sucesso) != data_local(agora)
    if agenda.pregao is not None and not agenda.pregao.aberto(agora):
        return ultimo_sucesso < agenda.pregao.ultimo_fechamento(agora)
    return agora - ultimo_sucesso >= intervalo - FOLGA_CICLO
