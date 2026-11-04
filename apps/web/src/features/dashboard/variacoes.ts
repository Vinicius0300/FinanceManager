import { comparar, sinal } from "@/lib/decimal";
import type { VariacaoCarteira } from "./consultas";

export type VariacaoAtivo = VariacaoCarteira["ativos"][number];

export const MAXIMO_POR_LADO = 3;

/**
 * Altas e baixas do dia: as maiores variações positivas (da maior para a menor) e as
 * maiores negativas (da mais negativa para a menos), comparando a razão decimal sem
 * `number`. Variação zero ou sem razão não entra em nenhum dos lados.
 */
export function separarAltasEBaixas(
  ativos: readonly VariacaoAtivo[],
  maximo = MAXIMO_POR_LADO,
): { altas: VariacaoAtivo[]; baixas: VariacaoAtivo[] } {
  const comRazao = ativos.filter(
    (a): a is VariacaoAtivo & { variacao: { variacao: string } } =>
      typeof a.variacao.variacao === "string",
  );
  const altas = comRazao
    .filter((a) => sinal(a.variacao.variacao) > 0)
    .sort((a, b) => comparar(b.variacao.variacao, a.variacao.variacao))
    .slice(0, maximo);
  const baixas = comRazao
    .filter((a) => sinal(a.variacao.variacao) < 0)
    .sort((a, b) => comparar(a.variacao.variacao, b.variacao.variacao))
    .slice(0, maximo);
  return { altas, baixas };
}
