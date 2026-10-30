import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom não tem canvas: os gráficos viram um marcador com o rótulo acessível e os dados
// recebidos (as cores e opções do ECharts têm testes próprios).
vi.mock("@/components/graficos/GraficoECharts", () => ({
  GraficoECharts: ({ rotulo, opcoes }: { rotulo: string; opcoes: unknown }) => (
    <div role="img" aria-label={rotulo} data-opcoes={JSON.stringify(opcoes)} />
  ),
}));
vi.mock("@/components/graficos/GraficoPreco", () => ({
  GraficoPreco: ({ rotulo, pontos }: { rotulo: string; pontos: unknown[] }) => (
    <div role="img" aria-label={rotulo} data-pontos={pontos.length} />
  ),
}));
