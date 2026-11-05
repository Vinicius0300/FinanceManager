import { describe, expect, it } from "vitest";
import type { CoresTema } from "@/theme/cores";
import { montarIndice } from "./dominio/indice";
import { calcularPosicoes } from "./dominio/layout";
import type { Termo } from "./dominio/termo";
import {
  escaparHtml,
  OPACIDADE_ESMAECIDA,
  opcoesGrafo,
  tamanhoDoNo,
  termosVisiveis,
} from "./grafo";

const CORES: CoresTema = {
  series: [
    "rgb(1, 1, 1)",
    "rgb(2, 2, 2)",
    "rgb(3, 3, 3)",
    "rgb(4, 4, 4)",
    "rgb(5, 5, 5)",
    "rgb(6, 6, 6)",
  ],
  caixa: "rgb(9, 9, 9)",
  texto: "rgb(10, 10, 10)",
  textoSuave: "rgb(20, 20, 20)",
  borda: "rgb(30, 30, 30)",
  fundo: "rgb(40, 40, 40)",
  cartao: "rgb(50, 50, 50)",
  positivo: "rgb(60, 60, 60)",
  negativo: "rgb(70, 70, 70)",
};

function termo(slug: string, categoria: Termo["categoria"], links: string[] = []): Termo {
  return {
    slug,
    titulo: slug.toUpperCase(),
    categoria,
    sinonimos: [],
    resumo: `Resumo <b>${slug}</b>`,
    revisadoEm: "2026-11",
    corpo: "",
    links,
  };
}

// a(conceitos) — b(indicadores) — c(renda-fixa) — d(renda-fixa); e(impostos) solto.
const INDICE = montarIndice([
  termo("a", "conceitos", ["b"]),
  termo("b", "indicadores", ["c"]),
  termo("c", "renda-fixa", ["d"]),
  termo("d", "renda-fixa"),
  termo("e", "impostos"),
]);
const TODAS = new Set(["conceitos", "indicadores", "renda-fixa", "impostos"]);

interface No {
  id: string;
  symbolSize: number;
  itemStyle: { color: string; opacity?: number; borderWidth: number };
  label: { show: boolean; fontWeight: string };
}
interface Ligacao {
  source: string;
  target: string;
  lineStyle?: unknown;
}
type Opcoes = {
  series: {
    data: No[];
    links: Ligacao[];
    layout: string;
    labelLayout: unknown;
    emphasis: { focus: string };
    blur: { itemStyle: { opacity: number } };
  }[];
  tooltip: { formatter: (p: unknown) => string };
};

function opcoes(visiveis: string[], selecionado: string | null) {
  return opcoesGrafo({
    indice: INDICE,
    visiveis,
    posicoes: calcularPosicoes(visiveis, INDICE.arestas),
    selecionado,
    cores: CORES,
  }) as unknown as Opcoes;
}

describe("termos visíveis no grafo", () => {
  it("todos das categorias ligadas, na ordem do índice", () => {
    expect(termosVisiveis(INDICE, TODAS, null)).toEqual(["a", "b", "c", "d", "e"]);
    const semRendaFixa = new Set(["conceitos", "indicadores", "impostos"]);
    expect(termosVisiveis(INDICE, semRendaFixa, null)).toEqual(["a", "b", "e"]);
  });

  it("o termo aberto aparece mesmo com a categoria desligada", () => {
    expect(termosVisiveis(INDICE, new Set(["conceitos"]), "c")).toEqual(["a", "c"]);
  });
});

describe("opções do grafo", () => {
  it("tamanho pelo número de ligações, com mínimo e máximo", () => {
    // 8 + 18 × √(ligações ÷ máximo), arredondado.
    expect(tamanhoDoNo(0, 16)).toBe(8);
    expect(tamanhoDoNo(4, 16)).toBe(17); // 8 + 18 × 0,5
    expect(tamanhoDoNo(16, 16)).toBe(26);
    expect(tamanhoDoNo(32, 16)).toBe(26); // nunca passa do máximo
    expect(tamanhoDoNo(3, 0)).toBe(8); // glossário sem ligações
  });

  it("todos os nomes ficam ligados; o ECharts esconde só os sobrepostos (some com o zoom)", () => {
    const serie = opcoes(["a", "b", "c", "d", "e"], null).series[0];
    expect(serie?.data.every((n) => n.label.show)).toBe(true);
    expect(serie?.labelLayout).toEqual({ hideOverlap: true });
  });

  it("posições prontas (layout none), cor pela categoria e só arestas entre visíveis", () => {
    const o = opcoes(["a", "b", "e"], null);
    const serie = o.series[0];
    expect(serie?.layout).toBe("none");
    expect(serie?.data.map((n) => [n.id, n.itemStyle.color])).toEqual([
      ["a", "rgb(1, 1, 1)"],
      ["b", "rgb(2, 2, 2)"],
      ["e", "rgb(5, 5, 5)"],
    ]);
    expect(serie?.links.map((l) => `${l.source}-${l.target}`)).toEqual(["a-b"]);
    // Poucos nós: todos os rótulos aparecem.
    expect(serie?.data.every((n) => n.label.show)).toBe(true);
  });

  it("mouse sobre uma bolinha: vizinhos mantêm a cor e o resto esmaece (ECharts)", () => {
    const serie = opcoes(["a", "b"], null).series[0];
    expect(serie?.emphasis.focus).toBe("adjacency");
    expect(serie?.blur.itemStyle.opacity).toBe(OPACIDADE_ESMAECIDA);
  });

  it("termo aberto: só ele ganha destaque; nada fica esmaecido", () => {
    const serie = opcoes(["a", "b", "c", "d", "e"], "b").series[0];
    const selecionado = serie?.data.find((n) => n.id === "b");
    expect(selecionado?.itemStyle.borderWidth).toBe(3);
    expect(selecionado?.symbolSize).toBe(tamanhoDoNo(2, 2) + 6); // b é o mais ligado
    expect(selecionado?.label.fontWeight).toBe("bold");
    const outros = serie?.data.filter((n) => n.id !== "b") ?? [];
    expect(outros.every((n) => n.itemStyle.borderWidth === 1.5)).toBe(true);
    expect(outros.every((n) => n.label.fontWeight === "normal")).toBe(true);
    // Sem opacidade própria em nó ou aresta: o esmaecer é só o do mouse.
    expect(serie?.data.every((n) => n.itemStyle.opacity === undefined)).toBe(true);
    expect(serie?.links.every((l) => l.lineStyle === undefined)).toBe(true);
  });

  it("tooltip mostra título e resumo escapados; arestas sem tooltip", () => {
    const o = opcoes(["a", "b"], null);
    expect(
      o.tooltip.formatter({ dataType: "node", data: { name: "A", resumo: "Resumo <b>a</b>" } }),
    ).toBe("<strong>A</strong><br/>Resumo &lt;b&gt;a&lt;/b&gt;");
    expect(o.tooltip.formatter({ dataType: "edge", data: {} })).toBe("");
    expect(escaparHtml(`"a" & 'b'`)).toBe("&quot;a&quot; &amp; &#39;b&#39;");
  });
});
