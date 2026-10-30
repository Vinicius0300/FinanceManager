import { FalhaApi } from "@/lib/backend";

export interface SaldoInsuficiente {
  instituicao: string;
  moeda: string;
  data: string;
  valorFaltante: string;
}

/** Lê os `detalhes` do 409 `saldo_insuficiente`; `null` para qualquer outro erro. */
export function lerSaldoInsuficiente(erro: unknown): SaldoInsuficiente | null {
  if (!(erro instanceof FalhaApi) || erro.codigo !== "saldo_insuficiente") return null;
  return {
    instituicao: erro.detalhe("instituicao") ?? "a instituição",
    moeda: erro.detalhe("moeda") ?? "BRL",
    data: erro.detalhe("data") ?? "",
    valorFaltante: erro.detalhe("valor_faltante") ?? "0",
  };
}
