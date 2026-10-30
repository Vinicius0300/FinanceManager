import { cn } from "@/lib/utils";
import { CLASSES_OPERACAO, NOMES_OPERACAO, type Operacao } from "./filtros";

/** Selo com a cor da operação (compra azul, aporte violeta, venda rosa, resgate coral, provento turquesa). */
export function SeloOperacao({ tipo }: { tipo: Operacao }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold",
        CLASSES_OPERACAO[tipo].selo,
      )}
    >
      <span aria-hidden className={cn("size-1.5 rounded-full", CLASSES_OPERACAO[tipo].ponto)} />
      {NOMES_OPERACAO[tipo]}
    </span>
  );
}
