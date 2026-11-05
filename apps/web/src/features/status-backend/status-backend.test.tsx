import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as backend from "@/lib/backend";
import { ContextoClienteApi, useClienteApi } from "@/lib/cliente-api";
import { formatarDataHora } from "@/lib/formatacao";
import { PortaoBackend } from "./PortaoBackend";
import { TelaStatusBackend } from "./TelaStatusBackend";

vi.mock("@/lib/backend", async (importOriginal) => {
  const original = await importOriginal<typeof backend>();
  return {
    ...original,
    obterConexaoBackend: vi.fn(),
    reiniciarBackend: vi.fn(),
    obterVersaoApp: vi.fn(() => Promise.resolve("1.0.0")),
  };
});

const CONEXAO = { urlBase: "http://127.0.0.1:50000", token: "t".repeat(64) };
const HORARIO = "2026-10-28T15:30:00Z";

function comQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function json(corpo: unknown, status = 200) {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** fetch falso que responde pelas rotas do backend e confere o token. */
function fetchFalso(opcoes: { pingStatus?: number; versao?: string } = {}) {
  return vi.fn((recurso: RequestInfo | URL) => {
    const entrada = recurso instanceof Request ? recurso : new Request(recurso);
    const url = new URL(entrada.url);
    if (url.pathname === "/health") {
      return Promise.resolve(json({ status: "ok", versao: opcoes.versao ?? "1.0.0" }));
    }
    if (url.pathname === "/api/ping") {
      const autorizado = entrada.headers.get("Authorization") === `Bearer ${CONEXAO.token}`;
      if (!autorizado || opcoes.pingStatus === 401) {
        return Promise.resolve(
          json({ codigo: "nao_autorizado", mensagem: "Token de sessão ausente ou inválido." }, 401),
        );
      }
      return Promise.resolve(json({ mensagem: "pong", horario: HORARIO, versao: "0.1.0" }));
    }
    return Promise.resolve(json({ codigo: "http_404", mensagem: "Recurso não encontrado." }, 404));
  });
}

function renderTela(fetchFn: typeof fetch) {
  const cliente = backend.criarClienteApi(CONEXAO, fetchFn);
  return render(
    comQuery(
      <ContextoClienteApi.Provider value={{ cliente, conexao: CONEXAO }}>
        <TelaStatusBackend />
      </ContextoClienteApi.Provider>,
    ),
  );
}

describe("PortaoBackend", () => {
  beforeEach(() => {
    vi.mocked(backend.obterConexaoBackend).mockReset();
    vi.mocked(backend.reiniciarBackend).mockReset();
  });

  it("mostra carregamento enquanto o backend inicia", () => {
    vi.mocked(backend.obterConexaoBackend).mockReturnValue(new Promise(() => undefined));
    render(comQuery(<PortaoBackend>conteúdo</PortaoBackend>));
    expect(screen.getByRole("status")).toHaveTextContent("Iniciando o serviço interno");
    expect(screen.queryByText("conteúdo")).not.toBeInTheDocument();
  });

  it("libera a UI quando o backend responde", async () => {
    vi.mocked(backend.obterConexaoBackend).mockResolvedValue(CONEXAO);
    render(comQuery(<PortaoBackend>conteúdo liberado</PortaoBackend>));
    expect(await screen.findByText("conteúdo liberado")).toBeInTheDocument();
  });

  it("mostra erro claro e permite tentar novamente", async () => {
    vi.mocked(backend.obterConexaoBackend)
      .mockRejectedValueOnce(new Error("O serviço interno não respondeu em 30 segundos."))
      .mockResolvedValueOnce(CONEXAO);
    vi.mocked(backend.reiniciarBackend).mockResolvedValue(undefined);

    render(comQuery(<PortaoBackend>conteúdo liberado</PortaoBackend>));
    expect(await screen.findByRole("alert")).toHaveTextContent("não respondeu em 30 segundos");

    await userEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(backend.reiniciarBackend).toHaveBeenCalledOnce();
    expect(await screen.findByText("conteúdo liberado")).toBeInTheDocument();
  });
});

describe("useReiniciarBackend", () => {
  beforeEach(() => {
    vi.mocked(backend.obterConexaoBackend).mockReset();
    vi.mocked(backend.reiniciarBackend).mockReset();
  });

  it("limpa todas as consultas (porta e token mudam) e usa a conexão nova", async () => {
    const NOVA = { urlBase: "http://127.0.0.1:50001", token: "n".repeat(64) };
    vi.mocked(backend.obterConexaoBackend)
      .mockRejectedValueOnce(new Error("O serviço interno parou."))
      .mockResolvedValueOnce(NOVA);
    vi.mocked(backend.reiniciarBackend).mockResolvedValue(undefined);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // Dados de consultas feitas com o backend anterior.
    client.setQueryData(["portfolio", "posicoes"], [{ ativo_id: 1 }]);
    client.setQueryData(["health"], { status: "ok", versao: "0.1.0" });

    function MostraConexao() {
      return <p>{useClienteApi().conexao.urlBase}</p>;
    }
    render(
      <QueryClientProvider client={client}>
        <PortaoBackend>
          <MostraConexao />
        </PortaoBackend>
      </QueryClientProvider>,
    );
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));

    expect(await screen.findByText(NOVA.urlBase)).toBeInTheDocument();
    expect(client.getQueryData(["portfolio", "posicoes"])).toBeUndefined();
    expect(client.getQueryData(["health"])).toBeUndefined();
  });
});

describe("TelaStatusBackend", () => {
  it("mostra backend conectado e a resposta da rota protegida", async () => {
    const fetchFn = fetchFalso();
    renderTela(fetchFn);

    expect(await screen.findByText("Conectado")).toBeInTheDocument();
    expect(await screen.findByText("pong")).toBeInTheDocument();
    expect(screen.getByText(formatarDataHora(HORARIO))).toBeInTheDocument();
    expect(screen.getByText(CONEXAO.urlBase)).toBeInTheDocument();
    // O token nunca aparece na tela.
    expect(screen.queryByText(CONEXAO.token)).not.toBeInTheDocument();
  });

  it("mostra a mensagem em pt-BR quando o token é recusado", async () => {
    renderTela(fetchFalso({ pingStatus: 401 }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Token de sessão ausente ou inválido.",
    );
  });

  it("Sobre mostra a versão do app e a do serviço interno, sem aviso quando batem", async () => {
    renderTela(fetchFalso());
    await waitFor(() => {
      expect(screen.getByText("Versão do app").nextElementSibling).toHaveTextContent("1.0.0");
    });
    await waitFor(() => {
      expect(screen.getByText("Versão do serviço interno").nextElementSibling).toHaveTextContent(
        "1.0.0",
      );
    });
    expect(screen.queryByText(/são diferentes/)).not.toBeInTheDocument();
  });

  it("Sobre avisa quando as versões do app e do serviço interno divergem", async () => {
    renderTela(fetchFalso({ versao: "0.9.0" }));
    expect(await screen.findByText(/são diferentes/)).toHaveTextContent(
      "As versões do app (1.0.0) e do serviço interno (0.9.0) são diferentes.",
    );
  });

  it("Sobre mostra traço fora do app (sem Tauri)", async () => {
    vi.mocked(backend.obterVersaoApp).mockResolvedValueOnce(null);
    renderTela(fetchFalso());
    await waitFor(() => {
      expect(screen.getByText("Versão do app").nextElementSibling).toHaveTextContent("—");
    });
    expect(screen.queryByText(/são diferentes/)).not.toBeInTheDocument();
  });

  it("mostra indisponível quando a rede falha", async () => {
    const fetchFn = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    renderTela(fetchFn);
    await waitFor(
      () => {
        expect(screen.getByText("Indisponível")).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
      "Não foi possível conectar ao serviço interno",
    );
  });
});
