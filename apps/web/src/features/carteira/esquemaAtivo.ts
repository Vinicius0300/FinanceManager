import { z } from "zod";
import type { components } from "@/api/schema";
import type { TipoAtivo } from "@/lib/consultas-comuns";
import {
  dataObrigatoria,
  decimalObrigatorio,
  decimalOpcional,
  textoObrigatorio,
  textoOpcional,
} from "@/lib/formularios";

type CampoTipo = components["schemas"]["CampoTipo"];
export type AtivoEntrada = components["schemas"]["AtivoEntrada"];

/**
 * Esquema do formulário de ativo **gerado a partir do schema do tipo**
 * (`GET /api/tipos-ativo`): cada `CampoTipo` (texto, decimal, inteiro, data, escolha) ganha
 * a validação equivalente à do backend.
 */

const TAMANHO_TEXTO_PADRAO = 200;

export const AJUDA_SIMBOLO_EXTERNO: Record<string, string> = {
  fundo:
    "Só para fundos com subclasses (Resolução CVM 175): informe o ID_SUBCLASSE da cota que " +
    "você tem. Sem ele, o app não escolhe sozinho qual cota usar.",
  cripto: "Id da moeda na CoinGecko. Vazio = encontrado automaticamente pelo símbolo.",
  acao_br: "Símbolo no Yahoo (ex.: PETR4.SA). Vazio = gerado automaticamente.",
  acao_us: "Símbolo no Yahoo. Vazio = o próprio símbolo.",
};

function esquemaDoCampo(campo: CampoTipo) {
  const limites = { minimo: campo.minimo, maximo: campo.maximo };
  switch (campo.tipo) {
    case "decimal":
      return campo.obrigatorio
        ? decimalObrigatorio({ casas: 8, ...limites })
        : decimalOpcional({ casas: 8, ...limites });
    case "inteiro": {
      const base = campo.obrigatorio
        ? decimalObrigatorio({ casas: 0, ...limites })
        : decimalOpcional({ casas: 0, ...limites });
      // Inteiro vai como número JSON (a API recusa texto para campos inteiros).
      return base.transform((v) => (v === null ? null : Number(v)));
    }
    case "data":
      return campo.obrigatorio
        ? dataObrigatoria
        : z
            .string()
            .regex(/^(\d{4}-\d{2}-\d{2})?$/, "Data inválida.")
            .transform((v) => (v === "" ? null : v));
    case "escolha":
      return campo.obrigatorio
        ? z.string().min(1, "Escolha uma opção.")
        : z.string().transform((v) => (v === "" ? null : v));
    default:
      return campo.obrigatorio
        ? textoObrigatorio(campo.tamanho_maximo ?? TAMANHO_TEXTO_PADRAO)
        : textoOpcional(campo.tamanho_maximo ?? TAMANHO_TEXTO_PADRAO);
  }
}

export function criarEsquemaAtivo(tipo: TipoAtivo) {
  const metadados = Object.fromEntries(tipo.campos.map((c) => [c.nome, esquemaDoCampo(c)]));
  return z.object({
    nome: textoObrigatorio(150),
    simbolo: textoOpcional(30),
    moeda: z.string().min(1, "Escolha a moeda."),
    simbolo_externo: textoOpcional(60),
    metadados: z.object(metadados),
  });
}

export type ValoresFormularioAtivo = {
  nome: string;
  simbolo: string;
  moeda: string;
  simbolo_externo: string;
  metadados: Record<string, string>;
};

/** Monta o corpo da API: metadados vazios são omitidos. */
export function paraEntradaAtivo(
  tipo: TipoAtivo,
  dados: z.output<ReturnType<typeof criarEsquemaAtivo>>,
): AtivoEntrada {
  const metadados: Record<string, string | number> = {};
  for (const [nome, valor] of Object.entries(dados.metadados)) {
    if (valor !== null && valor !== "") metadados[nome] = valor;
  }
  return {
    tipo: tipo.slug,
    nome: dados.nome,
    simbolo: tipo.modo === "cotas" ? dados.simbolo : null,
    moeda: dados.moeda,
    simbolo_externo: dados.simbolo_externo,
    metadados,
  };
}
