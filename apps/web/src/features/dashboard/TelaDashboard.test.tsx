import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAnaliseStore } from "@/lib/consultas-comuns";
import { renderizar, type Chamada } from "@/test/api-falsa";
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
    const maiores = await screen.findByRole("table");
    expect(within(maiores).getByText("PETR4")).toBeInTheDocument();
    expect(within(maiores).getByText("Defasado")).toHaveAttribute(
      "title",
      "Cotação de 4 dias atrás.",
    );
    expect(within(maiores).getByText("58,82%")).toBeInTheDocument();
  });

  it("seletor de análise por instituição refaz as consultas com instituicao_id", async () => {
    useAnaliseStore.setState({ instituicaoId: null });
    const { usuario, chamadas } = renderizar(<TelaDashboard agora={AGORA} />, { rotas: ROTAS });
    await screen.findByRole("option", { name: "XP" });
    await usuario.selectOptions(screen.getByRole("combobox", { name: /Análise/ }), "1");
    await waitFor(() => {
      expect(
        chamadas.some(
          (c) => c.caminho === "/api/portfolio/alocacao" && c.query.get("instituicao_id") === "1",
        ),
      ).toBe(true);
    });
    expect(
      chamadas.some(
        (c) => c.caminho === "/api/portfolio/evolucao" && c.query.get("instituicao_id") === "1",
      ),
    ).toBe(true);
    useAnaliseStore.setState({ instituicaoId: null });
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
