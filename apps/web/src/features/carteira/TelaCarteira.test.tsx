import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderizar, type Chamada } from "@/test/api-falsa";
import { TelaCarteira } from "./TelaCarteira";

const limpo = (t: string | null) => (t ?? "").replace(/\u00a0/g, " ");

function posicao(dados: Record<string, unknown>) {
  return {
    instituicao_id: null,
    quantidade: null,
    preco_medio: null,
    preco_atual: null,
    valor: null,
    origem: "automatico",
    data_preco: "2026-10-29",
    defasado: false,
    aviso: null,
    erro: null,
    participacao: "0.5",
    metricas: null,
    metricas_brl: null,
    variacao_dia: null,
    moeda: "BRL",
    ...dados,
  };
}

const ROTAS = {
  "GET /api/portfolio/posicoes": [
    posicao({
      ativo_id: 10,
      nome: "Petrobras PN",
      simbolo: "PETR4",
      tipo: "acao_br",
      quantidade: "200",
      preco_medio: "38.12",
      preco_atual: "50",
      valor_brl: "10000.00",
      variacao_dia: {
        preco_atual: "50",
        data_atual: "2026-10-29",
        preco_anterior: "49",
        data_anterior: "2026-10-28",
        variacao: "0.0204",
        variacao_brl: "200",
      },
    }),
    posicao({
      ativo_id: 11,
      nome: "Apple",
      simbolo: "AAPL",
      tipo: "acao_us",
      moeda: "USD",
      quantidade: "5",
      preco_atual: "229.1",
      valor_brl: "6342.80",
      defasado: true,
      aviso: "Câmbio de 6 dias atrás.",
      origem: "manual",
    }),
    posicao({
      ativo_id: 12,
      nome: "CDB Banco X",
      simbolo: null,
      tipo: "renda_fixa",
      valor_brl: "1000.00",
      origem: "calculado",
    }),
  ],
  "GET /api/portfolio/alocacao": [{ grupo: "acao_br", valor: "10000", percentual: "1" }],
  "GET /api/cotacoes/status": [
    {
      ativo_id: 10,
      nome: "PETR4",
      tipo: "acao_br",
      valor: "50",
      data: "2026-10-29",
      data_hora: "2026-10-29T17:00:00Z",
      origem: "automatico",
      provider_preco: "yfinance",
      provider: "yfinance",
      ultima_tentativa: "2026-10-29T17:00:00Z",
      ultimo_sucesso: "2026-10-29T17:00:00Z",
      ultimo_erro: null,
      defasado: false,
      aviso: null,
    },
    {
      ativo_id: 11,
      nome: "AAPL",
      tipo: "acao_us",
      valor: "229.1",
      data: "2026-10-27",
      data_hora: null,
      origem: "manual",
      provider_preco: null,
      provider: "yfinance",
      ultima_tentativa: "2026-10-29T17:00:00Z",
      ultimo_sucesso: null,
      ultimo_erro: "Yahoo indisponível (HTTP 503).",
      defasado: true,
      aviso: "Cotação de 2 dias.",
    },
  ],
  "GET /api/cotacoes/atualizacao": {
    em_andamento: false,
    ultimo_ciclo_inicio: null,
    ultimo_ciclo_fim: null,
    precos_atualizados: null,
    erros: null,
  },
  "GET /api/ativos/{id}/precos": {
    itens: [
      {
        id: 1,
        ativo_id: 10,
        data: "2026-10-28",
        data_hora: "2026-10-28T21:00:00Z",
        valor: "49",
        moeda: "BRL",
        origem: "automatico",
        provider: "yfinance",
      },
    ],
    total: 1,
    limite: 500,
    deslocamento: 0,
  },
};

describe("Carteira", () => {
  it("lista posições com valores, variação, selo defasado e status da última atualização", async () => {
    renderizar(<TelaCarteira />, { rotas: ROTAS });
    const tabela = await screen.findByRole("table", { name: "Posições" });
    const linhas = within(tabela).getAllByRole("row");
    // Ordenada por valor (BRL) decrescente: PETR4, AAPL, CDB.
    expect(linhas[1]).toHaveTextContent("PETR4");
    expect(linhas[2]).toHaveTextContent("AAPL");
    expect(limpo(linhas[1]?.textContent ?? "")).toContain("R$ 10.000,00");
    expect(limpo(linhas[1]?.textContent ?? "")).toContain("+2,04%");
    expect(limpo(linhas[2]?.textContent ?? "")).toContain("US$ 229,10");
    expect(within(linhas[2] as HTMLElement).getByText("Defasado")).toBeInTheDocument();
    expect(
      within(linhas[2] as HTMLElement).getByText(/Erro: Yahoo indisponível/),
    ).toBeInTheDocument();
    expect(within(linhas[1] as HTMLElement).getByText(/Automático · yfinance/)).toBeInTheDocument();
  });

  it("busca, filtro por tipo e ordenação por coluna", async () => {
    const { usuario } = renderizar(<TelaCarteira />, { rotas: ROTAS });
    const tabela = await screen.findByRole("table", { name: "Posições" });
    await usuario.type(screen.getByRole("searchbox", { name: "Buscar ativo" }), "apple");
    expect(within(tabela).getAllByRole("row")).toHaveLength(2);
    await usuario.clear(screen.getByRole("searchbox", { name: "Buscar ativo" }));
    await usuario.selectOptions(
      screen.getByRole("combobox", { name: "Filtrar por tipo" }),
      "renda_fixa",
    );
    expect(within(tabela).getAllByRole("row")).toHaveLength(2);
    expect(tabela).toHaveTextContent("CDB Banco X");
    await usuario.selectOptions(screen.getByRole("combobox", { name: "Filtrar por tipo" }), "");
    await usuario.click(within(tabela).getByRole("button", { name: /Valor \(BRL\)/ }));
    const cabecalho = within(tabela).getByRole("columnheader", { name: /Valor \(BRL\)/ });
    expect(cabecalho).toHaveAttribute("aria-sort", "ascending");
    expect(within(tabela).getAllByRole("row")[1]).toHaveTextContent("CDB Banco X");
  });

  it("detalhe do ativo cotado: gráfico de preço e valor manual; renda fixa sem valor manual", async () => {
    const { usuario, chamadas } = renderizar(<TelaCarteira />, {
      rotas: {
        ...ROTAS,
        "POST /api/ativos/{id}/precos": (c: Chamada) => ({
          id: 2,
          ativo_id: 10,
          moeda: "BRL",
          origem: "manual",
          provider: null,
          data_hora: "",
          ...(c.corpo as object),
        }),
      },
    });
    const tabela = await screen.findByRole("table", { name: "Posições" });
    await usuario.click(within(tabela).getAllByRole("row")[1] as HTMLElement);
    const dialogo = await screen.findByRole("dialog");
    expect(
      await within(dialogo).findByRole("img", { name: /Preço de PETR4 em 1 ano/ }),
    ).toHaveAttribute("data-pontos", "1");
    const valor = within(dialogo).getByLabelText(/^Preço \(BRL\)/);
    await usuario.type(valor, "51,2345");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar valor" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
        data: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) as string,
        valor: "51.2345",
      });
    });
    await usuario.keyboard("{Escape}");

    await usuario.click(within(tabela).getAllByRole("row")[3] as HTMLElement); // CDB
    const cdb = await screen.findByRole("dialog");
    expect(within(cdb).getByText(/não aceita valor manual/)).toBeInTheDocument();
    expect(within(cdb).queryByRole("button", { name: "Salvar valor" })).not.toBeInTheDocument();
  });

  it("excluir ativo com transações mostra a mensagem da API", async () => {
    const { usuario } = renderizar(<TelaCarteira />, {
      rotas: {
        ...ROTAS,
        "DELETE /api/ativos/{id}": {
          status: 409,
          corpo: {
            codigo: "conflito",
            mensagem: "Não é possível excluir PETR4: há transações registradas.",
          },
        },
      },
    });
    const tabela = await screen.findByRole("table", { name: "Posições" });
    await usuario.click(within(tabela).getAllByRole("row")[1] as HTMLElement);
    await usuario.click(await screen.findByRole("button", { name: "Excluir" }));
    const confirmacao = await screen.findByRole("alertdialog");
    await usuario.click(within(confirmacao).getByRole("button", { name: "Excluir" }));
    expect(await within(confirmacao).findByText(/há transações registradas/)).toBeInTheDocument();
  });

  it("estado vazio", async () => {
    renderizar(<TelaCarteira />, { rotas: { ...ROTAS, "GET /api/portfolio/posicoes": [] } });
    expect(await screen.findByText("Nenhuma posição aberta")).toBeInTheDocument();
  });

  it("por instituição: subtotal da API, resultado somado exato, caixa e posição sem resultado", async () => {
    const metricas = (resultado: string, rentabilidade: string) => ({
      resultado_total: resultado,
      rentabilidade_total: rentabilidade,
    });
    const porInstituicao: Record<string, unknown[]> = {
      "2": [
        posicao({
          ativo_id: 10,
          nome: "Petrobras PN",
          simbolo: "PETR4",
          tipo: "acao_br",
          instituicao_id: 2,
          valor_brl: "30496.00",
          metricas_brl: metricas("4210.40", "0.16"),
        }),
        posicao({
          ativo_id: 13,
          nome: "Vale ON",
          simbolo: "VALE3",
          tipo: "acao_br",
          instituicao_id: 2,
          valor_brl: "27170.00",
          metricas_brl: metricas("3012.50", "0.125"),
        }),
      ],
      "3": [
        posicao({
          ativo_id: 11,
          nome: "Apple",
          simbolo: "AAPL",
          tipo: "acao_us",
          moeda: "USD",
          instituicao_id: 3,
          valor_brl: "31120.55",
          metricas_brl: metricas("-1083.20", "-0.034"),
        }),
      ],
      "4": [
        posicao({
          ativo_id: 12,
          nome: "CDB Banco X",
          simbolo: null,
          tipo: "renda_fixa",
          instituicao_id: 4,
          valor_brl: null,
          erro: "Não há CDI registrado.",
        }),
      ],
    };
    const resumo = (id: number, nome: string, patrimonio: string, caixa: string) => ({
      instituicao_id: id,
      nome,
      investimentos_brl: patrimonio,
      caixa_brl: caixa,
      patrimonio_brl: patrimonio,
      completo: id !== 4,
    });
    const { usuario } = renderizar(<TelaCarteira />, {
      rotas: {
        ...ROTAS,
        "GET /api/portfolio/posicoes": (c: Chamada) =>
          porInstituicao[c.query.get("instituicao_id") ?? ""] ?? [],
        "GET /api/portfolio/instituicoes": [
          resumo(2, "RICO", "60880.20", "3214.20"),
          resumo(3, "Avenue", "31120.55", "0.00"),
          resumo(4, "Banco X", "1000.00", "0.00"),
          resumo(5, "Nubank", "500.00", "500.00"),
        ],
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Por instituição" }));
    expect(screen.queryByRole("searchbox", { name: "Buscar ativo" })).not.toBeInTheDocument();
    const tabela = await screen.findByRole("table", { name: "Carteira por instituição" });
    const linhas = within(tabela)
      .getAllByRole("row")
      .slice(1)
      .map((l) => limpo(l.textContent));
    expect(linhas).toEqual([
      // RICO: valor da API (com o caixa); resultado 4.210,40 + 3.012,50 = 7.222,90.
      "RICO2 posiçõesR$ 60.880,20ganho: +R$ 7.222,90",
      "PETR4Ação (Brasil)R$ 30.496,00ganho: +R$ 4.210,40ganho: +16,00%",
      "VALE3Ação (Brasil)R$ 27.170,00ganho: +R$ 3.012,50ganho: +12,50%",
      "CaixaSaldo em contaR$ 3.214,20——",
      // Posição em USD entra pelo valor e resultado em BRL.
      "Avenue1 posiçãoR$ 31.120,55perda: −R$ 1.083,20",
      "AAPLAção (EUA)R$ 31.120,55perda: −R$ 1.083,20perda: −3,40%",
      // Posição sem resultado: subtotal indisponível, nunca um total parcial.
      "Banco X1 posiçãototal incompletoR$ 1.000,00—",
      "CDB Banco XErro: Não há CDI registrado.Renda fixa———",
      // Instituição só com caixa continua aparecendo.
      "Nubanksó caixaR$ 500,00R$ 0,00",
      "CaixaSaldo em contaR$ 500,00——",
    ]);
  });
});
