import { useEffect, useRef } from "react";
import type { ConexaoBackend } from "@/lib/backend";
import { useClienteApi } from "@/lib/cliente-api";

/**
 * Eventos em tempo real da atualização em segundo plano (SSE em `GET /api/eventos`).
 *
 * Por que `fetch` e não `EventSource`: o `EventSource` nativo não envia o header
 * `Authorization` (e o token não pode ir na URL). O `fetch` com `Authorization: Bearer`
 * lendo o corpo em streaming funciona com a CSP atual (`connect-src http://127.0.0.1:*`).
 *
 * Os valores chegam como texto (ex.: `"52.2"`); não faça aritmética em `number`.
 */
export type TipoEventoTempoReal =
  | "conectado"
  | "preco_atualizado"
  | "indicador_atualizado"
  | "erro_provider"
  | "fim_ciclo"
  | "lista_atualizada"
  | "erro_lista"
  | "heartbeat";

export interface EventoTempoReal {
  tipo: TipoEventoTempoReal | (string & {});
  dados: Record<string, unknown>;
}

export interface OpcoesEventos {
  fetchFn?: typeof fetch;
  /** Espera antes de reconectar após uma queda (dobra a cada falha). */
  esperaInicialMs?: number;
  esperaMaximaMs?: number;
  aoErro?: (erro: unknown) => void;
}

const ESPERA_INICIAL_MS = 1_000;
const ESPERA_MAXIMA_MS = 30_000;

function interpretarBloco(bloco: string): EventoTempoReal | null {
  let tipo = "message";
  const linhasDados: string[] = [];
  for (const linha of bloco.split("\n")) {
    if (linha.startsWith("event:")) tipo = linha.slice(6).trim();
    else if (linha.startsWith("data:")) linhasDados.push(linha.slice(5).trimStart());
  }
  if (linhasDados.length === 0 && tipo === "message") return null;
  const texto = linhasDados.join("\n");
  let dados: Record<string, unknown> = {};
  if (texto) {
    try {
      const valor: unknown = JSON.parse(texto);
      if (typeof valor === "object" && valor !== null) dados = valor as Record<string, unknown>;
    } catch {
      return null; // bloco malformado é ignorado; o stream continua
    }
  }
  return { tipo, dados };
}

/** Lê um corpo `text/event-stream` e devolve os eventos (blocos separados por linha em branco). */
export async function* lerEventosSse(
  corpo: ReadableStream<Uint8Array>,
): AsyncGenerator<EventoTempoReal> {
  const leitor = corpo.getReader();
  const decodificador = new TextDecoder();
  let acumulado = "";
  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      acumulado += decodificador.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let fim = acumulado.indexOf("\n\n");
      while (fim >= 0) {
        const evento = interpretarBloco(acumulado.slice(0, fim));
        acumulado = acumulado.slice(fim + 2);
        if (evento) yield evento;
        fim = acumulado.indexOf("\n\n");
      }
    }
  } finally {
    leitor.releaseLock();
  }
}

function esperar(ms: number, sinal: AbortSignal): Promise<void> {
  return new Promise((resolver) => {
    const temporizador = setTimeout(resolver, ms);
    sinal.addEventListener(
      "abort",
      () => {
        clearTimeout(temporizador);
        resolver();
      },
      { once: true },
    );
  });
}

/**
 * Conecta ao stream e chama `aoEvento` para cada evento. Reconecta sozinho com espera
 * crescente se a conexão cair (backend reiniciando, por exemplo). Devolve a função que
 * encerra a conexão.
 */
export function conectarEventos(
  conexao: ConexaoBackend,
  aoEvento: (evento: EventoTempoReal) => void,
  opcoes: OpcoesEventos = {},
): () => void {
  const {
    fetchFn = fetch,
    esperaInicialMs = ESPERA_INICIAL_MS,
    esperaMaximaMs = ESPERA_MAXIMA_MS,
    aoErro,
  } = opcoes;
  const controle = new AbortController();
  const { signal } = controle;
  const cancelado = () => signal.aborted;

  void (async () => {
    let espera = esperaInicialMs;
    while (!cancelado()) {
      try {
        const resposta = await fetchFn(`${conexao.urlBase}/api/eventos`, {
          headers: { Authorization: `Bearer ${conexao.token}`, Accept: "text/event-stream" },
          signal,
        });
        if (!resposta.ok || !resposta.body) {
          throw new Error(`O stream de eventos respondeu ${resposta.status}.`);
        }
        for await (const evento of lerEventosSse(resposta.body)) {
          espera = esperaInicialMs; // conexão saudável: zera a espera
          aoEvento(evento);
        }
      } catch (erro) {
        if (cancelado()) return;
        aoErro?.(erro);
      }
      await esperar(espera, signal);
      espera = Math.min(espera * 2, esperaMaximaMs);
    }
  })();

  return () => {
    controle.abort();
  };
}

/**
 * Hook de exemplo: assina os eventos enquanto o componente estiver montado.
 * Uso típico (Parte 4): invalidar as consultas de preços em `preco_atualizado`.
 */
export function useEventosTempoReal(
  aoEvento: (evento: EventoTempoReal) => void,
  opcoes?: OpcoesEventos,
): void {
  const { conexao } = useClienteApi();
  const callback = useRef(aoEvento);
  useEffect(() => {
    callback.current = aoEvento;
  });
  const fetchFn = opcoes?.fetchFn;

  useEffect(
    () =>
      conectarEventos(
        conexao,
        (evento) => {
          callback.current(evento);
        },
        { fetchFn },
      ),
    [conexao, fetchFn],
  );
}
