import { useMemo } from "react";
import { GraficoECharts } from "@/components/graficos/GraficoECharts";
import { nomeDoTipo, useTiposAtivo } from "@/lib/consultas-comuns";
import { paraGrafico } from "@/lib/decimal";
import { ORDEM_TIPOS_ATIVO, prepararFatias, type FatiaEntrada } from "@/lib/fatias";
import { formatarData, formatarMesCurto, formatarMoeda, formatarRazao } from "@/lib/formatacao";
import { comAlfa, useCoresTema, type CoresTema } from "@/theme/cores";
import type { Evolucao, Fatia } from "./consultas";

/** Legenda e tooltip sempre com nome e valor (âmbar e turquesa têm pouco contraste no claro). */
function tooltipBase(cores: CoresTema) {
  return {
    backgroundColor: cores.cartao,
    borderColor: cores.borda,
    textStyle: { color: cores.texto },
  };
}

/** Pizza de alocação por tipo de ativo, com a fatia caixa (cores fixas por tipo). */
export function GraficoAlocacao({ fatias }: { fatias: readonly Fatia[] }) {
  const cores = useCoresTema();
  const tipos = useTiposAtivo();
  const opcoes = useMemo(() => {
    const entrada: FatiaEntrada[] = fatias.map((f) => ({
      categoria: f.grupo,
      rotulo: f.grupo === "caixa" ? "Caixa" : nomeDoTipo(tipos.data, f.grupo),
      valor: f.valor,
      percentual: f.percentual,
    }));
    const prontas = prepararFatias(entrada, ORDEM_TIPOS_ATIVO, cores);
    const textos = new Map(
      prontas.map((f) => [
        f.rotulo,
        `${formatarMoeda(f.valor)} (${formatarRazao(f.percentual ?? null)})`,
      ]),
    );
    return {
      tooltip: {
        ...tooltipBase(cores),
        trigger: "item",
        formatter: (p: { name: string }) => `${p.name}: ${textos.get(p.name) ?? ""}`,
      },
      legend: {
        orient: "vertical",
        right: 0,
        top: "middle",
        textStyle: { color: cores.texto },
        formatter: (nome: string) => `${nome}  ${textos.get(nome) ?? ""}`,
      },
      series: [
        {
          type: "pie",
          radius: ["45%", "72%"],
          center: ["30%", "50%"],
          label: { show: false },
          itemStyle: { borderColor: cores.fundo, borderWidth: 2 },
          data: prontas.map((f) => ({
            name: f.rotulo,
            value: paraGrafico(f.valor),
            itemStyle: { color: f.cor },
          })),
        },
      ],
    };
  }, [fatias, tipos.data, cores]);
  return <GraficoECharts opcoes={opcoes} rotulo="Alocação da carteira por tipo de ativo" />;
}

/** Linha do patrimônio (--grafico-1) com área em degradê do próprio token (35% → 0%). */
export function GraficoEvolucao({ evolucao }: { evolucao: Evolucao }) {
  const cores = useCoresTema();
  const opcoes = useMemo(() => {
    const linha = cores.series[0] ?? cores.texto;
    const pontos = evolucao.pontos;
    const textos = pontos.map(
      (p) =>
        `${formatarData(p.data)}<br/>Patrimônio: ${formatarMoeda(p.patrimonio)}<br/>` +
        `Investimentos: ${formatarMoeda(p.investimentos)}<br/>Caixa: ${formatarMoeda(p.caixa)}`,
    );
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        ...tooltipBase(cores),
        trigger: "axis",
        formatter: (itens: { dataIndex: number }[]) => textos[itens[0]?.dataIndex ?? 0] ?? "",
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: pontos.map((p) => p.data),
        axisLabel: { color: cores.textoSuave, formatter: (d: string) => formatarMesCurto(d) },
        axisLine: { lineStyle: { color: cores.borda } },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: {
          color: cores.textoSuave,
          formatter: (v: number) => formatarMoeda(String(Math.round(v)), "BRL", { casas: 0 }),
        },
        splitLine: { lineStyle: { color: cores.borda } },
      },
      series: [
        {
          type: "line",
          name: "Patrimônio",
          showSymbol: false,
          data: pontos.map((p) => paraGrafico(p.patrimonio)),
          lineStyle: { color: linha, width: 2 },
          itemStyle: { color: linha },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: comAlfa(linha, 0.35) },
                { offset: 1, color: comAlfa(linha, 0) },
              ],
            },
          },
        },
      ],
    };
  }, [evolucao, cores]);
  return <GraficoECharts opcoes={opcoes} rotulo="Evolução do patrimônio" />;
}
