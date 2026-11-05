import { BarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { init, use as registrarModulos, type EChartsCoreOption, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// Só os módulos usados (tree-shaking): pizza, barras e linha.
registrarModulos([
  PieChart,
  BarChart,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

/** O que o ECharts informa no clique (só os campos usados pelo app). */
export interface EventoCliqueGrafico {
  dataType?: string; // "node" ou "edge" no grafo
  name?: string;
  data?: unknown;
}

/**
 * Invólucro do ECharts: cria o gráfico no elemento, aplica as opções (que já vêm com as
 * cores lidas dos tokens) e acompanha o tamanho do contêiner. Quando o tema muda, as
 * opções mudam e o gráfico é redesenhado. Uma falha do ECharts não derruba a tela.
 * `aoClicar` (opcional) recebe o clique num elemento do gráfico (ex.: nó do glossário).
 */
export function GraficoECharts({
  opcoes,
  rotulo,
  altura = 280,
  className,
  aoClicar,
}: {
  opcoes: EChartsCoreOption;
  rotulo: string;
  altura?: number;
  className?: string;
  aoClicar?: (evento: EventoCliqueGrafico) => void;
}) {
  const elemento = useRef<HTMLDivElement>(null);
  const grafico = useRef<ECharts | null>(null);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    const alvo = elemento.current;
    if (!alvo) return;
    let instancia: ECharts;
    try {
      instancia = init(alvo, null, { renderer: "canvas" });
    } catch {
      // Falha da biblioteca externa (ex.: sem canvas): mostra o aviso no lugar do gráfico.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFalhou(true);
      return;
    }
    grafico.current = instancia;
    const observador =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            instancia.resize();
          });
    observador?.observe(alvo);
    return () => {
      observador?.disconnect();
      instancia.dispose();
      grafico.current = null;
    };
  }, []);

  useEffect(() => {
    try {
      grafico.current?.setOption(opcoes, { notMerge: true });
    } catch {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFalhou(true);
    }
  }, [opcoes]);

  useEffect(() => {
    const instancia = grafico.current;
    if (!instancia || !aoClicar) return;
    const tratar = (evento: unknown) => {
      aoClicar(evento as EventoCliqueGrafico);
    };
    instancia.on("click", tratar);
    return () => {
      instancia.off("click", tratar);
    };
  }, [aoClicar]);

  if (falhou) {
    return (
      <p role="alert" className="py-6 text-center text-sm text-muted-foreground">
        Não foi possível desenhar o gráfico.
      </p>
    );
  }
  return (
    <div
      ref={elemento}
      role="img"
      aria-label={rotulo}
      className={cn("w-full", className)}
      style={{ height: altura }}
    />
  );
}
