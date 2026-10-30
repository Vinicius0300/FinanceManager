/**
 * Formatação pt-BR com Intl. Valores chegam da API como **texto decimal** e são passados
 * direto ao `Intl.NumberFormat` (que aceita texto sem converter para `number`), então nada
 * perde precisão. Datas da API ("2026-10-29") são datas de calendário: formatamos sem
 * passar por fuso horário.
 */
import { absoluto, ehDecimal, moverVirgula, sinal } from "./decimal";

type TextoNumerico = Intl.StringNumericLiteral;

const formatadorDataHora = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "medium",
});

const MESES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
] as const;

const SIMBOLOS_MOEDA: Record<string, string> = { BRL: "R$", USD: "US$", EUR: "€" };

const TRACO = "—";
export const SINAL_NEGATIVO = "−"; // sinal de menos tipográfico (U+2212)

/** Formata um instante ISO 8601 (vindo da API) no fuso local, em pt-BR. */
export function formatarDataHora(iso: string): string {
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "data inválida";
  return formatadorDataHora.format(data);
}

/** "2026-10-29" → "29/10/2026" (sem fuso horário). */
export function formatarData(iso: string | null | undefined): string {
  if (!iso) return TRACO;
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  if (!ano || !mes || !dia) return "data inválida";
  return `${dia}/${mes}/${ano}`;
}

/** "2026-10-01" → "outubro de 2026". */
export function formatarMesAno(iso: string): string {
  const [ano, mes] = iso.split("-");
  const nome = MESES[Number(mes) - 1];
  return nome && ano ? `${nome} de ${ano}` : "mês inválido";
}

/** "2026-10-01" → "out/26" (eixos de gráficos). */
export function formatarMesCurto(iso: string): string {
  const [ano, mes] = iso.split("-");
  const nome = MESES[Number(mes) - 1];
  return nome && ano ? `${nome.slice(0, 3)}/${ano.slice(2)}` : "?";
}

const cacheFormatadores = new Map<string, Intl.NumberFormat>();

function formatador(chave: string, opcoes: Intl.NumberFormatOptions): Intl.NumberFormat {
  let existente = cacheFormatadores.get(chave);
  if (!existente) {
    existente = new Intl.NumberFormat("pt-BR", opcoes);
    cacheFormatadores.set(chave, existente);
  }
  return existente;
}

function texto(valor: string): TextoNumerico {
  return valor.trim() as TextoNumerico;
}

/**
 * Valor monetário: "1234.5" → "R$ 1.234,50"; USD → "US$ 1.234,50".
 * Negativos usam o sinal de menos tipográfico antes do símbolo ("−R$ 10,00").
 */
export function formatarMoeda(
  valor: string | null | undefined,
  moeda = "BRL",
  opcoes: { casas?: number } = {},
): string {
  if (valor === null || valor === undefined || !ehDecimal(valor)) return TRACO;
  const casas = opcoes.casas ?? 2;
  const numero = formatador(`moeda-${casas}`, {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  }).format(texto(absoluto(valor)));
  const simbolo = SIMBOLOS_MOEDA[moeda] ?? moeda;
  const negativo = sinal(valor) < 0 ? SINAL_NEGATIVO : "";
  return `${negativo}${simbolo} ${numero}`;
}

/** Número com até `maximo` casas (quantidades, cotações): "0.12345678" → "0,12345678". */
export function formatarNumero(
  valor: string | null | undefined,
  opcoes: { minimo?: number; maximo?: number } = {},
): string {
  if (valor === null || valor === undefined || !ehDecimal(valor)) return TRACO;
  const minimo = opcoes.minimo ?? 0;
  const maximo = opcoes.maximo ?? 8;
  const numero = formatador(`numero-${minimo}-${maximo}`, {
    minimumFractionDigits: minimo,
    maximumFractionDigits: maximo,
  }).format(texto(absoluto(valor)));
  return sinal(valor) < 0 ? `${SINAL_NEGATIVO}${numero}` : numero;
}

/** Preço unitário na moeda do ativo, com até 8 casas e no mínimo 2. */
export function formatarPreco(valor: string | null | undefined, moeda = "BRL"): string {
  if (valor === null || valor === undefined || !ehDecimal(valor)) return TRACO;
  const numero = formatarNumero(valor, { minimo: 2, maximo: 8 });
  const simbolo = SIMBOLOS_MOEDA[moeda] ?? moeda;
  return numero.startsWith(SINAL_NEGATIVO)
    ? `${SINAL_NEGATIVO}${simbolo} ${numero.slice(1)}`
    : `${simbolo} ${numero}`;
}

/** Percentual já em pontos percentuais ("12.5" → "12,50%"). */
export function formatarPercentual(valor: string | null | undefined, casas = 2): string {
  if (valor === null || valor === undefined || !ehDecimal(valor)) return TRACO;
  const numero = formatarNumero(valor, { minimo: casas, maximo: casas });
  return `${numero}%`;
}

/** Razão da API ("0.1234" = 12,34%) formatada como percentual. */
export function formatarRazao(valor: string | null | undefined, casas = 2): string {
  if (valor === null || valor === undefined || !ehDecimal(valor)) return TRACO;
  return formatarPercentual(moverVirgula(valor, 2), casas);
}

export type TomValor = "positivo" | "negativo" | "neutro";

/** Tom de um valor financeiro: ganho, perda ou zero (zero usa a cor neutra). */
export function tomDoValor(valor: string | null | undefined): TomValor {
  if (valor === null || valor === undefined || !ehDecimal(valor)) return "neutro";
  const s = sinal(valor);
  return s > 0 ? "positivo" : s < 0 ? "negativo" : "neutro";
}

/** Valor com sinal explícito: "+R$ 195,00", "−R$ 40,00", "R$ 0,00". */
export function formatarMoedaComSinal(valor: string | null | undefined, moeda = "BRL"): string {
  const formatado = formatarMoeda(valor, moeda);
  return tomDoValor(valor) === "positivo" ? `+${formatado}` : formatado;
}

/** Razão com sinal explícito como percentual: "0.0125" → "+1,25%", "-0.004" → "−0,40%". */
export function formatarRazaoComSinal(valor: string | null | undefined, casas = 2): string {
  const formatado = formatarRazao(valor, casas);
  return tomDoValor(valor) === "positivo" ? `+${formatado}` : formatado;
}

/** "1 operação" / "3 operações". */
export function plural(quantidade: number, singular: string, pluralTexto: string): string {
  return `${quantidade.toLocaleString("pt-BR")} ${quantidade === 1 ? singular : pluralTexto}`;
}
