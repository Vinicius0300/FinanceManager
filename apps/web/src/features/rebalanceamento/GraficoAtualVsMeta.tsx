import { useMemo } from "react";
import {
  eixoCategorias,
  eixoValores,
  legendaInferior,
  tooltipCartao,
} from "@/components/graficos/estiloGrafico";
import { GraficoECharts } from "@/components/graficos/GraficoECharts";
import { nomeDoTipo, type TipoAtivo } from "@/lib/consultas-comuns";
import { paraGrafico } from "@/lib/decimal";
import { ORDEM_TIPOS_ATIVO } from "@/lib/fatias";
import { formatarPercentual } from "@/lib/formatacao";
import { comAlfa, corDaCategoria, useCoresTema } from "@/theme/cores";
import type { ClassePlano } from "./consultas";

/**
 * Barras agrupadas por classe: "Atual" na cor da classe (ordem fixa de `lib/fatias`) e
 * "Meta" em tom neutro com contorno. Só percentuais (o modo privacidade não esconde nada).
 */
export function GraficoAtualVsMeta({
  classes,
  tipos,
}: {
  classes: readonly ClassePlano[];
  tipos: readonly TipoAtivo[] | undefined;
}) {
  const cores = useCoresTema();
  const opcoes = useMemo(() => {
    const nomes = classes.map((c) => nomeDoTipo(tipos, c.tipo_ativo));
    const textos = classes.map(
      (c, i) =>
        `${nomes[i] ?? ""}<br/>Atual: ${formatarPercentual(c.percentual_atual)}<br/>` +
        `Meta: ${formatarPercentual(c.meta)}`,
    );
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 32, containLabel: true },
      legend: { ...legendaInferior(cores), data: ["Atual", "Meta"] },
      tooltip: {
        ...tooltipCartao(cores),
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (itens: { dataIndex: number }[]) => textos[itens[0]?.dataIndex ?? 0] ?? "",
      },
      xAxis: { ...eixoCategorias(cores), data: nomes },
      yAxis: {
        ...eixoValores(cores),
        axisLabel: { ...eixoValores(cores).axisLabel, formatter: (v: number) => `${v}%` },
      },
      series: [
        {
          name: "Atual",
          type: "bar",
          barMaxWidth: 28,
          itemStyle: { color: cores.series[0], borderRadius: [4, 4, 0, 0] },
          data: classes.map((c) => ({
            value: paraGrafico(c.percentual_atual),
            itemStyle: { color: corDaCategoria(c.tipo_ativo, ORDEM_TIPOS_ATIVO, cores) },
          })),
        },
        {
          name: "Meta",
          type: "bar",
          barMaxWidth: 28,
          itemStyle: {
            color: comAlfa(cores.caixa, 0.35),
            borderColor: cores.textoSuave,
            borderWidth: 1,
            borderType: "dashed",
            borderRadius: [4, 4, 0, 0],
          },
          data: classes.map((c) => paraGrafico(c.meta)),
        },
      ],
    };
  }, [classes, tipos, cores]);
  return (
    <GraficoECharts
      opcoes={opcoes}
      rotulo={`Alocação atual e meta por classe: ${classes
        .map(
          (c) =>
            `${nomeDoTipo(tipos, c.tipo_ativo)} ${formatarPercentual(c.percentual_atual)} (meta ${formatarPercentual(c.meta)})`,
        )
        .join("; ")}`}
    />
  );
}
