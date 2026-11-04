import { CATEGORIA_OUTROS, type CoresTema } from "@/theme/cores";
import { comparar, somar } from "./decimal";

/**
 * Fatias de gráficos por categoria (tipo de ativo, instituição, categoria de despesa).
 *
 * Regra das 6 cores por presença (Parte 5A):
 * - **As 6 maiores fatias presentes** ganham cor (comparação decimal exata; empate pela
 *   ordem fixa e depois pela ordem de chegada). As demais somam em **"Outros"**, com a cor
 *   de caixa (soma em decimal exato, sem `number`).
 * - **Cor fixa por categoria:** a posição em `ordem` (lista estável) define a cor das 6
 *   primeiras categorias da lista; elas mantêm essa cor sempre que estiverem entre as 6,
 *   mesmo que o ranking mude.
 * - Categoria sem cor própria (7ª em diante na ordem, ou fora dela) que entre no top 6 usa a
 *   **primeira cor livre**: a de uma categoria ausente ou que caiu em "Outros".
 * - A fatia `caixa` (saldo em conta) sempre usa a cor de caixa e fica por último.
 * - As fatias saem da maior para a menor.
 */
export interface FatiaEntrada {
  categoria: string;
  rotulo: string;
  valor: string;
  percentual?: string | null;
}

export interface FatiaPronta extends FatiaEntrada {
  cor: string;
}

export const MAXIMO_CATEGORIAS = 6;

export function prepararFatias(
  fatias: readonly FatiaEntrada[],
  ordem: readonly string[],
  cores: Pick<CoresTema, "series" | "caixa">,
): FatiaPronta[] {
  const caixa = fatias.filter((f) => f.categoria === "caixa");
  const posicao = (categoria: string) => {
    const indice = ordem.indexOf(categoria);
    return indice < 0 ? Number.MAX_SAFE_INTEGER : indice;
  };
  const demais = fatias
    .filter((f) => f.categoria !== "caixa")
    .map((f, i) => ({ fatia: f, i }))
    .sort(
      (a, b) =>
        comparar(b.fatia.valor, a.fatia.valor) ||
        posicao(a.fatia.categoria) - posicao(b.fatia.categoria) ||
        a.i - b.i,
    )
    .map(({ fatia }) => fatia);

  const visiveis = demais.slice(0, MAXIMO_CATEGORIAS);
  const agrupadas = demais.slice(MAXIMO_CATEGORIAS);

  // Primeiro as cores fixas de quem está no top 6; depois as livres para os demais.
  const usadas = new Set<number>();
  for (const f of visiveis) {
    const indice = posicao(f.categoria);
    if (indice < cores.series.length) usadas.add(indice);
  }
  const livres = cores.series.map((_, i) => i).filter((i) => !usadas.has(i));
  const prontas: FatiaPronta[] = visiveis.map((f) => {
    const indice = posicao(f.categoria);
    const fixa = indice < cores.series.length ? cores.series[indice] : undefined;
    if (fixa) return { ...f, cor: fixa };
    const livre = livres.shift();
    return { ...f, cor: (livre === undefined ? undefined : cores.series[livre]) ?? cores.caixa };
  });

  if (agrupadas.length > 0) {
    const percentuais = agrupadas.map((f) => f.percentual);
    prontas.push({
      categoria: CATEGORIA_OUTROS,
      rotulo: "Outros",
      valor: somar(agrupadas.map((f) => f.valor)),
      percentual: percentuais.every((p) => typeof p === "string") ? somar(percentuais) : null,
      cor: cores.caixa,
    });
  }
  return [...prontas, ...caixa.map((f) => ({ ...f, cor: cores.caixa }))];
}

/**
 * Ordem fixa das categorias de tipo de ativo (os 6 primeiros têm cor própria). Os tipos da
 * Parte 4.1 entram no fim para não mudar a cor dos existentes; quando estão entre as 6
 * maiores fatias, usam a primeira cor livre.
 */
export const ORDEM_TIPOS_ATIVO = [
  "acao_br",
  "renda_fixa",
  "fundo",
  "acao_us",
  "tesouro_direto",
  "cripto",
  "poupanca",
  "fundo_listado",
  "etf_br",
  "etf_us",
] as const;
