import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ativo, renderizar, type Chamada } from "@/test/api-falsa";
import { DialogoAtivo } from "./DialogoAtivo";

const criado = (c: Chamada) => ({ status: 201, corpo: { id: 50, ...(c.corpo as object) } });

describe("formulário de ativo gerado pelo schema do tipo", () => {
  it("troca os campos conforme o tipo (renda fixa sem símbolo; fundo com CNPJ e ajuda da subclasse)", async () => {
    const { usuario } = renderizar(<DialogoAtivo aberto aoMudar={vi.fn()} />);
    const tipo = await screen.findByLabelText(/^Tipo de ativo/);
    expect(screen.getByLabelText(/^Símbolo \(ticker\)/)).toBeInTheDocument();

    await usuario.selectOptions(tipo, "renda_fixa");
    expect(screen.queryByLabelText(/^Símbolo \(ticker\)/)).not.toBeInTheDocument();
    for (const rotulo of [
      /^Indexador/,
      /^Taxa/,
      /^Data da aplicação|^Data de aplicação/,
      /^Vencimento/,
      /^Emissor/,
      /^Liquidez/,
    ]) {
      expect(screen.getByLabelText(rotulo)).toBeInTheDocument();
    }

    await usuario.selectOptions(tipo, "fundo");
    expect(screen.getByLabelText(/^CNPJ do fundo/)).toBeInTheDocument();
    expect(screen.getByText("Usado para buscar o valor da cota na CVM.")).toBeInTheDocument();
    expect(screen.getByText(/ID_SUBCLASSE/)).toBeInTheDocument();

    await usuario.selectOptions(tipo, "tesouro_direto");
    expect(screen.getByLabelText(/^Vencimento/)).toHaveAttribute("type", "date");

    await usuario.selectOptions(tipo, "acao_us");
    expect(screen.getByLabelText(/^Moeda/)).toHaveValue("USD");
  });

  it("valida pelo schema e envia o corpo da API com os metadados normalizados", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(<DialogoAtivo aberto aoMudar={aoMudar} />, {
      rotas: { "POST /api/ativos": criado },
    });
    await usuario.selectOptions(await screen.findByLabelText(/^Tipo de ativo/), "renda_fixa");
    await usuario.click(screen.getByRole("button", { name: "Cadastrar ativo" }));
    expect(await screen.findAllByText("Campo obrigatório.")).not.toHaveLength(0);
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(0);

    await usuario.type(screen.getByLabelText(/^Nome/), "CDB Banco X");
    await usuario.selectOptions(screen.getByLabelText(/^Indexador/), "cdi");
    await usuario.type(screen.getByLabelText(/^Taxa/), "110,5");
    await usuario.type(screen.getByLabelText(/^Data d[ea] aplicação/), "2026-01-02");
    await usuario.type(screen.getByLabelText(/^Vencimento/), "2028-01-03");
    await usuario.type(screen.getByLabelText(/^Emissor/), "Banco X");
    await usuario.selectOptions(screen.getByLabelText(/^Liquidez/), "diaria");
    await usuario.click(screen.getByRole("button", { name: "Cadastrar ativo" }));

    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
      tipo: "renda_fixa",
      nome: "CDB Banco X",
      simbolo: null,
      moeda: "BRL",
      simbolo_externo: null,
      metadados: {
        indexador: "cdi",
        taxa: "110.5",
        data_aplicacao: "2026-01-02",
        vencimento: "2028-01-03",
        emissor: "Banco X",
        liquidez: "diaria",
      },
    });
  });

  it("erro por campo da API vai para o campo gerado (ex.: CNPJ)", async () => {
    const { usuario } = renderizar(<DialogoAtivo aberto aoMudar={vi.fn()} />, {
      rotas: {
        "POST /api/ativos": {
          status: 422,
          corpo: {
            codigo: "validacao",
            mensagem: "Dados do fundo inválidos.",
            detalhes: [{ campo: "cnpj", mensagem: "CNPJ inválido." }],
          },
        },
      },
    });
    await usuario.selectOptions(await screen.findByLabelText(/^Tipo de ativo/), "fundo");
    await usuario.type(screen.getByLabelText(/^Nome/), "Fundo X");
    await usuario.type(screen.getByLabelText(/^CNPJ do fundo/), "00.000.000/0000-00");
    await usuario.click(screen.getByRole("button", { name: "Cadastrar ativo" }));
    expect(await screen.findByText("CNPJ inválido.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^CNPJ do fundo/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Dados do fundo inválidos.")).toBeInTheDocument();
  });

  it("edição: tipo, moeda e símbolo bloqueados; PUT só com o que pode mudar", async () => {
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
    expect(screen.getByLabelText(/^Nome/)).toHaveValue("Apple");
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
