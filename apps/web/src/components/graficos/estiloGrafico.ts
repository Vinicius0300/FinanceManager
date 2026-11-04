import { comAlfa, type CoresTema } from "@/theme/cores";

/**
 * Estilo comum dos gráficos (Parte 5A), igual nos dois temas porque tudo vem dos tokens:
 * grade só horizontal e discreta, eixos em texto suave, tooltip com aparência de cartão,
 * legenda embaixo com marcadores redondos e área com degradê do próprio token.
 *
 * As funções devolvem fragmentos de opções do ECharts; o Lightweight Charts usa
 * `opcoesLightweight` (mesmas cores e grade).
 */

const FONTE = '"Segoe UI", system-ui, sans-serif';
const TAMANHO_FONTE = 11;

export function tooltipCartao(cores: CoresTema) {
  return {
    backgroundColor: cores.cartao,
    borderColor: cores.borda,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: cores.texto, fontFamily: FONTE, fontSize: 12 },
    extraCssText: "border-radius: 10px; box-shadow: var(--sombra-elevada);",
  };
}

export function legendaInferior(cores: CoresTema) {
  return {
    bottom: 0,
    left: "center",
    icon: "circle",
    itemWidth: 8,
    itemHeight: 8,
    itemGap: 16,
    textStyle: { color: cores.textoSuave, fontFamily: FONTE, fontSize: TAMANHO_FONTE },
  };
}

/** Eixo de categorias (datas, meses) sem marcações, com a linha base discreta. */
export function eixoCategorias(cores: CoresTema) {
  return {
    type: "category" as const,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: cores.borda } },
    axisLabel: { color: cores.textoSuave, fontFamily: FONTE, fontSize: TAMANHO_FONTE },
  };
}

/** Eixo de valores sem linha própria; só a grade horizontal tracejada e suave. */
export function eixoValores(cores: CoresTema) {
  return {
    type: "value" as const,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: cores.textoSuave, fontFamily: FONTE, fontSize: TAMANHO_FONTE },
    splitLine: { lineStyle: { color: cores.borda, type: "dashed" as const } },
  };
}

/** Área com degradê vertical do token (opaco em cima, transparente embaixo). */
export function areaDegrade(cor: string, alfaTopo = 0.35) {
  return {
    color: {
      type: "linear",
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: [
        { offset: 0, color: comAlfa(cor, alfaTopo) },
        { offset: 1, color: comAlfa(cor, 0) },
      ],
    },
  };
}

/** Mesmo visual no Lightweight Charts (série de preço do detalhe do ativo). */
export function opcoesLightweight(cores: CoresTema) {
  return {
    layout: {
      background: { type: "solid" as const, color: "transparent" },
      textColor: cores.textoSuave,
      fontFamily: FONTE,
      fontSize: TAMANHO_FONTE,
      attributionLogo: false,
    },
    grid: { vertLines: { visible: false }, horzLines: { color: cores.borda } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderColor: cores.borda },
    crosshair: {
      vertLine: { color: cores.textoSuave, labelBackgroundColor: cores.cartao },
      horzLine: { color: cores.textoSuave, labelBackgroundColor: cores.cartao },
    },
  };
}

export interface FatiaRosca {
  rotulo: string;
  valor: number; // só para desenhar (o texto exato vai em `texto`)
  cor: string;
  texto: string; // valor formatado (ex.: "R$ 1.234,56 (12,34%)")
}

/**
 * Rosca com legenda à direita (nome em cima, valor embaixo), usada na alocação e nas
 * categorias de despesa. Rosca de tamanho fixo para a legenda nunca a cobrir em cartões
 * estreitos; a legenda com os valores serve de resumo textual do gráfico.
 */
export function opcoesRosca(fatias: readonly FatiaRosca[], cores: CoresTema) {
  const textos = new Map(fatias.map((f) => [f.rotulo, f.texto]));
  return {
    tooltip: {
      ...tooltipCartao(cores),
      trigger: "item",
      formatter: (p: { name: string }) => `${p.name}: ${textos.get(p.name) ?? ""}`,
    },
    legend: {
      orient: "vertical",
      left: 210,
      top: "middle",
      icon: "circle",
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 8,
      formatter: (nome: string) => `{nome|${nome}}\n{valor|${textos.get(nome) ?? ""}}`,
      textStyle: {
        fontFamily: FONTE,
        rich: {
          nome: { color: cores.texto, fontSize: 12, lineHeight: 16, fontFamily: FONTE },
          valor: { color: cores.textoSuave, fontSize: 11, lineHeight: 14, fontFamily: FONTE },
        },
      },
    },
    series: [
      {
        type: "pie",
        radius: [62, 96],
        center: [100, "50%"],
        label: { show: false },
        emphasis: { scale: true, scaleSize: 4 },
        itemStyle: { borderColor: cores.fundo, borderWidth: 2, borderRadius: 4 },
        data: fatias.map((f) => ({ name: f.rotulo, value: f.valor, itemStyle: { color: f.cor } })),
      },
    ],
  };
}
