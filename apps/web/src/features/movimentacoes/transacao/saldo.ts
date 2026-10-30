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

export interface AtivoSemelhante {
  ativoId: number;
  nome: string;
  resumo: string;
}

/**
 * Lê os `detalhes` do 409 `ativo_semelhante` (renda fixa com os mesmos dados de um título
 * já cadastrado); `null` para qualquer outro erro.
 */
export function lerAtivoSemelhante(erro: unknown): AtivoSemelhante | null {
  if (!(erro instanceof FalhaApi) || erro.codigo !== "ativo_semelhante") return null;
  const id = Number(erro.detalhe("ativo_id"));
  if (!Number.isInteger(id) || id <= 0) return null;
  return {
    ativoId: id,
    nome: erro.detalhe("nome") ?? "título existente",
    resumo: erro.detalhe("resumo") ?? "",
  };
}
