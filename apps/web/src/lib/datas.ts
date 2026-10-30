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
