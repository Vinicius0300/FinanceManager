import { z } from "zod";
import type { components } from "@/api/schema";
import { ehZero } from "@/lib/decimal";
import { CASAS, dataObrigatoria, lerDecimal, paraCampo } from "@/lib/formularios";
import { NOMES_OPERACAO, OPERACOES, type Operacao } from "../historico/filtros";

export type TransacaoEntrada = components["schemas"]["TransacaoEntrada"];
export type TransacaoSaida = components["schemas"]["TransacaoSaida"];

export const SUBTIPOS_PROVENTO = [
  { valor: "dividendo", rotulo: "Dividendo" },
  { valor: "jcp", rotulo: "Juros sobre capital próprio (JCP)" },
  { valor: "rendimento", rotulo: "Rendimento" },
  { valor: "outro", rotulo: "Outro" },
] as const;

export interface ValoresTransacao {
  tipo: Operacao;
  ativo_id: string;
  instituicao_id: string;
  data: string;
  quantidade: string;
  preco_unitario: string;
  valor: string;
  taxas: string;
  cambio: string;
  subtipo_provento: string;
  imposto_retido: string;
  observacao: string;
}

/** O que o formulário precisa saber do ativo escolhido (vem do registry de tipos). */
export interface RegrasDoAtivo {
  moeda: string;
  tiposAceitos: readonly string[];
  aceitaTaxas: boolean;
}

export const usaQuantidade = (tipo: Operacao) => tipo === "compra" || tipo === "venda";

/**
 * Esquema do formulário de transação: os campos exigidos dependem da operação.
 * Compra/venda: quantidade (até 8 casas) e preço (até 8); aporte/resgate/provento: valor
 * (2 casas). Câmbio pago (até 6 casas) só para ativos fora do real: se vazio, o backend usa
 * a PTAX da data. Provento: tipo do provento e imposto retido (valor informado é o líquido).
 */
export function criarEsquemaTransacao(regras: (ativoId: number) => RegrasDoAtivo | undefined) {
  return z
    .object({
      tipo: z.enum(OPERACOES),
      // Obrigatórios conferidos no transform: assim todos os erros aparecem de uma vez
      // (o Zod não roda o transform se um campo do objeto já falhou).
      ativo_id: z.string(),
      instituicao_id: z.string(),
      data: z.string(),
      quantidade: z.string(),
      preco_unitario: z.string(),
      valor: z.string(),
      taxas: z.string(),
      cambio: z.string(),
      subtipo_provento: z.string(),
      imposto_retido: z.string(),
      observacao: z.string(),
    })
    .transform((v, ctx): TransacaoEntrada => {
      const exigir = (ok: boolean, campo: string, message: string) => {
        if (!ok) ctx.addIssue({ code: "custom", path: [campo], message });
      };
      exigir(v.ativo_id !== "", "ativo_id", "Escolha o ativo.");
      exigir(v.instituicao_id !== "", "instituicao_id", "Escolha a instituição.");
      const data = dataObrigatoria.safeParse(v.data);
      exigir(data.success, "data", data.error?.issues[0]?.message ?? "");
      exigir(v.observacao.length <= 500, "observacao", "Use no máximo 500 caracteres.");
      const ativoId = Number(v.ativo_id);
      const ativo = regras(ativoId);
      if (ativo && !ativo.tiposAceitos.includes(v.tipo)) {
        ctx.addIssue({
          code: "custom",
          path: ["tipo"],
          message: `Este tipo de ativo não aceita ${NOMES_OPERACAO[v.tipo].toLowerCase()}.`,
        });
      }
      const entrada: TransacaoEntrada = {
        tipo: v.tipo,
        ativo_id: ativoId,
        instituicao_id: Number(v.instituicao_id),
        data: v.data,
        taxas: "0",
        imposto_retido: "0",
        aceitar_ajuste: false,
        observacao: v.observacao.trim() || null,
      };
      if (usaQuantidade(v.tipo)) {
        entrada.quantidade = lerDecimal(ctx, "quantidade", v.quantidade, {
          casas: CASAS.quantidade,
          sinal: "positivo",
          obrigatorio: true,
        });
        entrada.preco_unitario = lerDecimal(ctx, "preco_unitario", v.preco_unitario, {
          casas: CASAS.preco,
          sinal: "naoNegativo",
          obrigatorio: true,
        });
        if (ativo?.aceitaTaxas !== false) {
          entrada.taxas =
            lerDecimal(ctx, "taxas", v.taxas, { casas: CASAS.moeda, sinal: "naoNegativo" }) ?? "0";
        }
      } else {
        entrada.valor = lerDecimal(ctx, "valor", v.valor, {
          casas: CASAS.moeda,
          sinal: "positivo",
          obrigatorio: true,
        });
      }
      if (v.tipo === "provento") {
        if (!v.subtipo_provento) {
          ctx.addIssue({
            code: "custom",
            path: ["subtipo_provento"],
            message: "Escolha o tipo do provento.",
          });
        }
        entrada.subtipo_provento = (v.subtipo_provento ||
          null) as TransacaoEntrada["subtipo_provento"];
        entrada.imposto_retido =
          lerDecimal(ctx, "imposto_retido", v.imposto_retido, {
            casas: CASAS.moeda,
            sinal: "naoNegativo",
          }) ?? "0";
      }
      if (ativo && ativo.moeda !== "BRL") {
        entrada.cambio = lerDecimal(ctx, "cambio", v.cambio, {
          casas: CASAS.cambio,
          sinal: "positivo",
        });
      }
      return entrada;
    });
}

export function valoresIniciais(hoje: string, transacao?: TransacaoSaida): ValoresTransacao {
  if (!transacao) {
    return {
      tipo: "compra",
      ativo_id: "",
      instituicao_id: "",
      data: hoje,
      quantidade: "",
      preco_unitario: "",
      valor: "",
      taxas: "",
      cambio: "",
      subtipo_provento: "dividendo",
      imposto_retido: "",
      observacao: "",
    };
  }
  const moedaEstrangeira = transacao.moeda !== "BRL";
  return {
    tipo: transacao.tipo,
    ativo_id: String(transacao.ativo_id),
    instituicao_id: String(transacao.instituicao_id),
    data: transacao.data,
    quantidade: paraCampo(transacao.quantidade),
    preco_unitario: paraCampo(transacao.preco_unitario),
    valor: paraCampo(transacao.valor),
    taxas: ehZero(transacao.taxas) ? "" : paraCampo(transacao.taxas),
    cambio: moedaEstrangeira ? paraCampo(transacao.cambio) : "",
    subtipo_provento: transacao.subtipo_provento ?? "dividendo",
    imposto_retido: ehZero(transacao.imposto_retido) ? "" : paraCampo(transacao.imposto_retido),
    observacao: transacao.observacao ?? "",
  };
}
