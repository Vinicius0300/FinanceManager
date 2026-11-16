import type { components } from "@/api/schema";
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
  credito_receita: "Receita",
  debito_despesa: "Despesa",
  transferencia_saida: "Transferência enviada",
  transferencia_entrada: "Transferência recebida",
};

/**
 * Texto da linha do extrato: "Receita: Salário", "Despesa: Aluguel", "Transferência para
 * Itaú", "Transferência de Nubank"; os demais pelo nome do tipo. `detalhe` é a descrição
 * mostrada embaixo (a das transferências; nos lançamentos ela já está no título).
 */
export function rotuloMovimento(m: components["schemas"]["MovimentoSaida"]): {
  titulo: string;
  detalhe: string | null;
} {
  if (m.tipo === "credito_receita" || m.tipo === "debito_despesa") {
    const tipo = m.tipo === "credito_receita" ? "Receita" : "Despesa";
    return { titulo: m.descricao ? `${tipo}: ${m.descricao}` : tipo, detalhe: null };
  }
  if (m.tipo === "transferencia_saida" || m.tipo === "transferencia_entrada") {
    const sentido = m.tipo === "transferencia_saida" ? "para" : "de";
    return {
      titulo: `Transferência ${sentido} ${m.contraparte ?? "outra instituição"}`,
      detalhe: m.descricao,
    };
  }
  const titulo = NOMES_MOVIMENTO[m.tipo] ?? m.tipo;
  // O ajuste automático grava como descrição o próprio nome do tipo: não repetir.
  return { titulo, detalhe: m.descricao === titulo ? null : m.descricao };
}
