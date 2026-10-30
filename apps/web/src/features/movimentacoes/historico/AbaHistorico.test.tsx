import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { escolherOndeSalvar } from "@/lib/dialogos-nativos";
import { renderizar, type Chamada } from "@/test/api-falsa";
import { BotaoExportar } from "../TelaMovimentacoes";
import { AbaHistorico } from "./AbaHistorico";

vi.mock("@/lib/dialogos-nativos", () => ({
  escolherOndeSalvar: vi.fn(),
  escolherArquivo: vi.fn(),
}));

const AGORA = new Date(2026, 9, 29, 12);

function operacao(dados: Record<string, unknown>) {
  return {
    instituicao_id: 1,
    quantidade: null,
    preco_unitario: null,
    valor: null,
    taxas: "0",
    moeda: "BRL",
    cambio: "1",
    subtipo_provento: null,
    imposto_retido: "0",
    observacao: null,
    criado_em: "2026-10-01T00:00:00Z",
    movimentos: [],
    taxas_brl: "0.00",
    imposto_retido_brl: "0.00",
    resultado: null,
    resultado_brl: null,
    situacao: "aberta",
    ...dados,
  };
}

// Prévia aprovada: compra PETR4, provento PETR4 e venda WEGE3 com prejuízo em outubro.
const OPERACOES = [
  operacao({
    id: 1,
    ativo_id: 10,
    tipo: "compra",
    data: "2026-10-24",
    quantidade: "200",
    preco_unitario: "38.12",
    taxas: "2",
    taxas_brl: "2.00",
    valor_total: "7626.00",
    valor_total_brl: "7626.00",
    movimentos: [{ id: 5, tipo: "debito_compra", valor: "7626.00" }],
  }),
  operacao({
    id: 2,
    ativo_id: 10,
    tipo: "provento",
    data: "2026-10-15",
    valor: "412.30",
    subtipo_provento: "dividendo",
    imposto_retido: "15",
    imposto_retido_brl: "15.00",
    valor_total: "412.30",
    valor_total_brl: "412.30",
  }),
  operacao({
    id: 3,
    ativo_id: 10,
    tipo: "venda",
    data: "2026-07-22",
    quantidade: "150",
    preco_unitario: "52.4",
    taxas: "3.5",
    taxas_brl: "3.50",
    valor_total: "7856.50",
    valor_total_brl: "7856.50",
    resultado: "-612.40",
    resultado_brl: "-612.40",
    situacao: "encerrada",
  }),
];

const RESUMO = {
  totais: {
    operacoes: 3,
    total_comprado: "7626.00",
    total_vendido: "7856.50",
    lucro_realizado: "-612.40",
    proventos_liquidos: "412.30",
    impostos_retidos: "15.00",
    taxas: "5.50",
    operacoes_com_taxas: 2,
  },
  total_sem_filtros: 14,
  inicio: "2025-11-01",
  fim: "2026-10-29",
  serie: [{ mes: "2026-10-01", compras: "7626.00", vendas: "0.00", proventos: "412.30" }],
  por_ativo: [
    {
      ativo_id: 10,
      situacao: "aberta",
      totais: {
        operacoes: 3,
        total_comprado: "7626.00",
        total_vendido: "7856.50",
        lucro_realizado: "-612.40",
        proventos_liquidos: "412.30",
        impostos_retidos: "15.00",
        taxas: "5.50",
        operacoes_com_taxas: 2,
      },
      instituicoes: [
        {
          instituicao_id: 1,
          situacao: "aberta",
          totais: {
            operacoes: 2,
            total_comprado: "7626.00",
            total_vendido: "0.00",
            lucro_realizado: "0.00",
            proventos_liquidos: "412.30",
            impostos_retidos: "15.00",
            taxas: "2.00",
            operacoes_com_taxas: 1,
          },
        },
        {
          instituicao_id: 2,
          situacao: "encerrada",
          totais: {
            operacoes: 1,
            total_comprado: "0.00",
            total_vendido: "7856.50",
            lucro_realizado: "-612.40",
            proventos_liquidos: "0.00",
            impostos_retidos: "0.00",
            taxas: "3.50",
            operacoes_com_taxas: 1,
          },
        },
      ],
    },
  ],
};

function rotas(itens = OPERACOES, resumo: object = RESUMO) {
  return {
    "GET /api/transacoes": () => ({ itens, total: itens.length, limite: 50, deslocamento: 0 }),
    "GET /api/transacoes/resumo": resumo,
  };
}

const ultimaLista = (chamadas: Chamada[]) =>
  chamadas.filter((c) => c.metodo === "GET" && c.caminho === "/api/transacoes").at(-1);
const url = () => screen.getByTestId("url-atual").textContent;
const limpo = (t: string | null) => (t ?? "").replace(/\u00a0/g, " ");

describe("Histórico de operações", () => {
  it("resumo em cartões, contador N de M, tabela agrupada por mês e consulta padrão (12 meses)", async () => {
    const { chamadas } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotas() });
    expect(await screen.findByText("3 de 14 operações")).toBeInTheDocument();
    const lucro = screen.getByRole("region", { name: "Lucro realizado" });
    expect(limpo(lucro.textContent)).toContain("−R$ 612,40");
    expect(within(lucro).getByText(/perda/)).toBeInTheDocument(); // não só pela cor
    expect(
      limpo(screen.getByRole("region", { name: "Proventos recebidos" }).textContent),
    ).toContain("R$ 15,00 de IR retido");
    expect(limpo(screen.getByRole("region", { name: "Taxas pagas" }).textContent)).toContain(
      "2 operações",
    );
    expect(
      screen.getByRole("img", { name: "Compras, vendas e proventos por mês" }),
    ).toBeInTheDocument();

    const tabela = await screen.findByRole("table", { name: "Histórico de operações" });
    expect(within(tabela).getByText("outubro de 2026")).toBeInTheDocument();
    expect(within(tabela).getByText("julho de 2026")).toBeInTheDocument();
    expect(limpo(tabela.textContent)).toContain("R$ 7.626,00");

    const consulta = ultimaLista(chamadas)?.query;
    expect(consulta?.get("inicio")).toBe("2025-11-01");
    expect(consulta?.get("fim")).toBe("2026-10-29");
    expect(consulta?.get("ordem")).toBe("data");
    expect(consulta?.has("tipos")).toBe(false);
  });

  it("selos de operação ligam/desligam e vão para a URL e para a API; etiqueta remove o filtro", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotas() });
    await screen.findByText("3 de 14 operações");
    await usuario.click(screen.getByRole("button", { name: "Provento", pressed: true }));
    await waitFor(() => {
      expect(url()).toContain("ops=compra%2Caporte%2Cvenda%2Cresgate");
    });
    await waitFor(() => {
      expect(ultimaLista(chamadas)?.query.getAll("tipos")).toEqual([
        "compra",
        "aporte",
        "venda",
        "resgate",
      ]);
    });
    const etiquetas = screen.getByRole("list", { name: "Filtros ativos" });
    expect(
      within(etiquetas).getByText("Operações: Compra, Aporte, Venda, Resgate"),
    ).toBeInTheDocument();
    await usuario.click(
      within(etiquetas).getByRole("button", { name: /Remover filtro Operações/ }),
    );
    await waitFor(() => {
      expect(url()).not.toContain("ops=");
    });
  });

  it("filtros de selects e caixas também ficam na URL e na API (instituição → situação por posição)", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotas() });
    await screen.findByText("3 de 14 operações");
    await usuario.selectOptions(screen.getByLabelText("Instituição"), "2");
    await usuario.selectOptions(screen.getByLabelText("Situação do ativo"), "encerrada");
    await usuario.click(screen.getByLabelText("Só vendas com prejuízo"));
    await waitFor(() => {
      const q = ultimaLista(chamadas)?.query;
      expect(q?.get("instituicao_id")).toBe("2");
      expect(q?.get("situacao")).toBe("encerrada");
      expect(q?.get("apenas_prejuizo")).toBe("true");
    });
    expect(url()).toContain("instituicao=2");
    expect(url()).toContain("prejuizo=1");
    expect(screen.getByText("Instituição: RICO")).toBeInTheDocument();
  });

  it("filtros lidos da URL ao voltar para a tela", async () => {
    const { chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotas(),
      url: "/movimentacoes?tipo_ativo=acao_br&periodo=tudo&custos=1",
    });
    await screen.findByText("3 de 14 operações");
    const q = ultimaLista(chamadas)?.query;
    expect(q?.get("tipo_ativo")).toBe("acao_br");
    expect(q?.get("apenas_com_custos")).toBe("true");
    expect(q?.has("inicio")).toBe(false);
    expect(screen.getByText("Período: Todo o histórico")).toBeInTheDocument();
  });

  it("busca espera a digitação parar antes de consultar", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotas() });
    await screen.findByText("3 de 14 operações");
    await usuario.type(screen.getByLabelText("Ativo"), "petr");
    await waitFor(() => {
      expect(ultimaLista(chamadas)?.query.get("busca")).toBe("petr");
    });
    expect(chamadas.filter((c) => c.query.get("busca") === "pe")).toHaveLength(0);
  });

  it("estado vazio com Limpar filtros", async () => {
    const vazio = {
      ...RESUMO,
      totais: { ...RESUMO.totais, operacoes: 0 },
      serie: [],
      por_ativo: [],
    };
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotas([], vazio),
      url: "/?moeda=USD",
    });
    expect(await screen.findByText("Nenhuma operação com esses filtros")).toBeInTheDocument();
    const botoes = screen.getAllByRole("button", { name: "Limpar filtros" });
    await usuario.click(botoes.at(-1) as HTMLElement);
    await waitFor(() => {
      expect(url()).toBe("/");
    });
  });

  it("nenhuma operação marcada: não consulta a lista e mostra vazio", async () => {
    const { chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotas(),
      url: "/?ops=",
    });
    expect(await screen.findByText("Nenhuma operação com esses filtros")).toBeInTheDocument();
    expect(chamadas.filter((c) => c.caminho === "/api/transacoes")).toHaveLength(0);
  });

  it("ordenar por coluna vai para a API e desliga o agrupamento por mês", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotas() });
    const tabela = await screen.findByRole("table", { name: "Histórico de operações" });
    await usuario.click(within(tabela).getByRole("button", { name: /Resultado/ }));
    await waitFor(() => {
      expect(ultimaLista(chamadas)?.query.get("ordem")).toBe("resultado");
    });
    expect(ultimaLista(chamadas)?.query.get("direcao")).toBe("desc");
    await waitFor(() => {
      expect(within(tabela).queryByText("outubro de 2026")).not.toBeInTheDocument();
    });
    await usuario.click(within(tabela).getByRole("button", { name: /Resultado/ }));
    await waitFor(() => {
      expect(ultimaLista(chamadas)?.query.get("direcao")).toBe("asc");
    });
  });

  it("clicar na linha abre o detalhe com os movimentos de caixa e as ações", async () => {
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotas() });
    const tabela = await screen.findByRole("table", { name: "Histórico de operações" });
    await usuario.click(within(tabela).getAllByRole("row")[2] as HTMLElement); // 1ª operação
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("Movimentos de caixa gerados")).toBeInTheDocument();
    expect(within(dialogo).getByText("Débito da compra/aporte")).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: "Editar" })).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: "Excluir" })).toBeInTheDocument();
  });

  it("visão Por ativo: linha agregada que se abre por instituição", async () => {
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotas() });
    await screen.findByText("3 de 14 operações");
    await usuario.click(screen.getByRole("button", { name: "Por ativo" }));
    const tabela = await screen.findByRole("table", { name: "Histórico por ativo" });
    expect(url()).toContain("visao=ativos");
    expect(within(tabela).queryByText("RICO")).not.toBeInTheDocument();
    const abrir = within(tabela).getByRole("button", { name: /Ver por instituição: PETR4/ });
    expect(abrir).toHaveAttribute("aria-expanded", "false");
    await usuario.click(abrir);
    expect(within(tabela).getByText("RICO")).toBeInTheDocument();
    expect(within(tabela).getByText("XP")).toBeInTheDocument();
    expect(within(tabela).getAllByText("Encerrada")).toHaveLength(1);
    await usuario.click(within(tabela).getByRole("button", { name: /Recolher: PETR4/ }));
    expect(within(tabela).queryByText("RICO")).not.toBeInTheDocument();
  });
});

describe("Exportar Excel", () => {
  beforeEach(() => {
    vi.mocked(escolherOndeSalvar).mockReset();
  });

  it("usa o caminho do diálogo nativo e envia todos os filtros da URL", async () => {
    vi.mocked(escolherOndeSalvar).mockResolvedValue("C:\\Users\\eu\\historico.xlsx");
    const { usuario, chamadas } = renderizar(<BotaoExportar agora={AGORA} />, {
      url: "/?tipo_ativo=acao_br&ops=venda&ordem=resultado",
      rotas: {
        "POST /api/transacoes/exportar": (c: Chamada) => ({
          caminho: (c.corpo as { caminho: string }).caminho,
          linhas: 4,
        }),
      },
    });
    await usuario.click(screen.getByRole("button", { name: "Exportar Excel" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Planilha salva em C:\\Users\\eu\\historico.xlsx (4 operações).",
    );
    expect(escolherOndeSalvar).toHaveBeenCalledWith("historico-operacoes-2026-10-29.xlsx", {
      nome: "Planilha do Excel",
      extensoes: ["xlsx"],
    });
    const post = chamadas.find((c) => c.caminho === "/api/transacoes/exportar");
    expect(post?.corpo).toEqual({ caminho: "C:\\Users\\eu\\historico.xlsx" });
    expect(post?.query.get("tipo_ativo")).toBe("acao_br");
    expect(post?.query.getAll("tipos")).toEqual(["venda"]);
    expect(post?.query.get("ordem")).toBe("resultado");
    expect(post?.query.has("limite")).toBe(false); // todas as páginas
  });

  it("cancelar o diálogo não chama a API; erro da API aparece em pt-BR", async () => {
    vi.mocked(escolherOndeSalvar).mockResolvedValueOnce(null);
    const { usuario, chamadas } = renderizar(<BotaoExportar agora={AGORA} />, {
      rotas: {
        "POST /api/transacoes/exportar": {
          status: 422,
          corpo: {
            codigo: "operacao_nao_permitida",
            mensagem:
              "Não foi possível salvar a planilha. Se ela estiver aberta no Excel, feche-a e tente de novo.",
          },
        },
      },
    });
    await usuario.click(screen.getByRole("button", { name: "Exportar Excel" }));
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(0);

    vi.mocked(escolherOndeSalvar).mockResolvedValueOnce("C:\\x.xlsx");
    await usuario.click(screen.getByRole("button", { name: "Exportar Excel" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("feche-a e tente de novo");
  });
});
