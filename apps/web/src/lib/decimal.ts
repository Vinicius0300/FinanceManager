/**
 * Decimais exatos em texto (como chegam da API: "1234.56", "-0.5").
 *
 * Regra do projeto: o front **não** faz aritmética financeira em `number`. Estas funções
 * trabalham com `BigInt` escalado (sem perda de precisão) e só existem para o que a tela
 * precisa: sinal (cor/seta de ganho e perda), comparação, agrupar fatias de gráfico em
 * "Outros" e normalizar o que o usuário digita. Totais financeiros vêm prontos da API.
 */

const PADRAO_DECIMAL = /^[-+]?\d+(\.\d+)?$/;

interface Escalado {
  inteiro: bigint;
  casas: number;
}

export function ehDecimal(texto: string): boolean {
  return PADRAO_DECIMAL.test(texto.trim());
}

function escalar(texto: string): Escalado {
  const limpo = texto.trim();
  if (!PADRAO_DECIMAL.test(limpo)) throw new Error(`Número inválido: ${texto}`);
  const negativo = limpo.startsWith("-");
  const semSinal = limpo.replace(/^[-+]/, "");
  const [parteInteira = "0", fracao = ""] = semSinal.split(".");
  const inteiro = BigInt(parteInteira + fracao);
  return { inteiro: negativo ? -inteiro : inteiro, casas: fracao.length };
}

function alinhar(a: Escalado, casas: number): bigint {
  return a.inteiro * 10n ** BigInt(casas - a.casas);
}

function paraTexto(inteiro: bigint, casas: number): string {
  const negativo = inteiro < 0n;
  const digitos = (negativo ? -inteiro : inteiro).toString().padStart(casas + 1, "0");
  const corte = digitos.length - casas;
  const texto = casas > 0 ? `${digitos.slice(0, corte)}.${digitos.slice(corte)}` : digitos;
  return negativo ? `-${texto}` : texto;
}

/** -1, 0 ou 1. */
export function sinal(texto: string): -1 | 0 | 1 {
  const { inteiro } = escalar(texto);
  return inteiro === 0n ? 0 : inteiro > 0n ? 1 : -1;
}

/** Zero (ou texto que não é número): usado para mostrar "—" em vez de "R$ 0,00". */
export function ehZero(texto: string | null | undefined): boolean {
  return !texto || !ehDecimal(texto) || sinal(texto) === 0;
}

/** Compara dois decimais (negativo se a < b, zero se iguais, positivo se a > b). */
export function comparar(a: string, b: string): number {
  const x = escalar(a);
  const y = escalar(b);
  const casas = Math.max(x.casas, y.casas);
  const diferenca = alinhar(x, casas) - alinhar(y, casas);
  return diferenca === 0n ? 0 : diferenca > 0n ? 1 : -1;
}

/** Soma exata (ex.: fatias agrupadas em "Outros"); preserva a maior quantidade de casas. */
export function somar(valores: readonly string[]): string {
  if (valores.length === 0) return "0";
  const escalados = valores.map(escalar);
  const casas = Math.max(...escalados.map((v) => v.casas));
  const total = escalados.reduce((soma, v) => soma + alinhar(v, casas), 0n);
  return paraTexto(total, casas);
}

/**
 * Multiplica por 10^casas movendo a vírgula (exato). Ex.: razão "0.1234" → "12.34" (%).
 * Usado para exibir as razões da API (rentabilidade, participação) como percentual.
 */
export function moverVirgula(texto: string, casas: number): string {
  const { inteiro, casas: atuais } = escalar(texto);
  if (casas >= atuais) return paraTexto(inteiro * 10n ** BigInt(casas - atuais), 0);
  return paraTexto(inteiro, atuais - casas);
}

/** Valor absoluto (para exibir "−R$ 10,00" com o sinal separado). */
export function absoluto(texto: string): string {
  return texto.trim().replace(/^[-+]/, "");
}

/**
 * Valor numérico **só para desenhar** gráficos (altura de barra, ângulo de fatia).
 * Nunca usar o resultado em contas ou na exibição de valores.
 */
export function paraGrafico(texto: string | null | undefined): number {
  if (!texto || !ehDecimal(texto)) return 0;
  return Number(texto);
}

/**
 * Converte o que o usuário digitou no padrão brasileiro ("1.234,56", "1234,5", "10")
 * ou com ponto decimal ("1234.56") para o texto aceito pela API ("1234.56").
 * Devolve `null` se não for um número.
 *
 * Regra: com vírgula, a vírgula é o separador decimal e os pontos são de milhar; sem
 * vírgula, um único ponto é o separador decimal (ex.: "0.5" de cripto).
 */
export function normalizarDecimal(entrada: string): string | null {
  const texto = entrada.trim().replace(/\s/g, "");
  if (!texto) return null;
  let normalizado: string;
  if (texto.includes(",")) {
    if ((texto.match(/,/g) ?? []).length > 1) return null;
    const [inteira = "", fracao = ""] = texto.split(",");
    if (inteira.includes(".") && !/^[-+]?\d{1,3}(\.\d{3})+$/.test(inteira)) return null;
    normalizado = `${inteira.replace(/\./g, "")}.${fracao}`;
    if (fracao === "") normalizado = inteira.replace(/\./g, "");
  } else {
    if ((texto.match(/\./g) ?? []).length > 1) return null;
    normalizado = texto;
  }
  normalizado = normalizado.replace(/^\+/, "");
  if (!PADRAO_DECIMAL.test(normalizado)) return null;
  return normalizado;
}

/** Quantidade de casas decimais de um texto já normalizado. */
export function casasDecimais(texto: string): number {
  return texto.split(".")[1]?.length ?? 0;
}
