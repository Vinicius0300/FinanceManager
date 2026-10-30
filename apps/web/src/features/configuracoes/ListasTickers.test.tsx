import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderizar } from "@/test/api-falsa";
import { SecaoListasTickers } from "./ListasTickers";

const LISTAS = {
  em_andamento: false,
  listas: [
    {
      bolsa: "B3",
      quantidade: 2916,
      atualizado_em: "2026-10-30T15:00:00Z",
      ultima_tentativa: "2026-10-30T15:00:00Z",
      status_arquivo: "Parcial",
      data_arquivo: "2026-10-30",
      ultimo_erro: null,
    },
    {
      bolsa: "EUA",
      quantidade: 0,
      atualizado_em: null,
      ultima_tentativa: "2026-10-30T15:00:00Z",
      status_arquivo: null,
      data_arquivo: null,
      ultimo_erro: "NASDAQ (diretório de símbolos) indisponível no momento.",
    },
  ],
};

describe("Configurações > Lista de tickers", () => {
  it("mostra a situação de cada bolsa, inclusive a falha", async () => {
    renderizar(<SecaoListasTickers />, { rotas: { "GET /api/simbolos/listas": LISTAS } });
    expect(await screen.findByText(/2\.916 papéis · atualizada em/)).toHaveTextContent(
      "arquivo de 30/10/2026 (parcial)",
    );
    expect(screen.getByText("Ainda não baixada.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Última tentativa falhou: NASDAQ (diretório de símbolos) indisponível no momento.",
    );
  });

  it("Atualizar lista pede a importação em segundo plano", async () => {
    const { usuario, chamadas } = renderizar(<SecaoListasTickers />, {
      rotas: {
        "GET /api/simbolos/listas": LISTAS,
        "POST /api/simbolos/atualizar": {
          status: 202,
          corpo: { mensagem: "Atualização da lista iniciada. O resultado chega pelos eventos." },
        },
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Atualizar lista" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Atualização da lista iniciada");
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(1);
  });

  it("durante a importação o botão fica ocupado; 409 vira mensagem", async () => {
    const { usuario } = renderizar(<SecaoListasTickers />, {
      rotas: {
        "GET /api/simbolos/listas": { ...LISTAS, em_andamento: true },
      },
    });
    expect(await screen.findByRole("button", { name: "Atualizando…" })).toBeDisabled();
    const ocupado = renderizar(<SecaoListasTickers />, {
      rotas: {
        "GET /api/simbolos/listas": LISTAS,
        "POST /api/simbolos/atualizar": {
          status: 409,
          corpo: {
            codigo: "atualizacao_em_andamento",
            mensagem: "A lista de tickers já está sendo atualizada.",
          },
        },
      },
    });
    const botoes = await screen.findAllByRole("button", { name: "Atualizar lista" });
    await ocupado.usuario.click(botoes[0] as HTMLElement);
    await waitFor(() => {
      expect(screen.getByText("A lista de tickers já está sendo atualizada.")).toBeInTheDocument();
    });
    expect(usuario).toBeDefined();
  });

  it("erro ao carregar a situação mostra o estado de erro", async () => {
    renderizar(<SecaoListasTickers />, {
      rotas: {
        "GET /api/simbolos/listas": {
          status: 500,
          corpo: { codigo: "erro_interno", mensagem: "Erro inesperado no serviço interno." },
        },
      },
    });
    expect(await screen.findByText("Erro inesperado no serviço interno.")).toBeInTheDocument();
  });
});
