import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTemaStore } from "@/theme/tema";

// Este arquivo testa os invólucros reais (o setup troca os gráficos por marcadores).
vi.unmock("@/components/graficos/GraficoECharts");
vi.unmock("@/components/graficos/GraficoPreco");

const echarts = vi.hoisted(() => ({
  setOption: vi.fn(),
  dispose: vi.fn(),
  resize: vi.fn(),
  init: vi.fn(),
}));
vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: echarts.init,
}));

const lw = vi.hoisted(() => ({
  setData: vi.fn(),
  addSeries: vi.fn(),
  remove: vi.fn(),
  createChart: vi.fn(),
}));
vi.mock("lightweight-charts", () => ({
  AreaSeries: "AreaSeries",
  ColorType: { Solid: "solid" },
  createChart: lw.createChart,
}));

const { GraficoECharts } = await import("./GraficoECharts");
const { GraficoPreco } = await import("./GraficoPreco");

beforeEach(() => {
  vi.clearAllMocks();
  echarts.init.mockReturnValue({
    setOption: echarts.setOption,
    dispose: echarts.dispose,
    resize: echarts.resize,
  });
  lw.addSeries.mockReturnValue({ setData: lw.setData });
  lw.createChart.mockReturnValue({
    addSeries: lw.addSeries,
    remove: lw.remove,
    timeScale: () => ({ fitContent: vi.fn() }),
  });
  // Tokens do tema escuro em rgb (como se o CSS estivesse carregado).
  document.documentElement.style.setProperty("--grafico-1", "rgb(139, 123, 255)");
  document.documentElement.style.setProperty("--foreground", "rgb(236, 235, 247)");
});

describe("GraficoECharts", () => {
  it("cria o gráfico, aplica as opções e libera ao desmontar", () => {
    const opcoes = { series: [{ type: "pie", data: [] }] };
    const { unmount } = render(<GraficoECharts opcoes={opcoes} rotulo="Alocação" />);
    expect(screen.getByRole("img", { name: "Alocação" })).toBeInTheDocument();
    expect(echarts.init).toHaveBeenCalledTimes(1);
    expect(echarts.setOption).toHaveBeenCalledWith(opcoes, { notMerge: true });
    unmount();
    expect(echarts.dispose).toHaveBeenCalled();
  });

  it("redesenha quando as opções mudam (ex.: troca de tema)", () => {
    const { rerender } = render(<GraficoECharts opcoes={{ a: 1 }} rotulo="X" />);
    rerender(<GraficoECharts opcoes={{ a: 2 }} rotulo="X" />);
    expect(echarts.setOption).toHaveBeenLastCalledWith({ a: 2 }, { notMerge: true });
    expect(echarts.init).toHaveBeenCalledTimes(1);
  });

  it("falha da biblioteca não derruba a tela", () => {
    echarts.init.mockImplementation(() => {
      throw new Error("sem canvas");
    });
    render(<GraficoECharts opcoes={{}} rotulo="X" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível desenhar o gráfico.");
  });
});

describe("GraficoPreco (Lightweight Charts)", () => {
  it("série de área com a cor do token --grafico-1 e degradê 35% → 0%", () => {
    render(
      <GraficoPreco
        rotulo="Preço"
        pontos={[
          { data: "2026-10-28", valor: "49.5" },
          { data: "2026-10-29", valor: "50" },
        ]}
      />,
    );
    const cor = lw.addSeries.mock.calls[0]?.[1] as Record<string, string>;
    // Sem canvas no jsdom, a cor fica no formato original do token (rgb aqui).
    expect(cor.lineColor).toBe("rgb(139, 123, 255)");
    expect(cor.topColor).toBe("rgba(139, 123, 255, 0.35)");
    expect(cor.bottomColor).toBe("rgba(139, 123, 255, 0)");
    expect(lw.setData).toHaveBeenLastCalledWith([
      { time: "2026-10-28", value: 49.5 },
      { time: "2026-10-29", value: 50 },
    ]);
  });

  it("refaz o gráfico ao trocar o tema", () => {
    useTemaStore.setState({ tema: "escuro" });
    render(<GraficoPreco rotulo="Preço" pontos={[]} />);
    expect(lw.createChart).toHaveBeenCalledTimes(1);
    act(() => {
      document.documentElement.style.setProperty("--grafico-1", "rgb(91, 61, 245)");
      useTemaStore.setState({ tema: "claro" });
    });
    expect(lw.createChart).toHaveBeenCalledTimes(2);
    expect(lw.remove).toHaveBeenCalledTimes(1);
    const cor = lw.addSeries.mock.calls.at(-1)?.[1] as Record<string, string>;
    expect(cor.lineColor).toBe("rgb(91, 61, 245)");
    act(() => {
      useTemaStore.setState({ tema: "escuro" });
    });
  });
});
