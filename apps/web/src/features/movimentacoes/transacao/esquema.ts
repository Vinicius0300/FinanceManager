import { z } from "zod";
import type { components } from "@/api/schema";
import {
  criarEsquemaAtivo,
  paraEntradaAtivo,
  type ValoresFormularioAtivo,
} from "@/features/carteira/esquemaAtivo";
import type { TipoAtivo } from "@/lib/consultas-comuns";
import { ehZero } from "@/lib/decimal";
import { CASAS, dataObrigatoria, lerDecimal, paraCampo } from "@/lib/formularios";
import { NOMES_OPERACAO, OPERACOES, type Operacao } from "../historico/filtros";

export type TransacaoEntrada = components["schemas"]["TransacaoEntrada"];
export type TransacaoSaida = components["schemas"]["TransacaoSaida"];
export type MovimentacaoEntrada = components["schemas"]["MovimentacaoEntrada"];

export const SUBTIPOS_PROVENTO = [
  { valor: "dividendo", rotulo: "Dividendo" },
  { valor: "jcp", rotulo: "Juros sobre capital próprio (JCP)" },
  { valor: "rendimento", rotulo: "Rendimento" },
  { valor: "outro", rotulo: "Outro" },
] as const;

/**
 * Campos específicos preenchidos com a data da operação (e escondidos no formulário único):
 * a data de aplicação de um título novo é a data do primeiro aporte.
 */
export const CAMPOS_COM_A_DATA_DA_OPERACAO = new Set(["data_aplicacao"]);

/** Só compra e aporte podem cadastrar um ativo novo (venda, resgate e provento não). */
export const OPERACOES_QUE_CRIAM: readonly Operacao[] = ["compra", "aporte"];

export const criaAtivo = (tipo: Operacao) => OPERACOES_QUE_CRIAM.includes(tipo);
export const usaQuantidade = (tipo: Operacao) => tipo === "compra" || tipo === "venda";

export type ModoAtivo = "" | "existente" | "novo";

export interface ValoresTransacao {
  tipo_ativo: string;
  tipo: Operacao;
  modo_ativo: ModoAtivo;
  ativo_id: string;
  novo_ativo: ValoresFormularioAtivo;
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

/** O que o esquema precisa consultar: tipos do registry e a moeda dos ativos cadastrados. */
export interface ContextoEsquema {
  tipo: (slug: string) => TipoAtivo | undefined;
  moedaDoAtivo: (ativoId: number) => string | undefined;
}

export function novoAtivoVazio(tipo?: TipoAtivo): ValoresFormularioAtivo {
  return {
    nome: "",
    simbolo: "",
    moeda: tipo?.moeda_padrao ?? "BRL",
    simbolo_externo: "",
    metadados: Object.fromEntries((tipo?.campos ?? []).map((c) => [c.nome, ""])),
  };
}

/** Primeira operação aceita pelo tipo, preferindo a atual. */
export function operacaoAceita(tipo: TipoAtivo | undefined, atual: Operacao): Operacao {
  if (!tipo || tipo.tipos_transacao.includes(atual)) return atual;
  const preferida = OPERACOES.find((op) => criaAtivo(op) && tipo.tipos_transacao.includes(op));
  return preferida ?? (tipo.tipos_transacao[0] as Operacao | undefined) ?? atual;
}

/**
 * Esquema do formulário único de movimentação. Os campos exigidos dependem do tipo de
 * ativo e da operação:
 * - ativo: um cadastrado (`ativo_id`) ou um novo (`novo_ativo`, validado pelo schema do
 *   tipo, como no cadastro; ticker obrigatório nos tipos com busca por ticker);
 * - compra/venda: quantidade (até 8 casas) e preço (até 8); aporte/resgate/provento: valor
 *   (2 casas); câmbio (até 6) só fora do real; provento: tipo e imposto retido.
 * Todos os erros aparecem de uma vez (validação no `transform`).
 */
export function criarEsquemaTransacao(contexto: ContextoEsquema) {
  return z
    .object({
      tipo_ativo: z.string(),
      tipo: z.enum(OPERACOES),
      modo_ativo: z.enum(["", "existente", "novo"]),
      ativo_id: z.string(),
      novo_ativo: z.object({
        nome: z.string(),
        simbolo: z.string(),
        moeda: z.string(),
        simbolo_externo: z.string(),
        metadados: z.record(z.string(), z.string()),
      }),
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
    .transform((v, ctx): MovimentacaoEntrada => {
      const exigir = (ok: boolean, caminho: (string | number)[], message: string) => {
        if (!ok) ctx.addIssue({ code: "custom", path: caminho, message });
      };
      const tipoAtivo = contexto.tipo(v.tipo_ativo);
      exigir(tipoAtivo !== undefined, ["tipo_ativo"], "Escolha o tipo de ativo.");
      exigir(v.instituicao_id !== "", ["instituicao_id"], "Escolha a instituição.");
      const data = dataObrigatoria.safeParse(v.data);
      exigir(data.success, ["data"], data.error?.issues[0]?.message ?? "");
      exigir(v.observacao.length <= 500, ["observacao"], "Use no máximo 500 caracteres.");
      if (tipoAtivo && !tipoAtivo.tipos_transacao.includes(v.tipo)) {
        exigir(
          false,
          ["tipo"],
          `${tipoAtivo.nome} não aceita ${NOMES_OPERACAO[v.tipo].toLowerCase()}.`,
        );
      }

      const entrada: MovimentacaoEntrada = {
        tipo: v.tipo,
        instituicao_id: Number(v.instituicao_id),
        data: v.data,
        taxas: "0",
        imposto_retido: "0",
        aceitar_ajuste: false,
        confirmar_novo: false,
        observacao: v.observacao.trim() || null,
      };

      let moeda = "BRL";
      if (v.modo_ativo === "existente" && v.ativo_id !== "") {
        entrada.ativo_id = Number(v.ativo_id);
        moeda = contexto.moedaDoAtivo(entrada.ativo_id) ?? "BRL";
      } else if (v.modo_ativo === "novo" && tipoAtivo) {
        if (!criaAtivo(v.tipo)) {
          exigir(false, ["ativo_id"], "Venda, resgate e provento só em ativos já cadastrados.");
        }
        const metadados = { ...v.novo_ativo.metadados };
        for (const campo of tipoAtivo.campos) {
          if (CAMPOS_COM_A_DATA_DA_OPERACAO.has(campo.nome)) metadados[campo.nome] = v.data;
        }
        const novo = criarEsquemaAtivo(tipoAtivo).safeParse({ ...v.novo_ativo, metadados });
        if (novo.success) {
          entrada.novo_ativo = paraEntradaAtivo(tipoAtivo, novo.data);
        } else {
          for (const problema of novo.error.issues) {
            ctx.addIssue({
              code: "custom",
              path: ["novo_ativo", ...problema.path.map((p) => (typeof p === "symbol" ? "" : p))],
              message: problema.message,
            });
          }
        }
        if (tipoAtivo.busca_por_ticker) {
          exigir(
            v.novo_ativo.simbolo.trim() !== "",
            ["novo_ativo", "simbolo"],
            "Informe o ticker.",
          );
        }
        moeda = v.novo_ativo.moeda || tipoAtivo.moeda_padrao;
      } else {
        exigir(false, ["ativo_id"], "Escolha o ativo.");
      }

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
        if (tipoAtivo?.aceita_taxas !== false) {
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
        exigir(v.subtipo_provento !== "", ["subtipo_provento"], "Escolha o tipo do provento.");
        entrada.subtipo_provento = (v.subtipo_provento ||
          null) as MovimentacaoEntrada["subtipo_provento"];
        entrada.imposto_retido =
          lerDecimal(ctx, "imposto_retido", v.imposto_retido, {
            casas: CASAS.moeda,
            sinal: "naoNegativo",
          }) ?? "0";
      }
      if (moeda !== "BRL") {
        entrada.cambio = lerDecimal(ctx, "cambio", v.cambio, {
          casas: CASAS.cambio,
          sinal: "positivo",
        });
      }
      return entrada;
    });
}

/** Corpo do PUT de edição (o ativo não muda): a movimentação sem os campos de cadastro. */
export function paraTransacaoEntrada(
  movimentacao: MovimentacaoEntrada,
  ativoId: number,
): TransacaoEntrada {
  return {
    ativo_id: ativoId,
    instituicao_id: movimentacao.instituicao_id,
    tipo: movimentacao.tipo,
    data: movimentacao.data,
    quantidade: movimentacao.quantidade ?? null,
    preco_unitario: movimentacao.preco_unitario ?? null,
    valor: movimentacao.valor ?? null,
    taxas: movimentacao.taxas,
    cambio: movimentacao.cambio ?? null,
    subtipo_provento: movimentacao.subtipo_provento ?? null,
    imposto_retido: movimentacao.imposto_retido,
    observacao: movimentacao.observacao ?? null,
    aceitar_ajuste: movimentacao.aceitar_ajuste,
  };
}

export function valoresIniciais(
  hoje: string,
  transacao?: TransacaoSaida,
  tipoDoAtivo?: TipoAtivo,
): ValoresTransacao {
  if (!transacao) {
    return {
      tipo_ativo: tipoDoAtivo?.slug ?? "",
      tipo: "compra",
      modo_ativo: "",
      ativo_id: "",
      novo_ativo: novoAtivoVazio(tipoDoAtivo),
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
    tipo_ativo: tipoDoAtivo?.slug ?? "",
    tipo: transacao.tipo,
    modo_ativo: "existente",
    ativo_id: String(transacao.ativo_id),
    novo_ativo: novoAtivoVazio(tipoDoAtivo),
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
