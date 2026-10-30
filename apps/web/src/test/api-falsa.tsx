import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";
import { criarClienteApi, type ConexaoBackend } from "@/lib/backend";
import { ContextoClienteApi } from "@/lib/cliente-api";
import tiposAtivo from "./dados/tipos-ativo.json";

/**
 * API falsa para testes de tela: responde pelas rotas do backend (sem rede), confere o
 * token e registra cada chamada (método, caminho, query e corpo) para as asserções.
 */
export const CONEXAO: ConexaoBackend = { urlBase: "http://127.0.0.1:50000", token: "t".repeat(64) };

export interface Chamada {
  metodo: string;
  caminho: string;
  query: URLSearchParams;
  corpo: unknown;
}

export type Resposta = unknown;
export type Manipulador = (chamada: Chamada) => Resposta;
export type Rotas = Record<string, Manipulador | object | null>;

export const TIPOS_ATIVO = tiposAtivo;

/** Respostas padrão para os cadastros usados em quase todas as telas. */
export const ROTAS_BASE: Rotas = {
  "GET /api/tipos-ativo": tiposAtivo,
  "GET /api/instituicoes": [
    { id: 1, nome: "XP", tipo: "corretora", criado_em: "2026-01-01T00:00:00Z" },
    { id: 2, nome: "RICO", tipo: "corretora", criado_em: "2026-01-01T00:00:00Z" },
  ],
  "GET /api/ativos": [
    ativo({ id: 10, tipo: "acao_br", simbolo: "PETR4", nome: "Petrobras PN" }),
    ativo({ id: 11, tipo: "acao_us", simbolo: "AAPL", nome: "Apple", moeda: "USD" }),
    ativo({ id: 12, tipo: "renda_fixa", simbolo: null, nome: "CDB Banco X", provider: null }),
  ],
};

export function ativo(dados: {
  id: number;
  tipo: string;
  nome: string;
  simbolo: string | null;
  moeda?: string;
  provider?: string | null;
  metadados?: Record<string, string | number>;
}) {
  return {
    moeda: "BRL",
    provider: "yfinance",
    simbolo_externo: null,
    metadados: {},
    criado_em: "2026-01-01T00:00:00Z",
    ...dados,
  };
}

function json(corpo: unknown, status: number): Response {
  if (status === 204) return new Response(null, { status });
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Caminho com ids trocados por {id} também é aceito como chave ("DELETE /api/ativos/{id}"). */
function normalizar(caminho: string): string {
  return caminho.replace(/\/\d+(?=\/|$)/g, "/{id}");
}

export function criarFetchFalso(rotas: Rotas) {
  const chamadas: Chamada[] = [];
  const fetchFn = vi.fn(async (recurso: RequestInfo | URL, init?: RequestInit) => {
    const pedido = recurso instanceof Request ? recurso : new Request(recurso, init);
    const url = new URL(pedido.url);
    if (pedido.headers.get("Authorization") !== `Bearer ${CONEXAO.token}`) {
      return json({ codigo: "nao_autorizado", mensagem: "Token inválido." }, 401);
    }
    const texto = pedido.method === "GET" ? "" : await pedido.text();
    const chamada: Chamada = {
      metodo: pedido.method,
      caminho: url.pathname,
      query: url.searchParams,
      corpo: texto ? (JSON.parse(texto) as unknown) : undefined,
    };
    chamadas.push(chamada);
    const chave = `${pedido.method} ${url.pathname}`;
    const manipulador = rotas[chave] ?? rotas[`${pedido.method} ${normalizar(url.pathname)}`];
    if (manipulador === undefined) {
      return json({ codigo: "http_404", mensagem: `Rota sem resposta no teste: ${chave}` }, 404);
    }
    const resposta: Resposta =
      typeof manipulador === "function" ? (manipulador as Manipulador)(chamada) : manipulador;
    if (resposta instanceof Response) return resposta; // ex.: stream SSE
    if (resposta && typeof resposta === "object" && "status" in resposta) {
      const r = resposta as { status: number; corpo?: unknown };
      return json(r.corpo ?? null, r.status);
    }
    return json(resposta, pedido.method === "DELETE" ? 204 : 200);
  });
  return { fetchFn, chamadas };
}

/** Mostra a URL atual (para conferir filtros gravados na query string). */
function UrlAtual() {
  const local = useLocation();
  return <div data-testid="url-atual">{`${local.pathname}${local.search}`}</div>;
}

export function renderizar(
  ui: ReactElement,
  opcoes: { rotas?: Rotas; url?: string; caminho?: string } = {},
) {
  const { fetchFn, chamadas } = criarFetchFalso({ ...ROTAS_BASE, ...opcoes.rotas });
  const cliente = criarClienteApi(CONEXAO, fetchFn);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  const usuario = userEvent.setup();
  const resultado = render(
    <QueryClientProvider client={queryClient}>
      <ContextoClienteApi.Provider value={{ cliente, conexao: CONEXAO }}>
        <MemoryRouter initialEntries={[opcoes.url ?? "/"]}>
          <Routes>
            <Route
              path={opcoes.caminho ?? "*"}
              element={
                <>
                  {ui}
                  <UrlAtual />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </ContextoClienteApi.Provider>
    </QueryClientProvider>,
  );
  return { ...resultado, chamadas, fetchFn, queryClient, usuario };
}
