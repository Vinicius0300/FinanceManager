import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderizar, type Chamada } from "@/test/api-falsa";
import { AbaCaixa } from "./caixa/AbaCaixa";
import { AbaEventos } from "./eventos/AbaEventos";

const AGORA = new Date(2026, 9, 29, 12);
const limpo = (t: string | null) => (t ?? "").replace(/\u00a0/g, " ");

const CAIXA = {
  "GET /api/contas": [
    { id: 1, instituicao_id: 1, instituicao_nome: "XP", moeda: "BRL", saldo: "898.50" },
    { id: 2, instituicao_id: 1, instituicao_nome: "XP", moeda: "USD", saldo: "10.00" },
  ],
  "GET /api/instituicoes/{id}/extrato": (c: Chamada) => ({
    instituicao_id: 1,
    moeda: c.query.get("moeda"),
    saldo_final: c.query.get("moeda") === "USD" ? "10.00" : "898.50",
    total: 3,
    limite: 50,
    deslocamento: 0,
    itens:
      c.query.get("moeda") === "USD"
        ? []
        : [
            {
              id: 1,
              conta_id: 1,
              transacao_id: null,
              tipo: "deposito",
              data: "2026-10-01",
              valor: "10000.00",
              descricao: "Aporte inicial",
              criado_em: "",
            },
            {
              id: 2,
              conta_id: 1,
              transacao_id: 9,
              tipo: "debito_compra",
              data: "2026-10-24",
              valor: "7626.00",
              descricao: null,
              criado_em: "",
            },
            {
              id: 3,
              conta_id: 1,
              transacao_id: null,
              tipo: "ajuste_saldo",
              data: "2026-10-24",
              valor: "124.50",
              descricao: null,
              criado_em: "",
            },
          ],
  }),
};

describe("Aba Caixa", () => {
  it("saldo por instituição e moeda, extrato e ações só nos movimentos manuais/ajuste", async () => {
    const { usuario, chamadas } = renderizar(<AbaCaixa agora={AGORA} />, { rotas: CAIXA });
    const [xp] = await screen.findAllByRole("button", { name: /Saldo em BRL/ });
    expect(limpo(xp?.textContent ?? "")).toContain("R$ 898,50");
    expect(limpo(screen.getByRole("button", { name: /Saldo em USD/ }).textContent)).toContain(
      "US$ 10,00",
    );
    // RICO sem conta ainda: mostra saldo zero em BRL.
    expect(screen.getAllByRole("button", { name: /Saldo em BRL/ })).toHaveLength(2);

    const extrato = await screen.findByRole("table", { name: "Extrato" });
    const linhas = within(extrato).getAllByRole("row");
    expect(limpo(linhas[1]?.textContent ?? "")).toContain("+R$ 10.000,00");
    expect(limpo(linhas[2]?.textContent ?? "")).toContain("−R$ 7.626,00");
    expect(within(linhas[2] as HTMLElement).queryByRole("button")).not.toBeInTheDocument();
    expect(
      within(linhas[3] as HTMLElement).getByText("Ajuste de saldo (depósito não informado)"),
    ).toBeInTheDocument();
    expect(within(linhas[3] as HTMLElement).getAllByRole("button")).toHaveLength(2);

    await usuario.click(screen.getByRole("button", { name: /Saldo em USD/ }));
    expect(await screen.findByText("Nenhum movimento nesta conta")).toBeInTheDocument();
    expect(chamadas.some((c) => c.query.get("moeda") === "USD")).toBe(true);
  });

  it("depósito manual com validação e alteração de valor", async () => {
    const { usuario, chamadas } = renderizar(<AbaCaixa agora={AGORA} />, {
      rotas: {
        ...CAIXA,
        "POST /api/movimentos": (c: Chamada) => ({
          id: 9,
          conta_id: 1,
          transacao_id: null,
          tipo: "deposito",
          criado_em: "",
          descricao: null,
          ...(c.corpo as object),
        }),
        "PATCH /api/movimentos/{id}": (c: Chamada) => ({ id: 1, ...(c.corpo as object) }),
      },
    });
    await screen.findByRole("table", { name: "Extrato" });
    await usuario.click(screen.getByRole("button", { name: "Depósito" }));
    const dialogo = await screen.findByRole("dialog", { name: "Novo depósito" });
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    expect(await within(dialogo).findByText("Campo obrigatório.")).toBeInTheDocument();
    await usuario.type(within(dialogo).getByLabelText(/^Valor/), "1.500,00");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
        instituicao_id: 1,
        moeda: "BRL",
        tipo: "deposito",
        data: "2026-10-29",
        valor: "1500.00",
        descricao: null,
      });
    });

    await usuario.click(screen.getByRole("button", { name: "Alterar valor de 01/10/2026" }));
    const editar = await screen.findByRole("dialog");
    expect(within(editar).getByLabelText(/^Data/)).toBeDisabled();
    const valor = within(editar).getByLabelText(/^Valor/);
    expect(valor).toHaveValue("10000,00");
    await usuario.clear(valor);
    await usuario.type(valor, "9000");
    await usuario.click(within(editar).getByRole("button", { name: "Salvar" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "PATCH")?.corpo).toEqual({ valor: "9000" });
    });
  });

  it("instituição: cadastro e exclusão recusada pela API com mensagem", async () => {
    const { usuario, chamadas } = renderizar(<AbaCaixa agora={AGORA} />, {
      rotas: {
        ...CAIXA,
        "POST /api/instituicoes": (c: Chamada) => ({
          id: 3,
          criado_em: "",
          ...(c.corpo as object),
        }),
        "DELETE /api/instituicoes/{id}": {
          status: 409,
          corpo: {
            codigo: "conflito",
            mensagem: "A instituição XP tem transações e não pode ser excluída.",
          },
        },
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Nova instituição" }));
    const dialogo = await screen.findByRole("dialog");
    await usuario.type(within(dialogo).getByLabelText(/^Nome/), "Inter");
    await usuario.selectOptions(within(dialogo).getByLabelText(/^Tipo/), "banco");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
        nome: "Inter",
        tipo: "banco",
      });
    });

    await usuario.click(screen.getByRole("button", { name: "Excluir XP" }));
    const confirmacao = await screen.findByRole("alertdialog");
    await usuario.click(within(confirmacao).getByRole("button", { name: "Excluir" }));
    expect(await within(confirmacao).findByText(/não pode ser excluída/)).toBeInTheDocument();
  });
});

describe("Aba Eventos corporativos", () => {
  const EVENTOS = {
    "GET /api/eventos-corporativos": [
      {
        id: 1,
        ativo_id: 10,
        tipo: "desdobramento",
        data: "2026-03-10",
        proporcao_de: 1,
        proporcao_para: 2,
        custo_unitario: "0",
        cambio: "1",
        observacao: null,
        criado_em: "",
      },
    ],
  };

  it("lista e cadastra com validação da proporção (só ativos em cotas)", async () => {
    const { usuario, chamadas } = renderizar(<AbaEventos agora={AGORA} />, {
      rotas: {
        ...EVENTOS,
        "POST /api/eventos-corporativos": (c: Chamada) => ({
          id: 2,
          criado_em: "",
          ...(c.corpo as object),
        }),
      },
    });
    const tabela = await screen.findByRole("table", { name: "Eventos corporativos" });
    expect(tabela).toHaveTextContent("Desdobramento");
    expect(tabela).toHaveTextContent("1:2");

    await usuario.click(screen.getByRole("button", { name: "Novo evento" }));
    const dialogo = await screen.findByRole("dialog");
    const ativo = await within(dialogo).findByLabelText(/^Ativo/);
    expect(within(ativo).queryByRole("option", { name: "CDB Banco X" })).not.toBeInTheDocument();
    await usuario.selectOptions(ativo, "10");
    await usuario.selectOptions(within(dialogo).getByLabelText(/^Evento/), "grupamento");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    expect(
      await within(dialogo).findByText(/No grupamento a quantidade final é menor/),
    ).toBeInTheDocument();

    const para = within(dialogo).getByLabelText(/^Para/);
    const de = within(dialogo).getByLabelText(/^De/);
    await usuario.clear(de);
    await usuario.type(de, "10");
    await usuario.clear(para);
    await usuario.type(para, "1");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
        ativo_id: 10,
        tipo: "grupamento",
        data: "2026-10-29",
        proporcao_de: 10,
        proporcao_para: 1,
        custo_unitario: "0",
        cambio: null,
        observacao: null,
      });
    });
  });

  it("bonificação de ativo em USD pede custo unitário e câmbio opcional", async () => {
    const { usuario } = renderizar(<AbaEventos agora={AGORA} />, { rotas: EVENTOS });
    await usuario.click(await screen.findByRole("button", { name: "Novo evento" }));
    const dialogo = await screen.findByRole("dialog");
    await usuario.selectOptions(await within(dialogo).findByLabelText(/^Ativo/), "11");
    await usuario.selectOptions(within(dialogo).getByLabelText(/^Evento/), "bonificacao");
    expect(within(dialogo).getByLabelText(/^Custo unitário atribuído \(USD\)/)).toBeInTheDocument();
    expect(within(dialogo).getByLabelText(/^Câmbio \(R\$ por USD\)/)).toBeInTheDocument();
  });
});
