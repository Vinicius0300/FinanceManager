import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { paraGrafico } from "@/lib/decimal";
import { comAlfa, useCoresTema } from "@/theme/cores";

export interface PontoPreco {
  data: string; // "2026-10-29"
  valor: string; // decimal em texto
}

/**
 * Série de preço de um ativo (TradingView Lightweight Charts). Cores vêm dos tokens e o
 * gráfico é refeito ao trocar o tema. Valores convertidos para número só para desenhar.
 */
export function GraficoPreco({
  pontos,
  rotulo,
  altura = 260,
}: {
  pontos: readonly PontoPreco[];
  rotulo: string;
  altura?: number;
}) {
  const elemento = useRef<HTMLDivElement>(null);
  const serie = useRef<ISeriesApi<"Area"> | null>(null);
  const grafico = useRef<IChartApi | null>(null);
  const cores = useCoresTema();
  const [falhou, setFalhou] = useState(false);
  const linha = cores.series[0] ?? cores.texto;

  useEffect(() => {
    const alvo = elemento.current;
    if (!alvo) return;
    try {
      const novo = createChart(alvo, {
        height: altura,
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: cores.textoSuave,
          attributionLogo: false,
        },
        grid: { vertLines: { color: cores.borda }, horzLines: { color: cores.borda } },
        rightPriceScale: { borderColor: cores.borda },
        timeScale: { borderColor: cores.borda },
        localization: { locale: "pt-BR" },
      });
      grafico.current = novo;
      serie.current = novo.addSeries(AreaSeries, {
        lineColor: linha,
        topColor: comAlfa(linha, 0.35),
        bottomColor: comAlfa(linha, 0),
        lineWidth: 2,
      });
    } catch {
      // Falha da biblioteca externa: mostra o aviso no lugar do gráfico.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFalhou(true);
    }
    return () => {
      grafico.current?.remove();
      grafico.current = null;
      serie.current = null;
    };
  }, [altura, cores, linha]);

  useEffect(() => {
    try {
      serie.current?.setData(pontos.map((p) => ({ time: p.data, value: paraGrafico(p.valor) })));
      grafico.current?.timeScale().fitContent();
    } catch {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFalhou(true);
    }
  }, [pontos, cores]);

  if (falhou) {
    return (
      <p role="alert" className="py-6 text-center text-sm text-muted-foreground">
        Não foi possível desenhar o gráfico de preço.
      </p>
    );
  }
  return (
    <div
      ref={elemento}
      role="img"
      aria-label={rotulo}
      className="w-full"
      style={{ height: altura }}
    />
  );
}
