import { useMemo } from "react";
import {
  areaDegrade,
  eixoCategorias,
  eixoValores,
  opcoesRosca,
  tooltipCartao,
} from "@/components/graficos/estiloGrafico";
import { GraficoECharts } from "@/components/graficos/GraficoECharts";
import { nomeDoTipo, useTiposAtivo } from "@/lib/consultas-comuns";
import { paraGrafico } from "@/lib/decimal";
import { ORDEM_TIPOS_ATIVO, prepararFatias, type FatiaEntrada } from "@/lib/fatias";
import { formatarData, formatarMesCurto, formatarMoeda, formatarRazao } from "@/lib/formatacao";
import { useCoresTema } from "@/theme/cores";
import type { Evolucao, Fatia } from "./consultas";
import { useValoresOcultos } from "@/lib/valores-ocultos";

/**
 * Rosca de alocação por tipo de ativo, com a fatia caixa (regra das 6 cores em
 * `lib/fatias`). Legenda e tooltip sempre com nome e valor (âmbar e turquesa têm pouco
 * contraste no claro), o que também serve de resumo textual do gráfico.
 */
export function GraficoAlocacao({ fatias }: { fatias: readonly Fatia[] }) {
  const ocultos = useValoresOcultos();
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
    return opcoesRosca(
      prontas.map((f) => ({
        rotulo: f.rotulo,
        valor: paraGrafico(f.valor),
        cor: f.cor,
        texto: `${formatarMoeda(f.valor, "BRL", { ocultar: ocultos })} (${formatarRazao(f.percentual ?? null)})`,
      })),
      cores,
    );
  }, [fatias, tipos.data, cores, ocultos]);
  return <GraficoECharts opcoes={opcoes} rotulo="Alocação da carteira por tipo de ativo" />;
}

/** Linha do patrimônio (--grafico-1) com área em degradê do próprio token (35% → 0%). */
export function GraficoEvolucao({ evolucao }: { evolucao: Evolucao }) {
  const ocultos = useValoresOcultos();
  const cores = useCoresTema();
  const opcoes = useMemo(() => {
    const linha = cores.series[0] ?? cores.texto;
    const pontos = evolucao.pontos;
    const textos = pontos.map(
      (p) =>
        `${formatarData(p.data)}<br/>Patrimônio: ${formatarMoeda(p.patrimonio, "BRL", { ocultar: ocultos })}<br/>` +
        `Investimentos: ${formatarMoeda(p.investimentos, "BRL", { ocultar: ocultos })}<br/>Caixa: ${formatarMoeda(p.caixa, "BRL", { ocultar: ocultos })}`,
    );
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        ...tooltipCartao(cores),
        trigger: "axis",
        formatter: (itens: { dataIndex: number }[]) => textos[itens[0]?.dataIndex ?? 0] ?? "",
      },
      xAxis: {
        ...eixoCategorias(cores),
        boundaryGap: false,
        data: pontos.map((p) => p.data),
        axisLabel: {
          ...eixoCategorias(cores).axisLabel,
          formatter: (d: string) => formatarMesCurto(d),
        },
      },
      yAxis: {
        ...eixoValores(cores),
        scale: true,
        axisLabel: {
          ...eixoValores(cores).axisLabel,
          formatter: (v: number) =>
            formatarMoeda(String(Math.round(v)), "BRL", { casas: 0, ocultar: ocultos }),
        },
      },
      series: [
        {
          type: "line",
          name: "Patrimônio",
          showSymbol: false,
          data: pontos.map((p) => paraGrafico(p.patrimonio)),
          lineStyle: { color: linha, width: 2 },
          itemStyle: { color: linha },
          areaStyle: areaDegrade(linha),
        },
      ],
    };
  }, [evolucao, cores, ocultos]);
  return <GraficoECharts opcoes={opcoes} rotulo="Evolução do patrimônio" altura={300} />;
}
