import { tooltipCartao } from "@/components/graficos/estiloGrafico";
import { comAlfa, type CoresTema } from "@/theme/cores";
import { indiceCategoria } from "./dominio/categorias";
import { grau, type Aresta, type IndiceGlossario } from "./dominio/indice";
import type { Posicao } from "./dominio/layout";

export const TAMANHO_MINIMO = 8;
export const TAMANHO_MAXIMO = 26;
/** Opacidade do resto do grafo enquanto o mouse está sobre uma bolinha. */
export const OPACIDADE_ESMAECIDA = 0.15;

/**
 * Tamanho da bolinha pelo número de ligações, relativo ao termo mais ligado. A raiz
 * quadrada evita que poucos termos muito ligados fiquem enormes e o resto, minúsculo.
 * Ex.: com máximo de 16 ligações, 16 → 26 px, 4 → 8 + 18 × √(4/16) = 17 px, 0 → 8 px.
 */
export function tamanhoDoNo(ligacoes: number, maximoLigacoes: number): number {
  if (maximoLigacoes <= 0) return TAMANHO_MINIMO;
  const fracao = Math.min(1, Math.max(0, ligacoes) / maximoLigacoes);
  return Math.round(TAMANHO_MINIMO + (TAMANHO_MAXIMO - TAMANHO_MINIMO) * Math.sqrt(fracao));
}

/**
 * Quais termos aparecem no grafo: todos das categorias ligadas, na ordem do índice. O termo
 * aberto sempre aparece, mesmo com a categoria dele desligada.
 */
export function termosVisiveis(
  indice: IndiceGlossario,
  categoriasAtivas: ReadonlySet<string>,
  selecionado: string | null,
): string[] {
  return indice.termos
    .filter((t) => t.slug === selecionado || categoriasAtivas.has(t.categoria))
    .map((t) => t.slug);
}

export function arestasEntre(indice: IndiceGlossario, slugs: readonly string[]): Aresta[] {
  const conjunto = new Set(slugs);
  return indice.arestas.filter(({ a, b }) => conjunto.has(a) && conjunto.has(b));
}

/** Escapa texto que vai para o tooltip (o ECharts monta o tooltip como HTML). */
export function escaparHtml(texto: string): string {
  return texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

interface DadoNo {
  id: string;
  name: string;
  resumo: string;
}

/**
 * Opções do ECharts para o grafo. As posições já vêm calculadas (`layout: "none"`), para o
 * desenho não pular a cada atualização.
 *
 * - **Mouse sobre uma bolinha** (`emphasis.focus: "adjacency"` do ECharts): ela, os
 *   vizinhos e as linhas entre eles mantêm a cor; o resto esmaece.
 * - **Termo aberto** (clicado): só ele ganha destaque, com contorno grosso, bolinha um
 *   pouco maior e rótulo em negrito. O resto do grafo fica normal.
 * - **Nomes:** todos os rótulos estão ligados, e o ECharts esconde só os que se sobrepõem
 *   a outros (`labelLayout.hideOverlap`), dando prioridade às bolinhas maiores. Ao dar zoom
 *   as bolinhas se afastam, as sobreposições somem e os nomes vão aparecendo.
 */
export function opcoesGrafo({
  indice,
  visiveis,
  posicoes,
  selecionado,
  cores,
}: {
  indice: IndiceGlossario;
  visiveis: readonly string[];
  posicoes: ReadonlyMap<string, Posicao>;
  selecionado: string | null;
  cores: CoresTema;
}) {
  const maximoLigacoes = Math.max(0, ...indice.termos.map((t) => grau(indice, t.slug)));

  const nos = visiveis.flatMap((slug) => {
    const termo = indice.porSlug.get(slug);
    const posicao = posicoes.get(slug);
    if (!termo || !posicao) return [];
    const ligacoes = grau(indice, slug);
    const ehSelecionado = slug === selecionado;
    return [
      {
        id: slug,
        name: termo.titulo,
        resumo: termo.resumo,
        x: posicao.x,
        y: posicao.y,
        symbolSize: tamanhoDoNo(ligacoes, maximoLigacoes) + (ehSelecionado ? 6 : 0),
        itemStyle: {
          color: cores.series[indiceCategoria(termo.categoria)] ?? cores.caixa,
          borderColor: ehSelecionado ? cores.texto : cores.fundo,
          borderWidth: ehSelecionado ? 3 : 1.5,
        },
        label: {
          show: true,
          fontWeight: ehSelecionado ? ("bold" as const) : ("normal" as const),
        },
      },
    ];
  });

  const ligacoes = arestasEntre(indice, visiveis).map(({ a, b }) => ({ source: a, target: b }));

  return {
    animationDurationUpdate: 300,
    tooltip: {
      ...tooltipCartao(cores),
      trigger: "item",
      extraCssText:
        "border-radius: 10px; box-shadow: var(--sombra-elevada); max-width: 280px; white-space: normal;",
      formatter: (p: { dataType?: string; data?: DadoNo }) =>
        p.dataType === "node" && p.data
          ? `<strong>${escaparHtml(p.data.name)}</strong><br/>${escaparHtml(p.data.resumo)}`
          : "",
    },
    series: [
      {
        type: "graph",
        layout: "none",
        roam: true,
        scaleLimit: { min: 0.4, max: 4 },
        // Sem top/bottom/left/right fixos: com as quatro margens o ECharts estica o desenho
        // para preencher a caixa (bolinhas viram elipses). Sem elas, ele encaixa o grafo
        // em ~80% da área mantendo a proporção. O zoom inicial abaixo de 1 deixa folga
        // para os rótulos das bolinhas da borda.
        zoom: 0.9,
        label: {
          position: "bottom",
          distance: 4,
          color: cores.texto,
          fontFamily: '"Segoe UI", system-ui, sans-serif',
          fontSize: 11,
        },
        // Reavaliado a cada zoom ou arraste (o ECharts refaz o layout dos rótulos no roam).
        labelLayout: { hideOverlap: true },
        lineStyle: { color: comAlfa(cores.textoSuave, 0.28), curveness: 0 },
        emphasis: {
          focus: "adjacency",
          label: { show: true },
          lineStyle: { width: 2, color: comAlfa(cores.textoSuave, 0.9) },
        },
        blur: {
          itemStyle: { opacity: OPACIDADE_ESMAECIDA },
          label: { opacity: OPACIDADE_ESMAECIDA },
          lineStyle: { opacity: 0.08 },
        },
        data: nos,
        links: ligacoes,
      },
    ],
  };
}
