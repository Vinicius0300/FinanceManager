import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ativo, renderizar, type Chamada } from "@/test/api-falsa";
import { DialogoAtivo } from "./DialogoAtivo";

const FUNDO = ativo({
  id: 20,
  tipo: "fundo",
  simbolo: null,
  nome: "Fundo X",
  provider: "cvm",
  metadados: { cnpj: "11222333000181" },
});

const CDB = ativo({
  id: 12,
  tipo: "renda_fixa",
  simbolo: null,
  nome: "CDB Banco X",
  provider: null,
  metadados: {
    indexador: "cdi",
    taxa: "110",
    data_aplicacao: "2026-01-02",
    vencimento: "2028-01-03",
    emissor: "Banco X",
    liquidez: "diaria",
  },
});

describe("edição de ativo (formulário gerado pelo schema do tipo)", () => {
  it("mostra os campos do tipo: renda fixa sem ticker; fundo com CNPJ e ajuda da subclasse", async () => {
    const { unmount } = renderizar(<DialogoAtivo aberto aoMudar={vi.fn()} ativo={CDB} />);
    expect(await screen.findByLabelText(/^Tipo de ativo/)).toHaveValue("renda_fixa");
    expect(screen.queryByLabelText(/^Símbolo \(ticker\)/)).not.toBeInTheDocument();
    for (const rotulo of [/^Indexador/, /^Taxa/, /^Data de aplicação/, /^Vencimento/]) {
      expect(screen.getByLabelText(rotulo)).toBeInTheDocument();
    }
    expect(screen.getByLabelText(/^Taxa/)).toHaveValue("110");
    unmount();

    renderizar(<DialogoAtivo aberto aoMudar={vi.fn()} ativo={FUNDO} />);
    expect(await screen.findByLabelText(/^CNPJ do fundo/)).toHaveValue("11222333000181");
    expect(screen.getByText("Usado para buscar o valor da cota na CVM.")).toBeInTheDocument();
    expect(screen.getByText(/ID_SUBCLASSE/)).toBeInTheDocument();
  });

  it("valida pelo schema antes de chamar a API", async () => {
    const { usuario, chamadas } = renderizar(<DialogoAtivo aberto aoMudar={vi.fn()} ativo={CDB} />);
    const taxa = await screen.findByLabelText(/^Taxa/);
    await usuario.clear(taxa);
    await usuario.clear(screen.getByLabelText(/^Nome/));
    await usuario.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(await screen.findAllByText("Campo obrigatório.")).toHaveLength(2);
    expect(chamadas.filter((c) => c.metodo === "PUT")).toHaveLength(0);
  });

  it("erro por campo da API vai para o campo gerado (ex.: CNPJ)", async () => {
    const { usuario } = renderizar(<DialogoAtivo aberto aoMudar={vi.fn()} ativo={FUNDO} />, {
      rotas: {
        "PUT /api/ativos/{id}": {
          status: 422,
          corpo: {
            codigo: "validacao",
            mensagem: "Dados do fundo inválidos.",
            detalhes: [{ campo: "cnpj", mensagem: "CNPJ inválido." }],
          },
        },
      },
    });
    const cnpj = await screen.findByLabelText(/^CNPJ do fundo/);
    await usuario.clear(cnpj);
    await usuario.type(cnpj, "00.000.000/0000-00");
    await usuario.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(await screen.findByText("CNPJ inválido.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^CNPJ do fundo/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Dados do fundo inválidos.")).toBeInTheDocument();
  });

  it("tipo, moeda e símbolo bloqueados; PUT só com o que pode mudar", async () => {
    const aoMudar = vi.fn();
    const apple = ativo({
      id: 11,
      tipo: "acao_us",
      simbolo: "AAPL",
      nome: "Apple",
      moeda: "USD",
      metadados: { bolsa: "NASDAQ" },
    });
    const { usuario, chamadas } = renderizar(
      <DialogoAtivo aberto aoMudar={aoMudar} ativo={apple} />,
      {
        rotas: { "PUT /api/ativos/{id}": (c: Chamada) => ({ ...apple, ...(c.corpo as object) }) },
      },
    );
    expect(await screen.findByLabelText(/^Tipo de ativo/)).toBeDisabled();
    expect(screen.getByLabelText(/^Moeda/)).toBeDisabled();
    expect(screen.getByLabelText(/^Símbolo \(ticker\)/)).toBeDisabled();
    const nome = screen.getByLabelText(/^Nome/);
    await usuario.clear(nome);
    await usuario.type(nome, "Apple Inc.");
    await usuario.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    const put = chamadas.find((c) => c.metodo === "PUT");
    expect(put?.caminho).toBe("/api/ativos/11");
    expect(put?.corpo).toEqual({
      nome: "Apple Inc.",
      simbolo_externo: null,
      metadados: { bolsa: "NASDAQ" },
    });
  });
});
