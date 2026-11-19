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
    // Cabeçalho da seção: título à esquerda e a troca de visão à direita.
    expect(screen.getByRole("heading", { name: "Histórico de operações" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Visão da tabela" })).toBeInTheDocument();

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

// ---------------------------------------------------------------------------------------
// Parte 9: operações dentro da instituição (visão Por ativo) e quantidade por página.
// ---------------------------------------------------------------------------------------

/** Posição aberta de hoje (só os campos que o painel usa). */
function posicao(dados: Record<string, unknown>) {
  return {
    nome: "Petrobras PN",
    simbolo: "PETR4",
    tipo: "acao_br",
    moeda: "BRL",
    instituicao_id: 1,
    quantidade: "200",
    preco_medio: "38.13",
    metricas: { custo: "7626.00" },
    ...dados,
  };
}

/** Consultas do painel: ativo e instituição exatos com 100 por vez (ou 1, a última). */
const ehPainel = (c: Chamada) =>
  c.caminho === "/api/transacoes" &&
  c.query.has("ativo_id") &&
  ["100", "1"].includes(c.query.get("limite") ?? "");
const chamadasPainel = (chamadas: Chamada[]) => chamadas.filter(ehPainel);
const ultimaListaPrincipal = (chamadas: Chamada[]) =>
  ultimaLista(chamadas.filter((c) => !ehPainel(c)));

/**
 * Rotas com o painel: na XP (1) PETR4 tem o provento de 15/10 e a compra de 24/10 (a API
 * devolve em ordem crescente, como pedido); na RICO (2) a posição está encerrada e não há
 * operação no filtro.
 */
function rotasComPainel(extra: Record<string, unknown> = {}) {
  return {
    ...rotas(),
    "GET /api/transacoes": (c: Chamada) => {
      if (!ehPainel(c)) return { itens: OPERACOES, total: 3, limite: 10, deslocamento: 0 };
      const doPainel = c.query.get("instituicao_id") === "1" ? [OPERACOES[1], OPERACOES[0]] : [];
      return { itens: doPainel, total: doPainel.length, limite: 100, deslocamento: 0 };
    },
    "GET /api/portfolio/posicoes": (c: Chamada) =>
      c.query.get("instituicao_id") === "1" ? [posicao({ ativo_id: 10 })] : [],
    ...extra,
  };
}

async function abrirPainel(
  usuario: ReturnType<typeof renderizar>["usuario"],
  instituicao: "XP" | "RICO" = "XP",
) {
  await screen.findByText("3 de 14 operações");
  await usuario.click(screen.getByRole("button", { name: "Por ativo" }));
  const tabela = await screen.findByRole("table", { name: "Histórico por ativo" });
  await usuario.click(within(tabela).getByRole("button", { name: /Ver por instituição: PETR4/ }));
  await usuario.click(
    within(tabela).getByRole("button", { name: `Ver operações: PETR4 em ${instituicao}` }),
  );
  return screen.findByRole("region", { name: `Operações de PETR4 em ${instituicao}` });
}

describe("Por ativo: operações dentro da instituição", () => {
  it("só consulta ao abrir; usa ativo, instituição, ordem crescente e os filtros do topo", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasComPainel(),
    });
    await screen.findByText("3 de 14 operações");
    await usuario.click(screen.getByRole("button", { name: "Por ativo" }));
    const tabela = await screen.findByRole("table", { name: "Histórico por ativo" });
    await usuario.click(within(tabela).getByRole("button", { name: /Ver por instituição: PETR4/ }));
    // Instituição listada, mas fechada: nenhuma consulta do painel.
    const botao = within(tabela).getByRole("button", { name: "Ver operações: PETR4 em XP" });
    expect(botao).toHaveAttribute("aria-expanded", "false");
    expect(chamadasPainel(chamadas)).toHaveLength(0);

    await usuario.click(botao);
    await screen.findByRole("region", { name: "Operações de PETR4 em XP" });
    const q = chamadasPainel(chamadas).at(-1)?.query;
    expect(q?.get("ativo_id")).toBe("10");
    expect(q?.get("instituicao_id")).toBe("1");
    expect(q?.get("ordem")).toBe("data");
    expect(q?.get("direcao")).toBe("asc");
    expect(q?.get("limite")).toBe("100");
    expect(q?.get("inicio")).toBe("2025-11-01"); // período do topo (12 meses)
    expect(q?.get("fim")).toBe("2026-10-29");
    expect(within(tabela).getByRole("button", { name: "Recolher: PETR4 em XP" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("mostra a posição de hoje, a primeira e a última operação e a lista; a linha abre o detalhe", async () => {
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotasComPainel() });
    const painel = await abrirPainel(usuario);
    // Posição: 200 ações, preço médio R$ 38,13 e custo R$ 7.626,00 (dados da posição).
    expect(await within(painel).findByText("200", { selector: "dd" })).toBeInTheDocument();
    expect(limpo(painel.textContent)).toContain("R$ 38,13");
    expect(limpo(painel.textContent)).toContain("R$ 7.626,00");
    const termos = within(painel)
      .getAllByRole("term")
      .map((t) => t.textContent);
    expect(termos).toEqual([
      "Quantidade atual",
      "Preço médio",
      "Custo da posição",
      "Primeira operação",
      "Última operação",
    ]);
    // Primeira = provento de 15/10; última = compra de 24/10 (lista em ordem crescente).
    expect(within(painel).getByText("15/10/2026", { selector: "dd" })).toBeInTheDocument();
    expect(within(painel).getByText("24/10/2026", { selector: "dd" })).toBeInTheDocument();

    const lista = within(painel).getByRole("table", { name: "Operações de PETR4 em XP" });
    const linhas = within(lista).getAllByRole("row").slice(1);
    expect(linhas).toHaveLength(2);
    expect(within(linhas[0] as HTMLElement).getByText("Provento")).toBeInTheDocument();
    expect(within(linhas[1] as HTMLElement).getByText("Compra")).toBeInTheDocument();

    await usuario.click(linhas[1] as HTMLElement);
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText("Movimentos de caixa gerados")).toBeInTheDocument();
  });

  it("posição fora da lista de abertas aparece como encerrada; sem operações, estado vazio", async () => {
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotasComPainel() });
    const painel = await abrirPainel(usuario, "RICO");
    expect(await within(painel).findByText("Posição encerrada")).toBeInTheDocument();
    expect(within(painel).queryByText("Preço médio")).not.toBeInTheDocument();
    expect(
      await within(painel).findByText("Nenhuma operação com esses filtros"),
    ).toBeInTheDocument();
  });

  it("ativo sem quantidade (renda fixa por aporte) mostra só o custo", async () => {
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasComPainel({
        "GET /api/portfolio/posicoes": [
          posicao({
            ativo_id: 10,
            quantidade: null,
            preco_medio: null,
            metricas: { custo: "5000" },
          }),
        ],
      }),
    });
    const painel = await abrirPainel(usuario);
    expect(await within(painel).findByText("Custo da posição")).toBeInTheDocument();
    expect(limpo(painel.textContent)).toContain("R$ 5.000,00");
    expect(within(painel).queryByText("Quantidade atual")).not.toBeInTheDocument();
    expect(within(painel).queryByText("Preço médio")).not.toBeInTheDocument();
  });

  it("erro na lista do painel: mensagem e Tentar novamente, sem derrubar a tabela", async () => {
    let falhar = true;
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasComPainel({
        "GET /api/transacoes": (c: Chamada) => {
          if (!ehPainel(c)) return { itens: OPERACOES, total: 3, limite: 10, deslocamento: 0 };
          if (falhar) {
            return {
              status: 500,
              corpo: { codigo: "erro_interno", mensagem: "Falha ao ler o banco." },
            };
          }
          return { itens: [OPERACOES[0]], total: 1, limite: 100, deslocamento: 0 };
        },
      }),
    });
    const painel = await abrirPainel(usuario);
    expect(await within(painel).findByText(/Falha ao ler o banco/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Histórico por ativo" })).toBeInTheDocument();
    falhar = false;
    await usuario.click(within(painel).getByRole("button", { name: /Tentar novamente/ }));
    expect(
      await within(painel).findByRole("table", { name: "Operações de PETR4 em XP" }),
    ).toBeInTheDocument();
  });

  it("mais de 100 operações: paginação própria e a última data vem de uma consulta decrescente", async () => {
    // 150 operações na XP: a página 1 traz 100 e a "última" vem de direcao=desc&limite=1.
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasComPainel({
        "GET /api/transacoes": (c: Chamada) => {
          if (!ehPainel(c)) return { itens: OPERACOES, total: 3, limite: 10, deslocamento: 0 };
          if (c.query.get("direcao") === "desc") {
            const ultima = { ...OPERACOES[0], data: "2026-10-28" };
            return { itens: [ultima], total: 150, limite: 1, deslocamento: 0 };
          }
          const deslocamento = Number(c.query.get("deslocamento"));
          const item = deslocamento === 0 ? OPERACOES[1] : OPERACOES[0];
          return { itens: [item], total: 150, limite: 100, deslocamento };
        },
      }),
    });
    const painel = await abrirPainel(usuario);
    expect(await within(painel).findByText("28/10/2026", { selector: "dd" })).toBeInTheDocument();
    const desc = chamadasPainel(chamadas).find((c) => c.query.get("direcao") === "desc");
    expect(desc?.query.get("limite")).toBe("1");
    const nav = within(painel).getByRole("navigation", { name: /Páginas das operações/ });
    expect(within(nav).getByText("Página 1 de 2")).toBeInTheDocument();
    await usuario.click(within(nav).getByRole("button", { name: /Próxima/ }));
    await waitFor(() => {
      expect(
        chamadasPainel(chamadas).some(
          (c) => c.query.get("deslocamento") === "100" && c.query.get("direcao") === "asc",
        ),
      ).toBe(true);
    });
    expect(await within(nav).findByText("Página 2 de 2")).toBeInTheDocument();
    // A primeira operação continua sendo a da 1ª página.
    expect(within(painel).getByText("15/10/2026", { selector: "dd" })).toBeInTheDocument();
  });

  it("Ver em Operações com este filtro: troca de visão e filtra por ativo e instituição exatos", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasComPainel(),
      url: "/?visao=ativos&moeda=BRL",
    });
    await screen.findByText("3 de 14 operações");
    const tabela = await screen.findByRole("table", { name: "Histórico por ativo" });
    await usuario.click(within(tabela).getByRole("button", { name: /Ver por instituição: PETR4/ }));
    await usuario.click(within(tabela).getByRole("button", { name: "Ver operações: PETR4 em XP" }));
    const painel = await screen.findByRole("region", { name: "Operações de PETR4 em XP" });
    await usuario.click(
      within(painel).getByRole("button", { name: /Ver em Operações com este filtro/ }),
    );
    await screen.findByRole("table", { name: "Histórico de operações" });
    expect(url()).toContain("ativo=10");
    expect(url()).toContain("instituicao=1");
    expect(url()).toContain("moeda=BRL"); // os outros filtros do topo continuam
    expect(url()).not.toContain("visao=");
    const etiquetas = screen.getByRole("list", { name: "Filtros ativos" });
    expect(within(etiquetas).getByText("Ativo: PETR4")).toBeInTheDocument();
    expect(within(etiquetas).getByText("Instituição: XP")).toBeInTheDocument();
    await waitFor(() => {
      const q = ultimaListaPrincipal(chamadas);
      expect(q?.query.get("ativo_id")).toBe("10");
    });
    // Remover a etiqueta tira o ativo exato da URL.
    await usuario.click(
      within(etiquetas).getByRole("button", { name: "Remover filtro Ativo: PETR4" }),
    );
    await waitFor(() => {
      expect(url()).not.toContain("ativo=");
    });
  });
});

/** Página de operações conforme `limite`/`deslocamento` pedidos (31 operações no total). */
function rotasPaginadas(total = 31) {
  return {
    ...rotas(),
    "GET /api/transacoes": (c: Chamada) => {
      const limite = Number(c.query.get("limite"));
      const deslocamento = Number(c.query.get("deslocamento"));
      const quantos = Math.max(0, Math.min(limite, total - deslocamento));
      const itens = Array.from({ length: quantos }, (_, i) =>
        operacao({
          id: 100 + deslocamento + i,
          ativo_id: 10,
          tipo: "compra",
          data: "2026-10-24",
          quantidade: "1",
          preco_unitario: "10",
          valor_total: "10.00",
          valor_total_brl: "10.00",
        }),
      );
      return { itens, total, limite, deslocamento };
    },
  };
}

/** Resumo com `n` ativos na visão Por ativo (ids 1000 em diante). */
function resumoComAtivos(n: number) {
  const grupo = RESUMO.por_ativo[0] as (typeof RESUMO.por_ativo)[number];
  return {
    ...RESUMO,
    por_ativo: Array.from({ length: n }, (_, i) => ({ ...grupo, ativo_id: 1000 + i })),
  };
}

describe("Quantidade por página", () => {
  it("Operações: padrão de 10, faixa exibida e botões nas pontas", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasPaginadas(),
    });
    expect(await screen.findByText("1–10 de 31 operações")).toBeInTheDocument();
    expect(ultimaLista(chamadas)?.query.get("limite")).toBe("10");
    expect(ultimaLista(chamadas)?.query.get("deslocamento")).toBe("0");
    expect(screen.getByLabelText("Mostrar")).toHaveValue("10");
    expect(screen.getByText("operações por página")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Paginação" });
    expect(within(nav).getByRole("button", { name: /Anterior/ })).toBeDisabled();
    expect(within(nav).getByText("Página 1 de 4")).toBeInTheDocument();

    await usuario.click(within(nav).getByRole("button", { name: /Próxima/ }));
    expect(await screen.findByText("11–20 de 31 operações")).toBeInTheDocument();
    expect(ultimaLista(chamadas)?.query.get("deslocamento")).toBe("10");
    expect(url()).toContain("pagina=2");

    // Última página: 31–31, Próxima desabilitada.
    await usuario.click(within(nav).getByRole("button", { name: /Próxima/ }));
    await screen.findByText("21–30 de 31 operações");
    await usuario.click(within(nav).getByRole("button", { name: /Próxima/ }));
    expect(await screen.findByText("31–31 de 31 operações")).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: /Próxima/ })).toBeDisabled();
  });

  it("trocar para 25 manda limite=25, grava na URL e volta para a página 1", async () => {
    const { usuario, chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasPaginadas(),
      url: "/?pagina=3",
    });
    await screen.findByText("21–30 de 31 operações");
    await usuario.selectOptions(screen.getByLabelText("Mostrar"), "25");
    expect(await screen.findByText("1–25 de 31 operações")).toBeInTheDocument();
    expect(ultimaLista(chamadas)?.query.get("limite")).toBe("25");
    expect(ultimaLista(chamadas)?.query.get("deslocamento")).toBe("0");
    expect(url()).toContain("itens=25");
    expect(url()).not.toContain("pagina=");
  });

  it("valor inválido na URL vira 10; página além da última vai para a última", async () => {
    const { chamadas } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasPaginadas(),
      url: "/?itens=30&pagina=9",
    });
    // 31 operações de 10 em 10 = 4 páginas: a página 9 volta para a 4.
    expect(await screen.findByText("31–31 de 31 operações")).toBeInTheDocument();
    expect(url()).toContain("pagina=4");
    expect(ultimaLista(chamadas)?.query.get("limite")).toBe("10");
  });

  it("mudar um filtro do topo volta as duas visões para a página 1", async () => {
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: rotasPaginadas(),
      url: "/?pagina=2&pagina_ativos=2",
    });
    await screen.findByText("11–20 de 31 operações");
    await usuario.selectOptions(screen.getByLabelText("Moeda"), "BRL");
    await waitFor(() => {
      expect(url()).toContain("moeda=BRL");
    });
    expect(url()).not.toContain("pagina=");
    expect(url()).not.toContain("pagina_ativos=");
  });

  it("Por ativo: 12 ativos = 10 na primeira página e 2 na segunda; tamanho separado por visão", async () => {
    const { usuario } = renderizar(<AbaHistorico agora={AGORA} />, {
      rotas: { ...rotasPaginadas(), "GET /api/transacoes/resumo": resumoComAtivos(12) },
      url: "/?itens=50",
    });
    await screen.findByText("1–31 de 31 operações");
    await usuario.click(screen.getByRole("button", { name: "Por ativo" }));
    const tabela = await screen.findByRole("table", { name: "Histórico por ativo" });
    expect(within(tabela).getAllByRole("button", { name: /Ver por instituição/ })).toHaveLength(10);
    expect(screen.getByText("1–10 de 12 ativos")).toBeInTheDocument();
    expect(screen.getByText("ativos por página")).toBeInTheDocument();
    expect(screen.getByLabelText("Mostrar")).toHaveValue("10"); // não herda os 50 de Operações

    await usuario.click(screen.getByRole("button", { name: /Próxima/ }));
    expect(await screen.findByText("11–12 de 12 ativos")).toBeInTheDocument();
    expect(within(tabela).getAllByRole("button", { name: /Ver por instituição/ })).toHaveLength(2);
    expect(url()).toContain("pagina_ativos=2");

    await usuario.selectOptions(screen.getByLabelText("Mostrar"), "25");
    expect(await screen.findByText("1–12 de 12 ativos")).toBeInTheDocument();
    expect(url()).toContain("itens_ativos=25");
    expect(url()).toContain("itens=50");
    expect(url()).not.toContain("pagina_ativos=");
  });

  it("sem operações, o rodapé de paginação não aparece", async () => {
    renderizar(<AbaHistorico agora={AGORA} />, { rotas: rotasPaginadas(0) });
    expect(await screen.findByText("Nenhuma operação com esses filtros")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mostrar")).not.toBeInTheDocument();
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
