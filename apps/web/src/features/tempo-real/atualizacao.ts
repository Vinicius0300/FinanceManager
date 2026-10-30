import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { create } from "zustand";
import { useEventosTempoReal, type EventoTempoReal } from "@/lib/eventos";

/**
 * Consome o stream SSE da atualização em segundo plano e mantém a tela atual sem
 * recarregar: a cada preço/indicador gravado, as consultas que dependem de cotação são
 * marcadas como desatualizadas (o TanStack Query refaz só as visíveis).
 *
 * Vários eventos chegam em sequência num ciclo; as invalidações são agrupadas numa janela
 * curta para não refazer as consultas a cada ativo.
 */
export const JANELA_INVALIDACAO_MS = 800;

/** Primeiras partes das chaves de consulta que dependem de preços e indicadores. */
export const CONSULTAS_DE_COTACAO = [
  "portfolio",
  "status-cotacoes",
  "precos",
  "indicadores",
  "atualizacao",
  "historico",
  "contas",
] as const;

interface EstadoAtualizacao {
  ultimoFim: string | null;
  ultimosErros: number;
  ultimaMensagemErro: string | null;
  registrarEvento: (evento: EventoTempoReal) => void;
}

export const useEstadoAtualizacao = create<EstadoAtualizacao>()((set) => ({
  ultimoFim: null,
  ultimosErros: 0,
  ultimaMensagemErro: null,
  registrarEvento: (evento) => {
    const { dados } = evento;
    if (evento.tipo === "fim_ciclo") {
      set({
        ultimoFim: typeof dados.fim === "string" ? dados.fim : null,
        ultimosErros: typeof dados.erros === "number" ? dados.erros : 0,
      });
    } else if (evento.tipo === "erro_provider" && typeof dados.mensagem === "string") {
      set({ ultimaMensagemErro: dados.mensagem });
    }
  },
}));

const EVENTOS_QUE_INVALIDAM = new Set([
  "preco_atualizado",
  "indicador_atualizado",
  "erro_provider",
  "fim_ciclo",
]);

export function invalidarCotacoes(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (consulta) =>
      (CONSULTAS_DE_COTACAO as readonly string[]).includes(String(consulta.queryKey[0])),
  });
}

/** Liga o stream ao cache de consultas (montado uma vez, no layout). */
export function useAtualizacaoTempoReal(): void {
  const queryClient = useQueryClient();
  const registrar = useEstadoAtualizacao((s) => s.registrarEvento);
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (temporizador.current) clearTimeout(temporizador.current);
    },
    [],
  );

  useEventosTempoReal((evento) => {
    registrar(evento);
    if (!EVENTOS_QUE_INVALIDAM.has(evento.tipo)) return;
    if (temporizador.current) return;
    temporizador.current = setTimeout(() => {
      temporizador.current = null;
      void invalidarCotacoes(queryClient);
    }, JANELA_INVALIDACAO_MS);
  });
}
