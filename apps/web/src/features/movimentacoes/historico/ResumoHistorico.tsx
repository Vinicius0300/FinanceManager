import { useMemo } from "react";
import { CartaoMetrica } from "@/components/CartaoMetrica";
import { GraficoECharts } from "@/components/graficos/GraficoECharts";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { ehZero, paraGrafico } from "@/lib/decimal";
import { formatarMesAno, formatarMesCurto, formatarMoeda, plural } from "@/lib/formatacao";
import { useCoresTema } from "@/theme/cores";
import type { ResumoHistorico } from "./consultas";

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
      legend: { top: 0, right: 0, textStyle: { color: cores.texto } },
      tooltip: {
        trigger: "axis",
        backgroundColor: cores.cartao,
        borderColor: cores.borda,
        textStyle: { color: cores.texto },
        formatter: (itens: { dataIndex: number }[]) => {
          const ponto = meses[itens[0]?.dataIndex ?? 0];
          if (!ponto) return "";
          return [
            formatarMesAno(ponto.mes),
            ...series.map((s) => `${s.nome}: ${formatarMoeda(ponto[s.campo])}`),
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: meses.map((p) => formatarMesCurto(p.mes)),
        axisLabel: { color: cores.textoSuave },
        axisLine: { lineStyle: { color: cores.borda } },
      },
      yAxis: {
        type: "value",
        axisLabel: { show: false },
        splitLine: { lineStyle: { color: cores.borda, type: "dashed" } },
      },
      series: series.map((s) => ({
        type: "bar",
        name: s.nome,
        itemStyle: { color: s.cor, borderRadius: [3, 3, 0, 0] },
        data: meses.map((p) => paraGrafico(p[s.campo])),
      })),
    };
  }, [resumo, cores]);
  return (
    <GraficoECharts opcoes={opcoes} rotulo="Compras, vendas e proventos por mês" altura={260} />
  );
}
