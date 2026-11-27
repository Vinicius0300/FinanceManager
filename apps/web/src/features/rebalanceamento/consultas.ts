import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";

export type Metas = components["schemas"]["MetasEsquema"];
export type Plano = components["schemas"]["PlanoSaida"];
export type ClassePlano = components["schemas"]["ClassePlanoSaida"];
export type AtivoPlano = components["schemas"]["AtivoPlanoSaida"];
export type ModoPlano = components["schemas"]["ModoPlano"];

/** Metas gravadas (classes, pesos por ativo e tolerância da banda). */
export function useMetas() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["rebalanceamento", "metas"],
    queryFn: async ({ signal }) =>
      exigir(await cliente.GET("/api/rebalanceamento/metas", { signal })),
  });
}

/**
 * Plano calculado no backend. `aporte` nulo = o caixa disponível (padrão da API). Mantém os
 * dados anteriores enquanto o novo plano chega, para a tela não piscar ao digitar.
 */
export function usePlano(aporte: string | null, modo: ModoPlano) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["rebalanceamento", "plano", aporte, modo],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/rebalanceamento/plano", {
          params: { query: { ...(aporte === null ? {} : { aporte }), modo } },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** Substitui todas as metas; no sucesso, todas as telas (e o cartão do Dashboard) recarregam. */
export function useGravarMetas() {
  const { cliente } = useClienteApi();
  return useGravacao(async (corpo: Metas) =>
    exigir(await cliente.PUT("/api/rebalanceamento/metas", { body: corpo })),
  );
}
