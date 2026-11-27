import { z } from "zod";
import { rotuloAtivo, type Ativo, type TipoAtivo } from "@/lib/consultas-comuns";
import { normalizarDecimal, sinal } from "@/lib/decimal";
import { lerDecimal, paraCampo } from "@/lib/formularios";
import type { Metas, Plano } from "./consultas";

/** Formulário do editor de metas: linhas, validação (Zod) e corpo do PUT (funções puras). */

export interface LinhaPeso {
  ativo_id: number;
  rotulo: string;
  peso: string;
}

export interface LinhaClasse {
  tipo: string;
  nome: string;
  temPosicao: boolean;
  percentual: string;
  pesos: LinhaPeso[];
}

export interface Valores {
  classes: LinhaClasse[];
}

export const preenchido = (texto: string) => texto.trim() !== "";

/**
 * Validação de cada campo (até 2 casas, de 0 a 100) e da regra "peso só em classe com
 * meta". As somas (classes = 100%; pesos de uma classe = 100%) são conferidas ao vivo e
 * bloqueiam o botão Salvar; a API confere tudo de novo.
 */
export const esquema = z
  .object({
    classes: z.array(
      z.object({
        tipo: z.string(),
        nome: z.string(),
        temPosicao: z.boolean(),
        percentual: z.string(),
        pesos: z.array(z.object({ ativo_id: z.number(), rotulo: z.string(), peso: z.string() })),
      }),
    ),
  })
  .superRefine((valores, ctx) => {
    const opcoes = { casas: 2, minimo: "0", maximo: "100" };
    valores.classes.forEach((classe, i) => {
      lerDecimal(ctx, `classes.${i}.percentual`, classe.percentual, opcoes);
      classe.pesos.forEach((peso, j) => {
        const caminho = `classes.${i}.pesos.${j}.peso`;
        lerDecimal(ctx, caminho, peso.peso, opcoes);
        if (preenchido(peso.peso) && !preenchido(classe.percentual)) {
          ctx.addIssue({
            code: "custom",
            message: "Defina a meta da classe antes de dar peso aos ativos dela.",
            path: [caminho],
          });
        }
      });
    });
  });

/** Corpo do PUT: só as classes e os pesos preenchidos (vazio = sem meta / sem peso). */
export function paraCorpo(valores: Valores, tolerancia: number): Metas {
  const numero = (texto: string) => normalizarDecimal(texto) ?? texto;
  return {
    classes: valores.classes
      .filter((c) => preenchido(c.percentual))
      .map((c) => ({ tipo_ativo: c.tipo, percentual: numero(c.percentual) })),
    ativos: valores.classes.flatMap((c) =>
      c.pesos
        .filter((p) => preenchido(p.peso))
        .map((p) => ({ tipo_ativo: c.tipo, ativo_id: p.ativo_id, peso: numero(p.peso) })),
    ),
    tolerancia_pp: tolerancia,
  };
}

/**
 * Linhas do editor: uma por tipo de ativo do registry, os que têm posição primeiro (na
 * ordem do plano), depois os demais. Os pesos listam os ativos da classe com posição
 * aberta ou com peso já gravado.
 */
export function montarLinhas(
  tipos: readonly TipoAtivo[],
  plano: Plano,
  metas: Metas,
  ativos: readonly Ativo[],
): LinhaClasse[] {
  const comPosicao = plano.classes
    .filter((c) => c.ativos.some((a) => sinal(a.valor_atual) > 0))
    .map((c) => c.tipo_ativo);
  const ordem = [
    ...comPosicao.filter((t) => tipos.some((x) => x.slug === t)),
    ...tipos.map((t) => t.slug).filter((t) => !comPosicao.includes(t)),
  ];
  const cadastro = new Map(ativos.map((a) => [a.id, a]));
  return ordem.map((slug) => {
    const meta = metas.classes.find((c) => c.tipo_ativo === slug);
    const doPlano = plano.classes.find((c) => c.tipo_ativo === slug)?.ativos ?? [];
    const ids = [
      ...doPlano.filter((a) => sinal(a.valor_atual) > 0).map((a) => a.ativo_id),
      ...metas.ativos.filter((a) => a.tipo_ativo === slug).map((a) => a.ativo_id),
    ];
    const pesos = [...new Set(ids)].map((id) => {
      const doItem = doPlano.find((a) => a.ativo_id === id);
      return {
        ativo_id: id,
        rotulo: doItem ? (doItem.simbolo ?? doItem.nome) : rotuloAtivo(cadastro.get(id)),
        peso: paraCampo(metas.ativos.find((a) => a.ativo_id === id)?.peso),
      };
    });
    return {
      tipo: slug,
      nome: tipos.find((t) => t.slug === slug)?.nome ?? slug,
      temPosicao: comPosicao.includes(slug),
      percentual: paraCampo(meta?.percentual),
      pesos,
    };
  });
}
