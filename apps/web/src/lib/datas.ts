import {
  addDays,
  format,
  isValid,
  parseISO,
  startOfMonth,
  startOfYear,
  subMonths,
  subYears,
} from "date-fns";

/** Datas de calendário no formato da API ("2026-10-29"), no fuso local do computador. */
export function paraIso(data: Date): string {
  return format(data, "yyyy-MM-dd");
}

export function hojeIso(agora: Date = new Date()): string {
  return paraIso(agora);
}

export function isoValida(texto: string | null | undefined): texto is string {
  return !!texto && /^\d{4}-\d{2}-\d{2}$/.test(texto) && isValid(parseISO(texto));
}

/** Período do histórico (decisão: meses de calendário, "12m" é o padrão). */
export type Periodo = "mes" | "3m" | "12m" | "ano" | "tudo" | "personalizado";

export const PERIODOS: readonly { valor: Periodo; rotulo: string }[] = [
  { valor: "mes", rotulo: "Este mês" },
  { valor: "3m", rotulo: "Últimos 3 meses" },
  { valor: "12m", rotulo: "Últimos 12 meses" },
  { valor: "ano", rotulo: "Este ano" },
  { valor: "tudo", rotulo: "Todo o histórico" },
  { valor: "personalizado", rotulo: "Personalizado" },
];

export const PERIODO_PADRAO: Periodo = "12m";

/**
 * Início e fim de um período em meses de calendário: "últimos 12 meses" vai do dia 1º de
 * 11 meses atrás até hoje (12 barras no gráfico mensal). "tudo" não tem limites.
 */
export function intervaloDoPeriodo(
  periodo: Periodo,
  agora: Date,
  personalizado: { inicio?: string | null; fim?: string | null } = {},
): { inicio: string | null; fim: string | null } {
  const hoje = paraIso(agora);
  switch (periodo) {
    case "mes":
      return { inicio: paraIso(startOfMonth(agora)), fim: hoje };
    case "3m":
      return { inicio: paraIso(startOfMonth(subMonths(agora, 2))), fim: hoje };
    case "12m":
      return { inicio: paraIso(startOfMonth(subMonths(agora, 11))), fim: hoje };
    case "ano":
      return { inicio: paraIso(startOfYear(agora)), fim: hoje };
    case "tudo":
      return { inicio: null, fim: null };
    case "personalizado":
      return {
        inicio: isoValida(personalizado.inicio) ? personalizado.inicio : null,
        fim: isoValida(personalizado.fim) ? personalizado.fim : null,
      };
  }
}

/** Janelas da evolução do patrimônio (a API aceita no máximo 1 ano). */
export type JanelaEvolucao = "1m" | "3m" | "6m" | "1a";

export const JANELAS_EVOLUCAO: readonly { valor: JanelaEvolucao; rotulo: string }[] = [
  { valor: "1m", rotulo: "1M" },
  { valor: "3m", rotulo: "3M" },
  { valor: "6m", rotulo: "6M" },
  { valor: "1a", rotulo: "1A" },
];

export function inicioDaJanela(janela: JanelaEvolucao, agora: Date): string {
  switch (janela) {
    case "1m":
      return paraIso(subMonths(agora, 1));
    case "3m":
      return paraIso(subMonths(agora, 3));
    case "6m":
      return paraIso(subMonths(agora, 6));
    case "1a":
      // 365 dias contando hoje (limite da API).
      return paraIso(addDays(subYears(agora, 1), 1));
  }
}

const MINUTO_MS = 60_000;
const HORA_MS = 60 * MINUTO_MS;
const DIA_MS = 24 * HORA_MS;

function contar(n: number, singular: string, plural: string): string {
  return `há ${n} ${n === 1 ? singular : plural}`;
}

/**
 * Tempo passado desde um instante ISO, em pt-BR ("agora há pouco", "há 10 minutos",
 * "há 3 dias", "há 2 meses"). Sempre arredonda para baixo; instante no futuro (relógio
 * adiantado) conta como "agora há pouco".
 */
export function tempoDecorrido(iso: string, agora: Date = new Date()): string {
  const instante = new Date(iso);
  if (Number.isNaN(instante.getTime())) return "—";
  const ms = agora.getTime() - instante.getTime();
  if (ms < MINUTO_MS) return "agora há pouco";
  if (ms < HORA_MS) return contar(Math.floor(ms / MINUTO_MS), "minuto", "minutos");
  if (ms < DIA_MS) return contar(Math.floor(ms / HORA_MS), "hora", "horas");
  const dias = Math.floor(ms / DIA_MS);
  if (dias < 30) return contar(dias, "dia", "dias");
  if (dias < 365) return contar(Math.floor(dias / 30), "mês", "meses");
  return contar(Math.floor(dias / 365), "ano", "anos");
}
