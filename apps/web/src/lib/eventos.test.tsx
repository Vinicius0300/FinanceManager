import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConexaoBackend } from "./backend";
import { ContextoClienteApi } from "./cliente-api";
import { criarClienteApi } from "./backend";
import {
  conectarEventos,
  lerEventosSse,
  useEventosTempoReal,
  type EventoTempoReal,
} from "./eventos";

const CONEXAO: ConexaoBackend = { urlBase: "http://127.0.0.1:5000", token: "t".repeat(64) };

/** Corpo SSE entregue em pedaços (como a rede faz). */
function corpo(pedacos: string[]): ReadableStream<Uint8Array> {
  const codificador = new TextEncoder();
  return new ReadableStream({
    start(controle) {
      for (const pedaco of pedacos) controle.enqueue(codificador.encode(pedaco));
      controle.close();
    },
  });
}

async function coletar(stream: ReadableStream<Uint8Array>): Promise<EventoTempoReal[]> {
  const eventos: EventoTempoReal[] = [];
  for await (const evento of lerEventosSse(stream)) eventos.push(evento);
  return eventos;
}

describe("lerEventosSse", () => {
  it("junta pedaços e separa os eventos", async () => {
    const eventos = await coletar(
      corpo([
        "event: conectado\ndata: {}\n\nevent: preco_at",
        'ualizado\ndata: {"ativo_id":1,"valor":"52.2"}\n',
        "\nevent: heartbeat\r\ndata: {}\r\n\r\n",
      ]),
    );
    expect(eventos).toEqual([
      { tipo: "conectado", dados: {} },
      { tipo: "preco_atualizado", dados: { ativo_id: 1, valor: "52.2" } },
      { tipo: "heartbeat", dados: {} },
    ]);
  });

  it("ignora blocos malformados ou vazios", async () => {
    const eventos = await coletar(
      corpo([": comentário\n\nevent: x\ndata: {quebrado\n\nevent: fim_ciclo\ndata: {}\n\n"]),
    );
    expect(eventos).toEqual([{ tipo: "fim_ciclo", dados: {} }]);
  });
});

describe("conectarEventos", () => {
  it("envia o token e reconecta depois de uma queda", async () => {
    const chamadas: RequestInit[] = [];
    const fetchFalso = vi.fn((_url: string | URL | Request, init?: RequestInit) => {
      chamadas.push(init ?? {});
      if (chamadas.length === 1) return Promise.reject(new TypeError("Failed to fetch"));
      return Promise.resolve(
        new Response(corpo(['event: fim_ciclo\ndata: {"erros":0}\n\n']), { status: 200 }),
      );
    });
    const recebidos: EventoTempoReal[] = [];
    const erros: unknown[] = [];
    const parar = conectarEventos(
      CONEXAO,
      (e) => {
        recebidos.push(e);
      },
      {
        fetchFn: fetchFalso,
        esperaInicialMs: 1,
        aoErro: (erro) => {
          erros.push(erro);
        },
      },
    );
    // O stream falso fecha logo: o cliente reconecta e recebe o evento de novo (esperado).
    await waitFor(() => {
      expect(recebidos[0]).toEqual({ tipo: "fim_ciclo", dados: { erros: 0 } });
    });
    parar();
    expect(fetchFalso.mock.calls[0]?.[0]).toBe("http://127.0.0.1:5000/api/eventos");
    expect(chamadas[0]?.headers).toMatchObject({ Authorization: `Bearer ${CONEXAO.token}` });
    expect(erros).toHaveLength(1);
  });

  it("trata resposta de erro (ex.: 401) como queda", async () => {
    const fetchFalso = vi.fn(() => Promise.resolve(new Response("{}", { status: 401 })));
    const erros: unknown[] = [];
    const parar = conectarEventos(CONEXAO, () => undefined, {
      fetchFn: fetchFalso,
      esperaInicialMs: 50,
      aoErro: (erro) => {
        erros.push(erro);
      },
    });
    await waitFor(() => {
      expect(erros).toHaveLength(1);
    });
    parar();
    expect(String(erros[0])).toMatch(/respondeu 401/);
  });
});

describe("useEventosTempoReal", () => {
  it("assina enquanto o componente está montado", async () => {
    const fetchFalso = vi.fn(() =>
      Promise.resolve(
        new Response(corpo(['event: preco_atualizado\ndata: {"ativo_id":3}\n\n']), {
          status: 200,
        }),
      ),
    );
    const recebidos: EventoTempoReal[] = [];

    function Exemplo() {
      useEventosTempoReal(
        (evento) => {
          recebidos.push(evento);
        },
        {
          fetchFn: fetchFalso,
        },
      );
      return null;
    }

    const { unmount } = render(
      <ContextoClienteApi.Provider value={{ cliente: criarClienteApi(CONEXAO), conexao: CONEXAO }}>
        <Exemplo />
      </ContextoClienteApi.Provider>,
    );
    await waitFor(() => {
      expect(recebidos[0]).toEqual({ tipo: "preco_atualizado", dados: { ativo_id: 3 } });
    });
    unmount();
  });
});
