import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderizar, type Chamada } from "@/test/api-falsa";
import { DialogoTransacao } from "./DialogoTransacao";

const AGORA = new Date(2026, 9, 29, 12);

const SALDO_INSUFICIENTE = {
  status: 409,
  corpo: {
    codigo: "saldo_insuficiente",
    mensagem: "Saldo insuficiente em XP (BRL) em 29/10/2026: faltam 1.234,50 BRL.",
    detalhes: [
      { campo: "instituicao_id", mensagem: "1" },
      { campo: "instituicao", mensagem: "XP" },
      { campo: "moeda", mensagem: "BRL" },
      { campo: "data", mensagem: "2026-10-29" },
      { campo: "valor_faltante", mensagem: "1234.50" },
    ],
  },
};

const ATIVO_SEMELHANTE = {
  status: 409,
  corpo: {
    codigo: "ativo_semelhante",
    mensagem: "Você já tem um título com os mesmos dados (CDB Banco X).",
    detalhes: [
      { campo: "ativo_id", mensagem: "12" },
      { campo: "nome", mensagem: "CDB Banco X" },
      { campo: "resumo", mensagem: "CDB Banco X · indexador: cdi · taxa: 110" },
    ],
  },
};

function transacaoGravada(corpo: Record<string, unknown>) {
  return {
    id: 99,
    ativo_id: 10,
    instituicao_id: 1,
    tipo: "compra" as const,
    data: "2026-10-29",
    quantidade: null,
    preco_unitario: null,
    taxas: "0",
    moeda: "BRL",
    cambio: "1",
    criado_em: "2026-10-29T12:00:00Z",
    movimentos: [],
    valor_total: "0",
    valor_total_brl: "0",
    taxas_brl: "0",
    imposto_retido_brl: "0",
    resultado: null,
    resultado_brl: null,
    situacao: "aberta" as const,
    valor: null,
    subtipo_provento: null,
    imposto_retido: "0",
    observacao: null,
    ...corpo,
  };
}

function movimentacaoGravada(corpo: Record<string, unknown>, criado = true) {
  return {
    status: 201,
    corpo: {
      transacao: transacaoGravada({}),
      ativo: {
        id: 50,
        tipo: "fundo_listado",
        nome: "x",
        simbolo: "X",
        moeda: "BRL",
        provider: "yfinance",
        simbolo_externo: null,
        metadados: {},
        criado_em: "2026-10-29T12:00:00Z",
      },
      ativo_criado: criado,
      ...corpo,
    },
  };
}

const BUSCA_HGLG = {
  itens: [
    {
      simbolo: "HGLG11",
      nome: "PATRIA LOG - FDO INV IMOB",
      tipo: "fundo_listado",
      origem: "lista",
      ativo_id: null,
      simbolo_externo: "HGLG11.SA",
      categoria: "FUNDS",
      campos_sugeridos: {},
    },
  ],
  bolsa: "B3",
  lista_disponivel: true,
  atualizando_lista: false,
  aviso: null,
};

const BUSCA_BOVA = {
  ...BUSCA_HGLG,
  itens: [
    {
      simbolo: "BOVA11",
      nome: "ISHARES IBOVESPA FUNDO DE ÍNDICE",
      tipo: "etf_br",
      origem: "lista",
      ativo_id: null,
      simbolo_externo: "BOVA11.SA",
      categoria: "ETF EQUITIES",
      campos_sugeridos: {},
    },
  ],
};

const POSICOES = [
  {
    ativo_id: 10,
    nome: "Petrobras PN",
    simbolo: "PETR4",
    tipo: "acao_br",
    moeda: "BRL",
    instituicao_id: 1,
    quantidade: "100",
    preco_medio: "30",
    preco_atual: "38",
    valor: "3800",
    valor_brl: "3800",
    origem: "automatico",
    data_preco: "2026-10-29",
    defasado: false,
    aviso: null,
    erro: null,
    participacao: "1",
    metricas: null,
    metricas_brl: null,
    variacao_dia: null,
  },
];

type Usuario = ReturnType<typeof renderizar>["usuario"];

async function escolherTipo(usuario: Usuario, slug: string) {
  await usuario.selectOptions(await screen.findByLabelText(/^Tipo de ativo/), slug);
}

async function compraPetr4(usuario: Usuario) {
  await escolherTipo(usuario, "acao_br");
  await usuario.selectOptions(screen.getByLabelText(/^Instituição/), "1");
  await usuario.type(screen.getByRole("combobox", { name: /^Ativo/ }), "PETR4");
  await usuario.click(await screen.findByRole("option", { name: /PETR4 · Petrobras PN/ }));
  await usuario.type(screen.getByLabelText(/^Quantidade/), "200");
  await usuario.type(screen.getByLabelText(/^Preço unitário/), "38,12");
  await usuario.type(screen.getByLabelText(/^Taxas/), "2");
}

const BUSCA_PETR4 = {
  ...BUSCA_HGLG,
  itens: [
    {
      simbolo: "PETR4",
      nome: "Petrobras PN",
      tipo: "acao_br",
      origem: "carteira",
      ativo_id: 10,
      simbolo_externo: null,
      categoria: null,
      campos_sugeridos: {},
    },
  ],
};

const posts = (chamadas: Chamada[]) =>
  chamadas.filter((c) => c.metodo === "POST" && c.caminho === "/api/movimentacoes");

describe("DialogoTransacao (formulário único)", () => {
  it("valida em pt-BR e não chama a API com campos faltando", async () => {
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />,
    );
    await usuario.click(await screen.findByRole("button", { name: "Registrar" }));
    expect(await screen.findByText("Escolha o tipo de ativo.")).toBeInTheDocument();
    expect(screen.getByText("Escolha a instituição.")).toBeInTheDocument();
    expect(posts(chamadas)).toHaveLength(0);
    // Sem tipo, a operação fica bloqueada e os campos de valores não aparecem.
    expect(screen.getByLabelText(/^Operação/)).toBeDisabled();
    expect(screen.queryByLabelText(/^Quantidade/)).not.toBeInTheDocument();
  });

  it("operações mudam com o tipo (renda fixa: aporte e resgate)", async () => {
    const { usuario } = renderizar(<DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />);
    await escolherTipo(usuario, "renda_fixa");
    const operacao = screen.getByLabelText(/^Operação/);
    expect(
      within(operacao)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Aporte", "Resgate"]);
    expect(operacao).toHaveValue("aporte");
    expect(screen.getByLabelText(/^Valor \(BRL\)/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^Taxas/)).not.toBeInTheDocument();
  });

  it("compra de ativo da carteira pela busca", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={aoMudar} agora={AGORA} />,
      {
        rotas: {
          "GET /api/simbolos/busca": BUSCA_PETR4,
          "POST /api/movimentacoes": movimentacaoGravada({}, false),
        },
      },
    );
    await compraPetr4(usuario);
    expect(screen.getByText(/já na carteira/)).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    expect(posts(chamadas)[0]?.corpo).toMatchObject({
      ativo_id: 10,
      instituicao_id: 1,
      quantidade: "200",
      preco_unitario: "38.12",
      taxas: "2",
      aceitar_ajuste: false,
    });
    const busca = chamadas.find((c) => c.caminho === "/api/simbolos/busca");
    expect(busca?.query.get("tipo")).toBe("acao_br");
    expect(busca?.query.get("q")).toBe("PETR4");
  });

  it("compra de FII da lista oficial: cadastra o ativo junto", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={aoMudar} agora={AGORA} />,
      {
        rotas: {
          "GET /api/simbolos/busca": BUSCA_HGLG,
          "POST /api/movimentacoes": movimentacaoGravada({}),
        },
      },
    );
    await escolherTipo(usuario, "fundo_listado");
    await usuario.selectOptions(screen.getByLabelText(/^Instituição/), "2");
    await usuario.type(screen.getByRole("combobox", { name: /^Ativo/ }), "hglg");
    const opcao = await screen.findByRole("option", { name: /HGLG11/ });
    expect(within(opcao).getByText("Novo, será cadastrado")).toBeInTheDocument();
    await usuario.keyboard("{ArrowDown}{ArrowUp}{Enter}"); // teclado: volta ao 1º e confirma
    expect(screen.getByRole("group", { name: /Novo ativo/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Ticker/)).toHaveValue("HGLG11");
    expect(screen.getByLabelText(/^Nome/)).toHaveValue("PATRIA LOG - FDO INV IMOB");
    await usuario.type(screen.getByLabelText(/^Quantidade/), "10");
    await usuario.type(screen.getByLabelText(/^Preço unitário/), "160");
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    expect(posts(chamadas)[0]?.corpo).toMatchObject({
      instituicao_id: 2,
      novo_ativo: {
        tipo: "fundo_listado",
        simbolo: "HGLG11",
        nome: "PATRIA LOG - FDO INV IMOB",
        simbolo_externo: "HGLG11.SA",
      },
    });
    expect(posts(chamadas)[0]?.corpo).not.toHaveProperty("ativo_id");
  });

  it("tipo diferente da lista oficial: avisa e troca para o tipo certo", async () => {
    const { usuario } = renderizar(<DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />, {
      rotas: { "GET /api/simbolos/busca": BUSCA_BOVA },
    });
    await escolherTipo(usuario, "acao_br");
    await usuario.type(screen.getByRole("combobox", { name: /^Ativo/ }), "BOVA11");
    const opcao = await screen.findByRole("option", { name: /BOVA11/ });
    expect(within(opcao).getByText(/Lista oficial: ETF \(Brasil\)/)).toBeInTheDocument();
    await usuario.click(opcao);
    expect(screen.getByText(/Na lista oficial, BOVA11 é/)).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Usar ETF (Brasil)" }));
    expect(screen.getByLabelText(/^Tipo de ativo/)).toHaveValue("etf_br");
    expect(screen.getByLabelText(/^Ticker/)).toHaveValue("BOVA11"); // escolha mantida
    expect(screen.queryByText(/Na lista oficial/)).not.toBeInTheDocument();
  });

  it("ticker fora das listas: cadastro manual com aviso", async () => {
    const { usuario } = renderizar(<DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />, {
      rotas: {
        "GET /api/simbolos/busca": {
          ...BUSCA_HGLG,
          itens: [],
          atualizando_lista: true,
        },
      },
    });
    await escolherTipo(usuario, "acao_br");
    await usuario.type(screen.getByRole("combobox", { name: /^Ativo/ }), "novo3");
    expect(await screen.findByText(/Atualizando a lista oficial da B3/)).toBeInTheDocument();
    await usuario.click(
      await screen.findByRole("option", { name: /Cadastrar “NOVO3” manualmente/ }),
    );
    expect(screen.getByText(/NOVO3 não foi encontrado nas listas oficiais/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Ticker/)).toHaveValue("NOVO3");
    expect(screen.getByLabelText(/^Ticker/)).not.toHaveAttribute("readonly");
  });

  it("renda fixa: novo título com campos do tipo e 409 de título semelhante", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={aoMudar} agora={AGORA} />,
      {
        rotas: {
          "POST /api/movimentacoes": (c: Chamada) => {
            const corpo = c.corpo as Record<string, unknown>;
            return corpo.usar_ativo_id ? movimentacaoGravada({}, false) : ATIVO_SEMELHANTE;
          },
        },
      },
    );
    await escolherTipo(usuario, "renda_fixa");
    await usuario.selectOptions(screen.getByLabelText(/^Instituição/), "1");
    await usuario.selectOptions(screen.getByLabelText(/^Ativo/), "novo");
    expect(screen.queryByLabelText(/^Data de aplicação/)).not.toBeInTheDocument(); // = data
    await usuario.type(screen.getByLabelText(/^Nome/), "CDB X");
    await usuario.selectOptions(screen.getByLabelText(/^Indexador/), "cdi");
    await usuario.type(screen.getByLabelText(/^Taxa/), "110");
    await usuario.type(screen.getByLabelText(/^Vencimento/), "2028-01-03");
    await usuario.type(screen.getByLabelText(/^Emissor/), "Banco X");
    await usuario.selectOptions(screen.getByLabelText(/^Liquidez/), "diaria");
    await usuario.type(screen.getByLabelText(/^Valor \(BRL\)/), "500");
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));

    const alerta = await screen.findByRole("alertdialog", { name: "Você já tem este título" });
    expect(within(alerta).getByText("CDB Banco X")).toBeInTheDocument();
    expect(posts(chamadas)[0]?.corpo).toMatchObject({
      tipo: "aporte",
      valor: "500",
      novo_ativo: {
        tipo: "renda_fixa",
        metadados: { data_aplicacao: "2026-10-29", taxa: "110", emissor: "Banco X" },
      },
    });
    await usuario.click(within(alerta).getByRole("button", { name: "Somar ao existente" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    expect(posts(chamadas)[1]?.corpo).toMatchObject({ usar_ativo_id: 12, valor: "500" });
  });

  it("venda: só posições da instituição na data, com o disponível e aviso acima dele", async () => {
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />,
      { rotas: { "GET /api/portfolio/posicoes": POSICOES } },
    );
    await escolherTipo(usuario, "acao_br");
    await usuario.selectOptions(screen.getByLabelText(/^Operação/), "venda");
    expect(screen.getByText(/Escolha a instituição para ver as posições/)).toBeInTheDocument();
    await usuario.selectOptions(screen.getByLabelText(/^Instituição/), "1");
    const ativo = await screen.findByLabelText(/^Ativo/);
    expect(
      within(ativo)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Escolha…", "PETR4 · Petrobras PN"]);
    await usuario.selectOptions(ativo, "10");
    expect(screen.getByText("Disponível: 100")).toBeInTheDocument();
    await usuario.type(screen.getByLabelText(/^Quantidade/), "150");
    expect(screen.getByText(/Maior que a posição: o registro será recusado/)).toBeInTheDocument();
    const consulta = chamadas.find((c) => c.caminho === "/api/portfolio/posicoes");
    expect(consulta?.query.get("instituicao_id")).toBe("1");
    expect(consulta?.query.get("data")).toBe("2026-10-29");
  });

  it("409 de saldo insuficiente: continuar reenvia com aceitar_ajuste", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={aoMudar} agora={AGORA} />,
      {
        rotas: {
          "GET /api/simbolos/busca": BUSCA_PETR4,
          "POST /api/movimentacoes": (c: Chamada) =>
            (c.corpo as Record<string, unknown>).aceitar_ajuste
              ? movimentacaoGravada({}, false)
              : SALDO_INSUFICIENTE,
        },
      },
    );
    await compraPetr4(usuario);
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));
    const alerta = await screen.findByRole("alertdialog", { name: "Saldo insuficiente" });
    expect(within(alerta).getByText("XP (BRL)")).toBeInTheDocument();
    expect(within(alerta).getByText(/R\$\s1\.234,50/)).toBeInTheDocument();
    await usuario.click(within(alerta).getByRole("button", { name: "Continuar assim mesmo" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    expect(posts(chamadas)).toHaveLength(2);
    expect(posts(chamadas)[1]?.corpo).toMatchObject({ aceitar_ajuste: true, quantidade: "200" });
  });

  it("cancelar no aviso de saldo não grava e volta ao formulário", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={aoMudar} agora={AGORA} />,
      {
        rotas: {
          "GET /api/simbolos/busca": BUSCA_PETR4,
          "POST /api/movimentacoes": SALDO_INSUFICIENTE,
        },
      },
    );
    await compraPetr4(usuario);
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));
    const alerta = await screen.findByRole("alertdialog");
    await usuario.click(within(alerta).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    expect(posts(chamadas)).toHaveLength(1);
    expect(aoMudar).not.toHaveBeenCalled();
  });

  it("outros erros da API aparecem no campo certo (inclusive do ativo novo)", async () => {
    const { usuario } = renderizar(<DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />, {
      rotas: {
        "GET /api/simbolos/busca": BUSCA_HGLG,
        "POST /api/movimentacoes": {
          status: 422,
          corpo: {
            codigo: "validacao",
            mensagem: "Dados inválidos.",
            detalhes: [
              { campo: "nome", mensagem: "Use no máximo 150 caracteres." },
              { campo: "quantidade", mensagem: "Quantidade inválida." },
            ],
          },
        },
      },
    });
    await escolherTipo(usuario, "fundo_listado");
    await usuario.selectOptions(screen.getByLabelText(/^Instituição/), "1");
    await usuario.type(screen.getByRole("combobox", { name: /^Ativo/ }), "hglg");
    await usuario.click(await screen.findByRole("option", { name: /HGLG11/ }));
    await usuario.type(screen.getByLabelText(/^Quantidade/), "1");
    await usuario.type(screen.getByLabelText(/^Preço unitário/), "1");
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));
    expect(await screen.findByText("Use no máximo 150 caracteres.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Nome/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/^Quantidade/)).toHaveAttribute("aria-invalid", "true");
  });

  it("câmbio aparece para ativo em USD", async () => {
    const { usuario } = renderizar(<DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />, {
      rotas: {
        "GET /api/simbolos/busca": {
          ...BUSCA_HGLG,
          bolsa: "EUA",
          itens: [
            {
              simbolo: "AAPL",
              nome: "Apple",
              tipo: "acao_us",
              origem: "carteira",
              ativo_id: 11,
              simbolo_externo: null,
              categoria: null,
              campos_sugeridos: {},
            },
          ],
        },
      },
    });
    await escolherTipo(usuario, "acao_us");
    expect(screen.queryByLabelText(/^Câmbio pago/)).not.toBeInTheDocument();
    await usuario.type(screen.getByRole("combobox", { name: /^Ativo/ }), "aapl");
    await usuario.click(await screen.findByRole("option", { name: /AAPL/ }));
    expect(screen.getByLabelText(/^Câmbio pago \(R\$ por USD\)/)).toBeInTheDocument();
  });

  it("edição: tipo e ativo bloqueados e PUT no mesmo id", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao
        aberto
        aoMudar={aoMudar}
        agora={AGORA}
        transacao={transacaoGravada({
          id: 7,
          ativo_id: 10,
          instituicao_id: 1,
          tipo: "venda",
          data: "2026-10-08",
          quantidade: "150",
          preco_unitario: "52.4",
          taxas: "3.5",
        })}
      />,
      {
        rotas: {
          "PUT /api/transacoes/{id}": (c: Chamada) =>
            transacaoGravada(c.corpo as Record<string, unknown>),
        },
      },
    );
    expect(await screen.findByLabelText(/^Tipo de ativo/)).toBeDisabled();
    expect(screen.getByText(/O ativo não pode ser trocado na edição/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Trocar/ })).not.toBeInTheDocument();
    const preco = screen.getByLabelText(/^Preço unitário/);
    expect(preco).toHaveValue("52,4");
    await usuario.clear(preco);
    await usuario.type(preco, "53");
    await usuario.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    const put = chamadas.find((c) => c.metodo === "PUT");
    expect(put?.caminho).toBe("/api/transacoes/7");
    expect(put?.corpo).toMatchObject({
      ativo_id: 10,
      tipo: "venda",
      preco_unitario: "53",
      taxas: "3.5",
    });
    expect(put?.corpo).not.toHaveProperty("novo_ativo");
    expect(posts(chamadas)).toHaveLength(0);
  });
});
