import { useMemo } from "react";
import { useTemaStore } from "./tema";

/**
 * Cores dos gráficos lidas das variáveis CSS em tempo de execução (nada de hex no código
 * dos gráficos). O valor muda com o tema: os componentes dependem de `useCoresTema` e se
 * redesenham quando o tema troca.
 *
 * Os tokens estão em `oklch(...)`, que o ECharts e o Lightweight Charts não interpretam
 * (eles calculam realces e transparências com o próprio parser de cores). Por isso cada
 * token é convertido para `rgb(...)` pelo próprio navegador: pintamos 1 pixel num canvas e
 * lemos a cor resultante.
 */
export const SERIES_GRAFICO = [
  "--grafico-1",
  "--grafico-2",
  "--grafico-3",
  "--grafico-4",
  "--grafico-5",
  "--grafico-6",
] as const;

export const TOKENS_GRAFICO = [...SERIES_GRAFICO, "--grafico-caixa"] as const;

export const CATEGORIA_OUTROS = "outros";

/** Lê uma variável CSS do <html> (texto vazio se não existir, ex.: em testes sem CSS). */
export function lerToken(nome: string, elemento: Element = document.documentElement): string {
  return getComputedStyle(elemento).getPropertyValue(nome).trim();
}

const cacheRgb = new Map<string, string>();
let contexto: CanvasRenderingContext2D | null | undefined;

function contexto2d(): CanvasRenderingContext2D | null {
  if (contexto === undefined) {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      contexto = canvas.getContext("2d", { willReadFrequently: true });
    } catch {
      contexto = null;
    }
  }
  return contexto;
}

/** Converte qualquer cor CSS (inclusive oklch) para `rgb(r, g, b)`; sem canvas, devolve a original. */
export function paraRgb(cor: string): string {
  if (!cor) return cor;
  const existente = cacheRgb.get(cor);
  if (existente) return existente;
  const ctx = contexto2d();
  if (!ctx) return cor;
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = cor;
  ctx.fillRect(0, 0, 1, 1);
  const [r = 0, g = 0, b = 0] = ctx.getImageData(0, 0, 1, 1).data;
  const rgb = `rgb(${r}, ${g}, ${b})`;
  cacheRgb.set(cor, rgb);
  return rgb;
}

/** `rgb(r, g, b)` → `rgba(r, g, b, alfa)` (degradês e preenchimentos). */
export function comAlfa(rgb: string, alfa: number): string {
  const partes = /^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/.exec(rgb);
  if (!partes) return rgb;
  return `rgba(${partes[1]}, ${partes[2]}, ${partes[3]}, ${alfa})`;
}

export interface CoresTema {
  series: string[];
  caixa: string;
  texto: string;
  textoSuave: string;
  borda: string;
  fundo: string;
  cartao: string;
  positivo: string;
  negativo: string;
}

export function lerCoresTema(): CoresTema {
  const cor = (token: string) => paraRgb(lerToken(token));
  return {
    series: SERIES_GRAFICO.map(cor),
    caixa: cor("--grafico-caixa"),
    texto: cor("--foreground"),
    textoSuave: cor("--muted-foreground"),
    borda: cor("--border"),
    fundo: cor("--card"),
    cartao: cor("--popover"),
    positivo: cor("--positivo"),
    negativo: cor("--negativo"),
  };
}

const cacheCores = new Map<string, CoresTema>();

/**
 * Cores de um tema (lidas uma vez e guardadas: os tokens de cada tema não mudam).
 * Chame com o tema já aplicado no <html>; o store do tema troca a classe na hora.
 * Sem CSS carregado (testes), não guarda nada para não fixar valores vazios.
 */
export function coresDoTema(tema: string): CoresTema {
  const existente = cacheCores.get(tema);
  if (existente) return existente;
  const cores = lerCoresTema();
  if (cores.texto) cacheCores.set(tema, cores);
  return cores;
}

/** Cores do tema atual; mudam (e os gráficos se redesenham) quando o tema troca. */
export function useCoresTema(): CoresTema {
  const tema = useTemaStore((s) => s.tema);
  return useMemo(() => coresDoTema(tema), [tema]);
}

/**
 * Cor fixa por categoria: a posição da categoria em `ordem` (lista completa e estável,
 * ex.: tipos de ativo do registry) define a série. Caixa, "Outros" e categorias além da
 * 6ª usam a cor de caixa.
 */
export function corDaCategoria(
  categoria: string,
  ordem: readonly string[],
  cores: Pick<CoresTema, "series" | "caixa">,
): string {
  if (categoria === "caixa" || categoria === CATEGORIA_OUTROS) return cores.caixa;
  const indice = ordem.indexOf(categoria);
  return (indice >= 0 ? cores.series[indice] : undefined) ?? cores.caixa;
}
