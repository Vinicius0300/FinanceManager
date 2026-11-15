import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatarMoeda } from "@/lib/formatacao";
import { useValoresOcultos, useValoresOcultosStore } from "@/lib/valores-ocultos";
import { renderizar } from "@/test/api-falsa";
import { BarraSuperior } from "./BarraSuperior";
import {
  agruparPorSituacao,
  contarStatus,
  idsDaSituacao,
  textoStatus,
  type Situacao,
} from "./status-cotacoes";

const limpo = (t: string | null) => (t ?? "").replaceAll(String.fromCharCode(0xa0), " ");

function status(
  ativo_id: number,
  situacao: Situacao,
  extra: { simbolo?: string | null; nome?: string; ultimo_erro?: string | null } = {},
) {
  return {
    ativo_id,
    nome: extra.nome ?? `Ativo ${ativo_id}`,
    simbolo: extra.simbolo === undefined ? `ATV${ativo_id}` : extra.simbolo,
    tipo: "acao_br",
    moeda: "BRL",
    valor: "10",
    data: "2026-10-29",
    data_hora: null,
    origem: "automatico",
    provider_preco: "yfinance",
    provider: situacao === "manual" ? null : "yfinance",
    ultima_tentativa: null,
    ultimo_sucesso: null,
    ultimo_erro: extra.ultimo_erro ?? (situacao === "com_erro" ? "Yahoo indisponível." : null),
    defasado: situacao === "defasado",
    aviso: null,
    situacao,
  };
}

const posicao = (ativo_id: number) => ({ ativo_id, nome: `Ativo ${ativo_id}` });

describe("contagem do chip de status", () => {
  it("conta pela situação do backend e só posições abertas", () => {
    const contagem = contarStatus(
      [
        status(1, "em_dia"),
        status(2, "em_dia"),
        status(3, "defasado"),
        status(4, "com_erro"),
        status(5, "com_erro"),
        status(6, "manual"),
        status(7, "defasado"), // sem posição aberta: fica de fora
      ],
      new Set([1, 2, 3, 4, 5, 6]),
    );
    expect(contagem).toEqual({ emDia: 2, defasadas: 1, comErro: 2, manuais: 1 });
    expect(textoStatus(contagem)).toBe("2 em dia · 1 defasada · 2 com erro · 1 manual");
  });

  it("omite as categorias zeradas; tudo zero mostra 0 em dia", () => {
    const zero = { emDia: 0, defasadas: 0, comErro: 0, manuais: 0 };
    expect(textoStatus({ ...zero, emDia: 14 })).toBe("14 em dia");
    expect(textoStatus({ ...zero, defasadas: 3 })).toBe("3 defasadas");
    expect(textoStatus({ ...zero, manuais: 2 })).toBe("2 manuais");
    expect(textoStatus(zero)).toBe("0 em dia");
  });

  it("agrupa erro, defasado, manual, em dia; dentro do grupo em ordem alfabética", () => {
    const itens = [
      status(1, "em_dia", { simbolo: "VALE3" }),
      status(2, "em_dia", { simbolo: "BBAS3" }),
      status(3, "manual"),
      status(4, "com_erro"),
      status(5, "defasado"),
    ];
    const grupos = agruparPorSituacao(itens, (i) => i.simbolo ?? i.nome);
    expect(grupos.map((g) => g.situacao)).toEqual(["com_erro", "defasado", "manual", "em_dia"]);
    expect(grupos[3]?.itens.map((i) => i.simbolo)).toEqual(["BBAS3", "VALE3"]);
    expect(idsDaSituacao(itens, "em_dia")).toEqual([1, 2]);
  });
});

const ROTAS = {
  "GET /api/cotacoes/status": [
    status(10, "em_dia", { simbolo: "PETR4" }),
    status(11, "com_erro", { simbolo: "MXRF11" }),
    status(12, "defasado"), // sem posição aberta
  ],
  "GET /api/portfolio/posicoes": [posicao(10), posicao(11)],
  "GET /api/cotacoes/atualizacao": {
    em_andamento: false,
    ultimo_ciclo_inicio: null,
    ultimo_ciclo_fim: null,
    precos_atualizados: null,
    erros: null,
  },
};

describe("barra superior", () => {
  it("chip com a contagem dos ativos com posição aberta", async () => {
    renderizar(<BarraSuperior />, { rotas: ROTAS });
    const chip = await screen.findByRole("button", {
      name: "Cotações: 1 em dia · 1 com erro. Ver a situação de cada ativo",
    });
    expect(limpo(chip.textContent)).toBe("1 em dia1 com erro");
    expect(screen.getByRole("switch", { name: "Modo escuro" })).toBeInTheDocument();
  });

  it("sem resposta do status, não mostra o chip (a barra continua)", async () => {
    const { chamadas } = renderizar(<BarraSuperior />, {
      rotas: { ...ROTAS, "GET /api/cotacoes/status": { status: 500, corpo: { mensagem: "x" } } },
    });
    await waitFor(() => {
      expect(chamadas.some((c) => c.caminho === "/api/cotacoes/status")).toBe(true);
    });
    expect(screen.queryByRole("button", { name: /Cotações:/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Atualizar cotações" })).toBeInTheDocument();
  });

  it("atualização forçada não trava e mostra o 409 de ciclo em andamento", async () => {
    let tentativas = 0;
    const { usuario, chamadas } = renderizar(<BarraSuperior />, {
      rotas: {
        ...ROTAS,
        "POST /api/cotacoes/atualizar": () => {
          tentativas += 1;
          return tentativas === 1
            ? { mensagem: "Atualização iniciada." }
            : {
                status: 409,
                corpo: {
                  codigo: "atualizacao_em_andamento",
                  mensagem: "Já existe uma atualização em andamento.",
                },
              };
        },
      },
    });
    const botao = await screen.findByRole("button", { name: "Atualizar cotações" });
    await usuario.click(botao);
    await waitFor(() => {
      expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(1);
    });
    await usuario.click(screen.getByRole("button", { name: "Atualizar cotações" }));
    expect(await screen.findByText("Já existe uma atualização em andamento.")).toBeInTheDocument();
  });

  it("olho oculta e mostra os valores da tela sem recarregá-la", async () => {
    function Saldo() {
      useValoresOcultos();
      return <p data-testid="saldo">{formatarMoeda("1234.5")}</p>;
    }
    const { usuario } = renderizar(
      <>
        <BarraSuperior />
        <Saldo />
      </>,
      { rotas: ROTAS },
    );
    expect(limpo(screen.getByTestId("saldo").textContent)).toBe("R$ 1.234,50");

    await usuario.click(screen.getByRole("button", { name: "Ocultar valores" }));
    expect(screen.getByTestId("saldo")).toHaveTextContent("R$ •••••");
    const botao = screen.getByRole("button", { name: "Mostrar valores" });
    expect(botao).toHaveAttribute("aria-pressed", "true");
    expect(useValoresOcultosStore.getState().ocultos).toBe(true);

    await usuario.click(botao);
    expect(limpo(screen.getByTestId("saldo").textContent)).toBe("R$ 1.234,50");
    expect(screen.getByRole("button", { name: "Ocultar valores" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});

const ROTAS_PAINEL = {
  ...ROTAS,
  "GET /api/cotacoes/status": [
    { ...status(10, "em_dia", { simbolo: "PETR4", nome: "Petrobras PN" }), valor: "38.45" },
    status(11, "com_erro", { simbolo: "MXRF11", ultimo_erro: "Ticker não encontrado na fonte." }),
    status(12, "defasado", { simbolo: "IVVB11" }),
    status(13, "defasado", { simbolo: "BOVA11" }),
    status(14, "manual", { simbolo: "CPA3" }),
    status(15, "defasado", { simbolo: "FORA3" }), // sem posição aberta
  ],
  "GET /api/portfolio/posicoes": [10, 11, 12, 13, 14].map(posicao),
};

async function abrirPainel(rotas: Record<string, unknown> = ROTAS_PAINEL) {
  const tela = renderizar(<BarraSuperior />, { rotas: rotas as never });
  await tela.usuario.click(await screen.findByRole("button", { name: /^Cotações:/ }));
  const painel = await screen.findByRole("dialog");
  return { ...tela, painel };
}

describe("painel de status das cotações", () => {
  it("clicar no chip abre o painel com cada ativo agrupado pela situação", async () => {
    const { painel } = await abrirPainel();
    expect(within(painel).getByRole("heading", { name: "Status das cotações" })).toBeVisible();
    const secoes = within(painel)
      .getAllByRole("region")
      .map((s) => s.getAttribute("aria-label"));
    expect(secoes).toEqual(["Com erro", "Defasados", "Manuais", "Em dia"]);
    const defasados = within(painel).getByRole("region", { name: "Defasados" });
    // Ordem alfabética dentro do grupo; o FORA3 (sem posição) não aparece.
    expect(
      within(defasados)
        .getAllByRole("listitem")
        .map((l) => l.textContent),
    ).toEqual([expect.stringContaining("BOVA11"), expect.stringContaining("IVVB11")]);
    expect(within(painel).queryByText("FORA3")).not.toBeInTheDocument();
    expect(within(painel).getByText("Ticker não encontrado na fonte.")).toBeInTheDocument();
    expect(within(painel).getByText("Preço informado à mão.")).toBeInTheDocument();
    expect(limpo(within(painel).getByText(/38,45/).textContent)).toBe("R$ 38,45");
  });

  it("filtra por situação e busca por ticker ou nome (sem acento)", async () => {
    const { painel, usuario } = await abrirPainel();
    await usuario.click(within(painel).getByRole("button", { name: /Com erro 1/ }));
    expect(within(painel).getByRole("button", { name: /Com erro 1/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(painel).getAllByRole("listitem")).toHaveLength(1);
    expect(within(painel).getByText("MXRF11")).toBeInTheDocument();

    await usuario.click(within(painel).getByRole("button", { name: /Todos 5/ }));
    await usuario.type(within(painel).getByRole("searchbox", { name: "Buscar ativo" }), "petro");
    expect(within(painel).getAllByRole("listitem")).toHaveLength(1);
    expect(within(painel).getByText("PETR4")).toBeInTheDocument();

    await usuario.clear(within(painel).getByRole("searchbox"));
    await usuario.type(within(painel).getByRole("searchbox"), "xyz");
    expect(within(painel).getByText("Nenhum ativo encontrado.")).toBeInTheDocument();
  });

  it("os botões atualizam só os defasados ou só os com erro", async () => {
    const { painel, usuario, chamadas } = await abrirPainel({
      ...ROTAS_PAINEL,
      "POST /api/cotacoes/atualizar-ativos": { mensagem: "Atualização iniciada." },
    });
    await usuario.click(
      within(painel).getByRole("button", { name: "Atualizar valores defasados (2)" }),
    );
    await waitFor(() => {
      expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(1);
    });
    // Só os defasados com posição aberta (o FORA3 fica de fora).
    expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({ ativo_ids: [12, 13] });

    await usuario.click(
      within(painel).getByRole("button", { name: "Atualizar valores com erro (1)" }),
    );
    await waitFor(() => {
      expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(2);
    });
    expect(chamadas.filter((c) => c.metodo === "POST")[1]?.corpo).toEqual({ ativo_ids: [11] });
  });

  it("sem ativos na situação, avisa e não chama a API; 409 aparece no painel", async () => {
    const { painel, usuario, chamadas } = await abrirPainel({
      ...ROTAS_PAINEL,
      "GET /api/cotacoes/status": [status(10, "em_dia"), status(11, "defasado")],
      "GET /api/portfolio/posicoes": [posicao(10), posicao(11)],
      "POST /api/cotacoes/atualizar-ativos": {
        status: 409,
        corpo: {
          codigo: "atualizacao_em_andamento",
          mensagem: "Já existe uma atualização em andamento.",
        },
      },
    });
    await usuario.click(
      within(painel).getByRole("button", { name: "Atualizar valores com erro (0)" }),
    );
    expect(within(painel).getByRole("status")).toHaveTextContent("Nenhum ativo com erro.");
    expect(chamadas.some((c) => c.metodo === "POST")).toBe(false);

    await usuario.click(
      within(painel).getByRole("button", { name: "Atualizar valores defasados (1)" }),
    );
    expect(await within(painel).findByRole("alert")).toHaveTextContent(
      "Já existe uma atualização em andamento.",
    );
  });

  it("filtro de uma situação que esvaziou volta a Todos", async () => {
    let lista = [status(10, "em_dia"), status(11, "defasado", { simbolo: "IVVB11" })];
    const { painel, usuario, queryClient } = await abrirPainel({
      ...ROTAS_PAINEL,
      "GET /api/cotacoes/status": () => lista,
      "GET /api/portfolio/posicoes": [posicao(10), posicao(11)],
    });
    await usuario.click(within(painel).getByRole("button", { name: /Defasados 1/ }));
    expect(within(painel).getAllByRole("listitem")).toHaveLength(1);
    lista = [status(10, "em_dia"), status(11, "em_dia", { simbolo: "IVVB11" })];
    await queryClient.invalidateQueries({ queryKey: ["status-cotacoes"] });
    await waitFor(() => {
      expect(within(painel).getAllByRole("listitem")).toHaveLength(2);
    });
    expect(within(painel).getByRole("button", { name: /Todos 2/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("Esc fecha o painel e devolve o foco ao chip", async () => {
    const { usuario } = await abrirPainel();
    await usuario.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /^Cotações:/ })).toHaveFocus();
  });
});
