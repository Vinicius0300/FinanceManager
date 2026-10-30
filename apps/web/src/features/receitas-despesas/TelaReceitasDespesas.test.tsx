import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderizar, type Chamada } from "@/test/api-falsa";
import { limitesDoMes, somarMes } from "./consultas";
import { TelaReceitasDespesas } from "./TelaReceitasDespesas";

const AGORA = new Date(2026, 9, 29, 12);
const limpo = (t: string | null) => (t ?? "").replace(/\u00a0/g, " ");

const ROTAS = {
  "GET /api/resumo-mensal": (c: Chamada) => ({
    ano: Number(c.query.get("ano")),
    mes: Number(c.query.get("mes")),
    total_receitas: "8000.00",
    total_despesas: "5500.00",
    saldo: "2500.00",
    por_categoria: [
      {
        categoria_id: 1,
        categoria_nome: "Moradia",
        tipo: "despesa",
        total: "3000.00",
        percentual: "0.5455",
      },
      {
        categoria_id: null,
        categoria_nome: "Sem categoria",
        tipo: "despesa",
        total: "2500.00",
        percentual: "0.4545",
      },
      {
        categoria_id: 3,
        categoria_nome: "Salário",
        tipo: "receita",
        total: "8000.00",
        percentual: "1",
      },
    ],
  }),
  "GET /api/categorias": [
    { id: 1, nome: "Moradia", tipo: "despesa" },
    { id: 2, nome: "Lazer", tipo: "despesa" },
    { id: 3, nome: "Salário", tipo: "receita" },
  ],
  "GET /api/lancamentos": {
    itens: [
      {
        id: 1,
        tipo: "despesa",
        data: "2026-10-05",
        valor: "3000.00",
        categoria_id: 1,
        categoria_nome: "Moradia",
        descricao: "Aluguel",
        observacao: null,
        criado_em: "",
      },
      {
        id: 2,
        tipo: "receita",
        data: "2026-10-01",
        valor: "8000.00",
        categoria_id: 3,
        categoria_nome: "Salário",
        descricao: "Salário",
        observacao: null,
        criado_em: "",
      },
    ],
    total: 2,
    limite: 500,
    deslocamento: 0,
  },
};

describe("utilitários de mês", () => {
  it("limites e navegação entre anos", () => {
    expect(limitesDoMes({ ano: 2026, mes: 2 })).toEqual({
      inicio: "2026-02-01",
      fim: "2026-02-28",
    });
    expect(somarMes({ ano: 2026, mes: 1 }, -1)).toEqual({ ano: 2025, mes: 12 });
    expect(somarMes({ ano: 2026, mes: 12 }, 1)).toEqual({ ano: 2027, mes: 1 });
  });
});

describe("Receitas e Despesas", () => {
  it("resumo do mês, gráfico por categoria (só despesas) e lançamentos com sinal", async () => {
    const { chamadas } = renderizar(<TelaReceitasDespesas agora={AGORA} />, { rotas: ROTAS });
    const saldo = await screen.findByRole("region", { name: "Saldo do mês" });
    await waitFor(() => {
      expect(limpo(saldo.textContent)).toContain("+R$ 2.500,00");
    });
    expect(limpo(screen.getByRole("region", { name: "Gasto" }).textContent)).toContain(
      "R$ 5.500,00",
    );
    const grafico = await screen.findByRole("img", { name: "Despesas do mês por categoria" });
    const opcoes = JSON.parse(grafico.getAttribute("data-opcoes") ?? "{}") as {
      series: { data: { name: string }[] }[];
    };
    expect(opcoes.series[0]?.data.map((d) => d.name)).toEqual(["Moradia", "Sem categoria"]);
    const tabela = await screen.findByRole("table", { name: "Lançamentos do mês" });
    expect(limpo(tabela.textContent)).toContain("−R$ 3.000,00");
    expect(limpo(tabela.textContent)).toContain("+R$ 8.000,00");
    const consulta = chamadas.find((c) => c.caminho === "/api/lancamentos")?.query;
    expect(consulta?.get("inicio")).toBe("2026-10-01");
    expect(consulta?.get("fim")).toBe("2026-10-31");
  });

  it("seletor de mês refaz as consultas", async () => {
    const { usuario, chamadas } = renderizar(<TelaReceitasDespesas agora={AGORA} />, {
      rotas: ROTAS,
    });
    await screen.findByRole("table", { name: "Lançamentos do mês" });
    await usuario.click(screen.getByRole("button", { name: "Mês anterior" }));
    await waitFor(() => {
      expect(
        chamadas.some((c) => c.caminho === "/api/resumo-mensal" && c.query.get("mes") === "9"),
      ).toBe(true);
    });
    expect(chamadas.some((c) => c.query.get("inicio") === "2026-09-01")).toBe(true);
    expect(screen.getByLabelText("Mês exibido")).toHaveValue("2026-09");
  });

  it("novo lançamento: categorias do tipo escolhido e corpo da API", async () => {
    const { usuario, chamadas } = renderizar(<TelaReceitasDespesas agora={AGORA} />, {
      rotas: {
        ...ROTAS,
        "POST /api/lancamentos": (c: Chamada) => ({
          id: 9,
          criado_em: "",
          categoria_nome: null,
          ...(c.corpo as object),
        }),
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Novo lançamento" }));
    const dialogo = await screen.findByRole("dialog");
    const categoria = await within(dialogo).findByLabelText(/^Categoria/);
    expect(within(categoria).getByRole("option", { name: "Lazer" })).toBeInTheDocument();
    expect(within(categoria).queryByRole("option", { name: "Salário" })).not.toBeInTheDocument();
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    expect(await within(dialogo).findAllByText("Campo obrigatório.")).toHaveLength(2);

    await usuario.type(within(dialogo).getByLabelText(/^Valor/), "120,90");
    await usuario.type(within(dialogo).getByLabelText(/^Descrição/), "Cinema");
    await usuario.selectOptions(categoria, "2");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
        tipo: "despesa",
        data: "2026-10-29",
        valor: "120.90",
        categoria_id: 2,
        descricao: "Cinema",
        observacao: null,
      });
    });
  });

  it("exclusão pede confirmação", async () => {
    const { usuario, chamadas } = renderizar(<TelaReceitasDespesas agora={AGORA} />, {
      rotas: { ...ROTAS, "DELETE /api/lancamentos/{id}": null },
    });
    await usuario.click(await screen.findByRole("button", { name: "Excluir Aluguel" }));
    const confirmacao = await screen.findByRole("alertdialog");
    expect(chamadas.filter((c) => c.metodo === "DELETE")).toHaveLength(0);
    await usuario.click(within(confirmacao).getByRole("button", { name: "Excluir" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "DELETE")?.caminho).toBe("/api/lancamentos/1");
    });
  });

  it("categorias: criar, renomear e mensagem da API ao excluir categoria em uso", async () => {
    const { usuario, chamadas } = renderizar(<TelaReceitasDespesas agora={AGORA} />, {
      rotas: {
        ...ROTAS,
        "POST /api/categorias": (c: Chamada) => ({ id: 4, ...(c.corpo as object) }),
        "PUT /api/categorias/{id}": (c: Chamada) => ({
          id: 2,
          tipo: "despesa",
          ...(c.corpo as object),
        }),
        "DELETE /api/categorias/{id}": {
          status: 409,
          corpo: { codigo: "conflito", mensagem: "A categoria Moradia tem lançamentos." },
        },
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Categorias" }));
    const dialogo = await screen.findByRole("dialog", { name: "Categorias" });
    await usuario.type(within(dialogo).getByLabelText("Nome da nova categoria"), "Mercado");
    await usuario.click(within(dialogo).getByRole("button", { name: "Adicionar" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
        nome: "Mercado",
        tipo: "despesa",
      });
    });
    await usuario.click(within(dialogo).getByRole("button", { name: "Renomear Lazer" }));
    const novoNome = within(dialogo).getByLabelText("Novo nome para Lazer");
    await usuario.clear(novoNome);
    await usuario.type(novoNome, "Diversão");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar nome" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "PUT")?.corpo).toEqual({ nome: "Diversão" });
    });
    await usuario.click(within(dialogo).getByRole("button", { name: "Excluir Moradia" }));
    const confirmacao = await screen.findByRole("alertdialog");
    await usuario.click(within(confirmacao).getByRole("button", { name: "Excluir" }));
    expect(
      await within(confirmacao).findByText("A categoria Moradia tem lançamentos."),
    ).toBeInTheDocument();
  });
});
