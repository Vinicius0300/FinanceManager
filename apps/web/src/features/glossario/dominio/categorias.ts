import { SERIES_GRAFICO } from "@/theme/cores";

/**
 * As seis categorias do glossário, na ordem fixa que define a cor de cada uma: a categoria
 * na posição N usa o token `--grafico-N` (regra das 6 cores da Parte 5A). Rótulo e cor vêm
 * só daqui; nenhum componente fixa cor própria.
 */
export const CATEGORIAS = [
  { id: "conceitos", rotulo: "Conceitos básicos" },
  { id: "indicadores", rotulo: "Indicadores" },
  { id: "renda-fixa", rotulo: "Renda fixa" },
  { id: "renda-variavel", rotulo: "Renda variável e fundos" },
  { id: "impostos", rotulo: "Impostos e custos" },
  { id: "planejamento", rotulo: "Planejamento e análise" },
] as const;

export type IdCategoria = (typeof CATEGORIAS)[number]["id"];

export const IDS_CATEGORIA: readonly IdCategoria[] = CATEGORIAS.map((c) => c.id);

export function ehCategoria(valor: string): valor is IdCategoria {
  return (IDS_CATEGORIA as readonly string[]).includes(valor);
}

export function rotuloCategoria(id: IdCategoria): string {
  return CATEGORIAS.find((c) => c.id === id)?.rotulo ?? id;
}

/** Posição da categoria (0 a 5), que escolhe a série de cor do gráfico. */
export function indiceCategoria(id: IdCategoria): number {
  return IDS_CATEGORIA.indexOf(id);
}

/** Variável CSS da cor da categoria, para chips e marcadores fora do canvas. */
export function tokenCategoria(id: IdCategoria): string {
  return `var(${SERIES_GRAFICO[indiceCategoria(id)] ?? "--grafico-caixa"})`;
}
