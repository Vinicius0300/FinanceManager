import { useMemo } from "react";
import { CartaoMetrica } from "@/components/CartaoMetrica";
import {
  eixoCategorias,
  eixoValores,
  legendaInferior,
  tooltipCartao,
} from "@/components/graficos/estiloGrafico";
import { GraficoECharts } from "@/components/graficos/GraficoECharts";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { ehZero, paraGrafico } from "@/lib/decimal";
import { formatarMesAno, formatarMesCurto, formatarMoeda, plural } from "@/lib/formatacao";
import { useCoresTema } from "@/theme/cores";
import type { ResumoHistorico } from "./consultas";
import { useValoresOcultos } from "@/lib/valores-ocultos";

/** Cartões do resumo do filtro: totais calculados pela API (o front não soma). */
export function CartoesResumo({
  resumo,
  carregando,
}: {
  resumo: ResumoHistorico | undefined;
  carregando: boolean;
}) {
  const t = resumo?.totais;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      <CartaoMetrica
        titulo="Total comprado"
        carregando={carregando}
        valor={formatarMoeda(t?.total_comprado)}
        apoio="compras e aportes"
      />
      <CartaoMetrica
        titulo="Total vendido"
        carregando={carregando}
        valor={formatarMoeda(t?.total_vendido)}
        apoio="vendas e resgates"
      />
      <CartaoMetrica
        titulo="Lucro realizado"
        carregando={carregando}
        valor={<ValorFinanceiro valor={t?.lucro_realizado} />}
        apoio="vendas e resgates do filtro"
      />
      <CartaoMetrica
        titulo="Proventos recebidos"
        carregando={carregando}
        valor={formatarMoeda(t?.proventos_liquidos)}
        apoio={
          t && (
            <>
              líquidos de imposto
              {!ehZero(t.impostos_retidos) && (
                <> · {formatarMoeda(t.impostos_retidos)} de IR retido</>
              )}
            </>
          )
        }
      />
      <CartaoMetrica
        titulo="Taxas pagas"
        carregando={carregando}
        valor={formatarMoeda(t?.taxas)}
        apoio={t && plural(t.operacoes_com_taxas, "operação", "operações")}
      />
    </div>
  );
}

/** Barras mensais: compras e aportes, vendas e resgates, proventos (cores fixas por série). */
export function GraficoMensal({ resumo }: { resumo: ResumoHistorico }) {
  const ocultos = useValoresOcultos();
  const cores = useCoresTema();
  const opcoes = useMemo(() => {
    const series = [
      { nome: "Compras e aportes", campo: "compras", cor: cores.series[3] },
      { nome: "Vendas e resgates", campo: "vendas", cor: cores.series[2] },
      { nome: "Proventos", campo: "proventos", cor: cores.series[4] },
    ] as const;
    const meses = resumo.serie;
    return {
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      legend: { ...legendaInferior(cores), top: 0, bottom: undefined, left: undefined, right: 0 },
      tooltip: {
        ...tooltipCartao(cores),
        trigger: "axis",
        formatter: (itens: { dataIndex: number }[]) => {
          const ponto = meses[itens[0]?.dataIndex ?? 0];
          if (!ponto) return "";
          return [
            formatarMesAno(ponto.mes),
            ...series.map(
              (s) => `${s.nome}: ${formatarMoeda(ponto[s.campo], "BRL", { ocultar: ocultos })}`,
            ),
          ].join("<br/>");
        },
      },
      xAxis: { ...eixoCategorias(cores), data: meses.map((p) => formatarMesCurto(p.mes)) },
      yAxis: { ...eixoValores(cores), axisLabel: { show: false } },
      series: series.map((s) => ({
        type: "bar",
        name: s.nome,
        barMaxWidth: 18,
        itemStyle: { color: s.cor, borderRadius: [4, 4, 0, 0] },
        data: meses.map((p) => paraGrafico(p[s.campo])),
      })),
    };
  }, [resumo, cores, ocultos]);
  return (
    <GraficoECharts opcoes={opcoes} rotulo="Compras, vendas e proventos por mês" altura={260} />
  );
}
