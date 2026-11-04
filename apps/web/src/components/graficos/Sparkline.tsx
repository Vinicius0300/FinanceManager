import { useMemo } from "react";
import { paraGrafico } from "@/lib/decimal";
import { useCoresTema } from "@/theme/cores";
import { areaDegrade } from "./estiloGrafico";
import { GraficoECharts } from "./GraficoECharts";

export interface PontoSparkline {
  data: string;
  valor: string; // decimal em texto (convertido para número só para desenhar)
}

/**
 * Mini gráfico de linha (sem eixos, grade nem tooltip) para os cartões de métrica.
 * O resumo textual (período e valores inicial e final) vai no `rotulo`, para leitores de
 * tela. Menos de 2 pontos não desenham nada.
 */
export function Sparkline({
  pontos,
  rotulo,
  altura = 40,
}: {
  pontos: readonly PontoSparkline[];
  rotulo: string;
  altura?: number;
}) {
  const cores = useCoresTema();
  const opcoes = useMemo(() => {
    const cor = cores.series[0] ?? cores.texto;
    return {
      animation: false,
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: "category", show: false, boundaryGap: false, data: pontos.map((p) => p.data) },
      yAxis: { type: "value", show: false, scale: true },
      series: [
        {
          type: "line",
          data: pontos.map((p) => paraGrafico(p.valor)),
          showSymbol: false,
          silent: true,
          smooth: 0.25,
          lineStyle: { color: cor, width: 1.5 },
          areaStyle: areaDegrade(cor, 0.3),
        },
      ],
    };
  }, [pontos, cores]);
  if (pontos.length < 2) return null;
  return <GraficoECharts opcoes={opcoes} rotulo={rotulo} altura={altura} />;
}
