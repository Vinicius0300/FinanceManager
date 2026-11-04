import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAnaliseStore } from "@/lib/consultas-comuns";
import { ativo, renderizar, type Chamada } from "@/test/api-falsa";
import { TelaDashboard } from "./TelaDashboard";

const AGORA = new Date(2026, 9, 29, 12);
const limpo = (t: string | null) => (t ?? "").replace(/\u00a0/g, " ");

const RESUMO = {
  data_ref: "2026-10-29",
  instituicao_id: null,
  investimentos_brl: "16101.50",
  caixa_brl: "898.50",
  patrimonio_brl: "17000.00",
  completo: true,
  variacao_dia_brl: "-120.30",
  variacao_dia: "-0.0071",
  rentabilidade: {
    valor_atual: "16101.50",
    custo: "15000",
    lucro_nao_realizado: "1101.50",
    valorizacao: "0.07",
    lucro_realizado: "0",
    proventos: "0",
    rendimentos_bonificacao: "0",
    resultado_total: "1101.50",
    total_investido: "15000.00",
    rentabilidade_total: "0.0734",
  },
  caixas: [],
};

const ROTAS = {
  "GET /api/portfolio/resumo": (c: Chamada) => ({
    ...RESUMO,
    instituicao_id: c.query.get("instituicao_id") ? Number(c.query.get("instituicao_id")) : null,
  }),
  "GET /api/resumo-mensal": {
    ano: 2026,
    mes: 10,
    total_receitas: "8000.00",
    total_despesas: "5500.00",
    saldo: "2500.00",
    por_categoria: [],
  },
  "GET /api/portfolio/alocacao": [
    { grupo: "acao_br", valor: "10000.00", percentual: "0.5882" },
    { grupo: "renda_fixa", valor: "6101.50", percentual: "0.3589" },
    { grupo: "caixa", valor: "898.50", percentual: "0.0529" },
  ],
  "GET /api/portfolio/evolucao": {
    pontos: [
      { data: "2026-10-28", investimentos: "16000", caixa: "898.5", patrimonio: "16898.5" },
      { data: "2026-10-29", investimentos: "16101.5", caixa: "898.5", patrimonio: "17000" },
    ],
    avisos: ["AAPL sem câmbio em 01/10/2026."],
  },
  "GET /api/portfolio/maiores": [
    {
      ativo_id: 10,
      nome: "Petrobras PN",
      simbolo: "PETR4",
      tipo: "acao_br",
      moeda: "BRL",
      instituicao_id: null,
      quantidade: "200",
      preco_medio: "38.12",
      preco_atual: "50",
      valor: "10000",
      valor_brl: "10000.00",
      origem: "automatico",
      data_preco: "2026-10-29",
      defasado: true,
      aviso: "Cotação de 4 dias atrás.",
      erro: null,
      participacao: "0.5882",
      metricas: null,
      metricas_brl: null,
      variacao_dia: null,
    },
  ],
};

function variacaoAtivo(ativo_id: number, nome: string, variacao: string, brl: string) {
  return {
    ativo_id,
    nome,
    variacao: {
      preco_atual: "10",
      data_atual: "2026-10-29",
      preco_anterior: "10",
      data_anterior: "2026-10-28",
      variacao,
      variacao_brl: brl,
    },
  };
}

const ATIVOS = [
  { id: 10, tipo: "acao_br", simbolo: "PETR4", nome: "Petrobras PN" },
  { id: 11, tipo: "acao_us", simbolo: "AAPL", nome: "Apple" },
  { id: 13, tipo: "acao_br", simbolo: "VALE3", nome: "Vale ON" },
  { id: 14, tipo: "cripto", simbolo: "BTC", nome: "Bitcoin" },
  { id: 15, tipo: "acao_br", simbolo: "ITSA4", nome: "Itaúsa PN" },
].map((a) => ativo(a));

Object.assign(ROTAS, {
  "GET /api/ativos": ATIVOS,
  "GET /api/portfolio/variacao-dia": {
    variacao_dia_brl: "-120.30",
    variacao_dia: "-0.0071",
    ativos: [
      variacaoAtivo(13, "Vale ON", "0.0148", "402.10"),
      variacaoAtivo(10, "Petrobras PN", "0.0312", "921.60"),
      variacaoAtivo(11, "Apple", "-0.0205", "-638.20"),
      variacaoAtivo(14, "Bitcoin", "-0.011", "-214.95"),
      variacaoAtivo(15, "Itaúsa PN", "0", "0"), // sem variação: fica de fora
    ],
  },
  "GET /api/portfolio/vencimentos": [
    {
      ativo_id: 20,
      nome: "CDB Banco X 110% CDI",
      simbolo: null,
      tipo: "renda_fixa",
      instituicao_id: null,
      vencimento: "2026-12-15",
      valor_brl: "25871.09",
      defasado: false,
      aviso: null,
    },
    {
      ativo_id: 21,
      nome: "Tesouro IPCA+ 2029",
      simbolo: null,
      tipo: "tesouro_direto",
      instituicao_id: null,
      vencimento: "2029-05-15",
      valor_brl: "18204.77",
      defasado: true,
      aviso: "Cotação de 5 dias atrás.",
    },
  ],
});

describe("Dashboard", () => {
  it("métricas: patrimônio com caixa, variação do dia, rentabilidade e saldo do mês", async () => {
    renderizar(<TelaDashboard agora={AGORA} />, { rotas: ROTAS });
    const patrimonio = await screen.findByRole("region", { name: "Patrimônio total" });
    await waitFor(() => {
      expect(limpo(patrimonio.textContent)).toContain("R$ 17.000,00");
    });
    expect(limpo(patrimonio.textContent)).toContain("Caixa R$ 898,50");
    const variacao = screen.getByRole("region", { name: "Variação do dia" });
    expect(limpo(variacao.textContent)).toContain("−R$ 120,30");
    expect(limpo(variacao.textContent)).toContain("−0,71%");
    expect(limpo(screen.getByRole("region", { name: "Rentabilidade" }).textContent)).toContain(
      "+7,34%",
    );
    expect(limpo(screen.getByRole("region", { name: "Saldo do mês" }).textContent)).toContain(
      "+R$ 2.500,00",
    );
  });

  it("gráficos de alocação (com a fatia caixa) e evolução, avisos e maiores ativos com selo defasado", async () => {
    renderizar(<TelaDashboard agora={AGORA} />, { rotas: ROTAS });
    const alocacao = await screen.findByRole("img", {
      name: "Alocação da carteira por tipo de ativo",
    });
    const opcoes = JSON.parse(alocacao.getAttribute("data-opcoes") ?? "{}") as {
      series: { data: { name: string; value: number }[] }[];
    };
    expect(opcoes.series[0]?.data.map((d) => d.name)).toEqual([
      "Ação (Brasil)",
      "Renda fixa",
      "Caixa",
    ]);
    expect(await screen.findByRole("img", { name: "Evolução do patrimônio" })).toBeInTheDocument();
    expect(screen.getByText("AAPL sem câmbio em 01/10/2026.")).toBeInTheDocument();
    const maiores = await screen.findByRole("table", { name: "Maiores ativos" });
    expect(within(maiores).getByText("PETR4")).toBeInTheDocument();
    expect(within(maiores).getByText("Defasado")).toHaveAttribute(
      "title",
      "Cotação de 4 dias atrás.",
    );
    expect(within(maiores).getByText("58,82%")).toBeInTheDocument();
  });

  it("seletor em segmentos: Por Instituição escolhe a primeira e refaz as consultas", async () => {
    useAnaliseStore.setState({ instituicaoId: null });
    const { usuario, chamadas } = renderizar(<TelaDashboard agora={AGORA} />, { rotas: ROTAS });
    expect(screen.getByRole("button", { name: "Análise Geral" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // Espera a lista de instituições para o segmento ter o que escolher.
    await waitFor(() => {
      expect(chamadas.some((c) => c.caminho === "/api/instituicoes")).toBe(true);
    });
    await usuario.click(screen.getByRole("button", { name: "Por Instituição" }));
    const combo = await screen.findByRole("combobox", { name: "Instituição" });
    expect(combo).toHaveValue("1");
    for (const caminho of [
      "/api/portfolio/alocacao",
      "/api/portfolio/evolucao",
      "/api/portfolio/variacao-dia",
      "/api/portfolio/vencimentos",
    ]) {
      await waitFor(() => {
        expect(
          chamadas.some((c) => c.caminho === caminho && c.query.get("instituicao_id") === "1"),
        ).toBe(true);
      });
    }
    await usuario.selectOptions(combo, "2");
    await waitFor(() => {
      expect(
        chamadas.some(
          (c) => c.caminho === "/api/portfolio/resumo" && c.query.get("instituicao_id") === "2",
        ),
      ).toBe(true);
    });
    // Teclado: seta para a esquerda volta para a Análise Geral.
    screen.getByRole("button", { name: "Por Instituição" }).focus();
    await usuario.keyboard("{ArrowLeft}");
    expect(screen.getByRole("button", { name: "Análise Geral" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByRole("combobox", { name: "Instituição" })).not.toBeInTheDocument();
    useAnaliseStore.setState({ instituicaoId: null });
  });

  it("sparkline do patrimônio com resumo textual; sem série, sem sparkline", async () => {
    renderizar(<TelaDashboard agora={AGORA} />, { rotas: ROTAS });
    const patrimonio = await screen.findByRole("region", { name: "Patrimônio total" });
    const sparkline = await within(patrimonio).findByRole("img");
    expect(limpo(sparkline.getAttribute("aria-label"))).toBe(
      "Evolução do patrimônio de 28/10/2026 (R$ 16.898,50) a 29/10/2026 (R$ 17.000,00)",
    );
    // Variação do dia não tem série: nenhum gráfico no cartão.
    expect(
      within(screen.getByRole("region", { name: "Variação do dia" })).queryByRole("img"),
    ).not.toBeInTheDocument();
  });

  it("altas e baixas do dia: maiores variações dos dois lados, em ordem", async () => {
    renderizar(<TelaDashboard agora={AGORA} />, { rotas: ROTAS });
    const altas = await screen.findByRole("region", { name: "Maiores altas" });
    const textos = (regiao: HTMLElement) =>
      within(regiao)
        .getAllByRole("listitem")
        .map((i) => limpo(i.textContent));
    await waitFor(() => {
      expect(textos(altas)[0]).toMatch(/^PETR4/);
    });
    expect(textos(altas)).toEqual([
      "PETR4ganho: +3,12%ganho: +R$ 921,60",
      "VALE3ganho: +1,48%ganho: +R$ 402,10",
    ]);
    const baixas = screen.getByRole("region", { name: "Maiores baixas" });
    expect(textos(baixas)).toEqual([
      "AAPLperda: −2,05%perda: −R$ 638,20",
      "BTCperda: −1,10%perda: −R$ 214,95",
    ]);
    expect(screen.queryByText("ITSA4")).not.toBeInTheDocument();
  });

  it("próximos vencimentos na ordem do backend, com valor e selo defasado", async () => {
    renderizar(<TelaDashboard agora={AGORA} />, { rotas: ROTAS });
    const tabela = await screen.findByRole("table", { name: "Próximos vencimentos" });
    const linhas = within(tabela).getAllByRole("row").slice(1);
    expect(limpo(linhas[0]?.textContent ?? "")).toBe("CDB Banco X 110% CDI 15/12/2026R$ 25.871,09");
    expect(linhas[1]).toHaveTextContent("Tesouro IPCA+ 2029");
    expect(within(linhas[1] as HTMLElement).getByText("Defasado")).toBeInTheDocument();
  });

  it("blocos novos vazios e com erro", async () => {
    const { usuario, chamadas } = renderizar(<TelaDashboard agora={AGORA} />, {
      rotas: {
        ...ROTAS,
        "GET /api/portfolio/vencimentos": [],
        "GET /api/portfolio/variacao-dia": {
          status: 500,
          corpo: { codigo: "erro_interno", mensagem: "Falha ao calcular a variação." },
        },
      },
    });
    expect(await screen.findByText("Nenhum título a vencer")).toBeInTheDocument();
    expect(await screen.findByText("Falha ao calcular a variação.")).toBeInTheDocument();
    const antes = chamadas.filter((c) => c.caminho === "/api/portfolio/variacao-dia").length;
    await usuario.click(screen.getByRole("button", { name: "Tentar novamente" }));
    await waitFor(() => {
      expect(chamadas.filter((c) => c.caminho === "/api/portfolio/variacao-dia").length).toBe(
        antes + 1,
      );
    });
  });

  it("altas e baixas sem variação mostra o estado vazio", async () => {
    renderizar(<TelaDashboard agora={AGORA} />, {
      rotas: {
        ...ROTAS,
        "GET /api/portfolio/variacao-dia": {
          variacao_dia_brl: "0",
          variacao_dia: null,
          ativos: [],
        },
      },
    });
    expect(await screen.findByText("Sem variação para mostrar")).toBeInTheDocument();
  });

  it("estados vazio e erro (com Tentar novamente)", async () => {
    const { usuario } = renderizar(<TelaDashboard agora={AGORA} />, {
      rotas: {
        ...ROTAS,
        "GET /api/portfolio/alocacao": [],
        "GET /api/portfolio/maiores": [],
        "GET /api/portfolio/resumo": {
          status: 500,
          corpo: { codigo: "erro_interno", mensagem: "Erro inesperado no serviço interno." },
        },
      },
    });
    expect(await screen.findByText("Nada investido ainda")).toBeInTheDocument();
    expect(await screen.findByText("Nenhuma posição aberta")).toBeInTheDocument();
    expect(await screen.findByText("Erro inesperado no serviço interno.")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Tentar novamente" }));
  });
});
