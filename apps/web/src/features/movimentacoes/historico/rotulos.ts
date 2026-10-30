import type { Operacao } from "./consultas";

export const NOMES_SUBTIPO: Record<string, string> = {
  dividendo: "dividendo",
  jcp: "JCP",
  rendimento: "rendimento",
  outro: "outro provento",
};

/** Agrupa as operações (já ordenadas por data pela API) por mês, na ordem recebida. */
export function agruparPorMes(
  operacoes: readonly Operacao[],
): { mes: string; itens: Operacao[] }[] {
  const grupos: { mes: string; itens: Operacao[] }[] = [];
  for (const op of operacoes) {
    const mes = `${op.data.slice(0, 7)}-01`;
    const ultimo = grupos.at(-1);
    if (ultimo?.mes === mes) ultimo.itens.push(op);
    else grupos.push({ mes, itens: [op] });
  }
  return grupos;
}

export const NOMES_MOVIMENTO: Record<string, string> = {
  deposito: "Depósito",
  saque: "Saque",
  debito_compra: "Débito da compra/aporte",
  credito_venda: "Crédito da venda/resgate",
  credito_provento: "Crédito do provento",
  ajuste_saldo: "Ajuste de saldo (depósito não informado)",
};
