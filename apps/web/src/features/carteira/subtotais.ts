import { somar } from "@/lib/decimal";

/**
 * Subtotal de Resultado de uma instituição (Parte 5A, decisão 9): soma exata (BigInt, sem
 * `number`) do resultado em BRL das posições do grupo. Se alguma posição não tiver
 * resultado (ex.: renda fixa sem indicador), o subtotal fica indisponível (`null`), para
 * não mostrar um total incompleto como se fosse completo.
 *
 * Exemplo conferido: PETR4 +4.210,40 e VALE3 +3.012,50 → +7.222,90.
 */
export function subtotalResultado(
  posicoes: readonly { metricas_brl?: { resultado_total: string } | null }[],
): string | null {
  const resultados = posicoes.map((p) => p.metricas_brl?.resultado_total);
  if (resultados.some((r) => typeof r !== "string")) return null;
  return somar(resultados as string[]);
}
