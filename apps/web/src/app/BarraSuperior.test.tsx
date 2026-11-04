import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderizar } from "@/test/api-falsa";
import { BarraSuperior } from "./BarraSuperior";
import { contarStatus, textoStatus } from "./status-cotacoes";

const limpo = (t: string | null) => (t ?? "").replace(/00a0/g, " ");

function status(ativo_id: number, defasado: boolean, ultimo_erro: string | null = null) {
  return {
    ativo_id,
    nome: `Ativo ${ativo_id}`,
    tipo: "acao_br",
    valor: "10",
    data: "2026-10-29",
    data_hora: null,
    origem: "automatico",
    provider_preco: "yfinance",
    provider: "yfinance",
    ultima_tentativa: null,
    ultimo_sucesso: null,
    ultimo_erro,
    defasado,
    aviso: null,
  };
}

const posicao = (ativo_id: number) => ({ ativo_id, nome: `Ativo ${ativo_id}` });

describe("contagem do chip de status", () => {
  it("prioridade erro > defasado > em dia e só posições abertas", () => {
    const contagem = contarStatus(
      [
        status(1, false),
        status(2, false),
        status(3, true),
        status(4, true, "HTTP 503"), // defasado e com erro: conta só como erro
        status(5, false, "Ticker não encontrado."),
        status(6, true), // sem posição aberta: fica de fora
      ],
      new Set([1, 2, 3, 4, 5]),
    );
    expect(contagem).toEqual({ emDia: 2, defasadas: 1, comErro: 2 });
    expect(textoStatus(contagem)).toBe("2 em dia · 1 defasada · 2 com erro");
  });

  it("omite as categorias zeradas; tudo zero mostra 0 em dia", () => {
    expect(textoStatus({ emDia: 14, defasadas: 0, comErro: 0 })).toBe("14 em dia");
    expect(textoStatus({ emDia: 0, defasadas: 3, comErro: 0 })).toBe("3 defasadas");
    expect(textoStatus({ emDia: 0, defasadas: 0, comErro: 0 })).toBe("0 em dia");
  });
});

const ROTAS = {
  "GET /api/cotacoes/status": [
    status(10, false),
    status(11, true, "Yahoo indisponível."),
    status(12, true),
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
    const chip = await screen.findByRole("status", { name: "Cotações: 1 em dia · 1 com erro" });
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
    expect(screen.queryByRole("status", { name: /Cotações:/ })).not.toBeInTheDocument();
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
});
