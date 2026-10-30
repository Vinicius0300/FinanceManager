import { CATEGORIA_OUTROS, type CoresTema } from "@/theme/cores";
import { somar } from "./decimal";

/**
 * Fatias de gráficos por categoria (tipo de ativo, instituição, categoria de despesa).
 *
 * Regras da paleta (Parte 4):
 * - **Ordem fixa:** a posição da categoria em `ordem` (lista estável) define a cor, então a
 *   mesma categoria tem a mesma cor em todos os gráficos.
 * - **Até 6 categorias** por gráfico ganham cor; acima disso, o resto vira **"Outros"**
 *   com a cor de caixa (somado em decimal exato, sem `number`).
 * - Categoria sem posição fixa (fora da ordem ou além da 6ª) usa a primeira cor livre.
 * - A fatia `caixa` (saldo em conta) sempre usa a cor de caixa e fica por último.
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
    .sort((a, b) => posicao(a.fatia.categoria) - posicao(b.fatia.categoria) || a.i - b.i)
    .map(({ fatia }) => fatia);

  const visiveis = demais.slice(0, MAXIMO_CATEGORIAS);
  const agrupadas = demais.slice(MAXIMO_CATEGORIAS);

  const usadas = new Set<number>();
  const comCor: (FatiaEntrada & { cor?: string })[] = visiveis.map((f) => {
    const indice = posicao(f.categoria);
    if (indice < cores.series.length) {
      usadas.add(indice);
      return { ...f, cor: cores.series[indice] };
    }
    return { ...f };
  });
  const livres = cores.series.map((_, i) => i).filter((i) => !usadas.has(i));
  const prontas: FatiaPronta[] = comCor.map((f) => {
    if (f.cor) return f as FatiaPronta;
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
 * Parte 4.1 entram no fim para não mudar a cor dos existentes; presentes no gráfico, usam a
 * primeira cor livre (ou "Outros" acima de 6 categorias). Rever na Parte 5.
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
