import type { Row } from "@tanstack/react-table";
import { comparar, ehDecimal } from "./decimal";

/**
 * Ordena colunas de decimais em texto pela comparação exata (sem `number`).
 * Vazios vão para o fim.
 */
export function ordenarDecimal<T>(a: Row<T>, b: Row<T>, coluna: string): number {
  const x = a.getValue<string | null | undefined>(coluna);
  const y = b.getValue<string | null | undefined>(coluna);
  const vx = x && ehDecimal(x) ? x : null;
  const vy = y && ehDecimal(y) ? y : null;
  if (vx === null && vy === null) return 0;
  if (vx === null) return 1;
  if (vy === null) return -1;
  return comparar(vx, vy);
}
