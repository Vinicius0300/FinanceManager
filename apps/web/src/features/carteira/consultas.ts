import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { invalidarCotacoes } from "@/features/tempo-real/atualizacao";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import type { AtivoEntrada } from "./esquemaAtivo";

export type StatusAtivo = components["schemas"]["StatusAtivoSaida"];
export type Preco = components["schemas"]["PrecoSaida"];
export type AtivoEdicao = components["schemas"]["AtivoEdicao"];

const INTERVALO_DURANTE_ATUALIZACAO_MS = 2_000;

export function useStatusCotacoes() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["status-cotacoes"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/cotacoes/status", { signal })),
  });
}

/** Estado do ciclo de atualização; consultado com frequência enquanto um ciclo roda. */
export function useAtualizacao() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["atualizacao"],
    queryFn: async ({ signal }) =>
      exigir(await cliente.GET("/api/cotacoes/atualizacao", { signal })),
    refetchInterval: (consulta) =>
      consulta.state.data?.em_andamento ? INTERVALO_DURANTE_ATUALIZACAO_MS : false,
  });
}

/**
 * Atualização forçada: a API só agenda o ciclo e responde na hora (a interface não trava).
 * O progresso chega pelo SSE e pela consulta de `atualizacao`.
 */
export function useForcarAtualizacao() {
  const { cliente } = useClienteApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => exigir(await cliente.POST("/api/cotacoes/atualizar")),
    onSuccess: () => invalidarCotacoes(queryClient),
  });
}

export function usePrecos(ativoId: number, inicio: string) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["precos", ativoId, inicio],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/ativos/{ativo_id}/precos", {
          params: { path: { ativo_id: ativoId }, query: { inicio, limite: 500 } },
          signal,
        }),
      ),
  });
}

export function useCriarAtivo() {
  const { cliente } = useClienteApi();
  return useGravacao(async (corpo: AtivoEntrada) =>
    exigir(await cliente.POST("/api/ativos", { body: corpo })),
  );
}

export function useEditarAtivo() {
  const { cliente } = useClienteApi();
  return useGravacao(async ({ id, corpo }: { id: number; corpo: AtivoEdicao }) =>
    exigir(
      await cliente.PUT("/api/ativos/{ativo_id}", {
        params: { path: { ativo_id: id } },
        body: corpo,
      }),
    ),
  );
}

export function useExcluirAtivo() {
  const { cliente } = useClienteApi();
  return useGravacao(async (id: number) => {
    exigir(await cliente.DELETE("/api/ativos/{ativo_id}", { params: { path: { ativo_id: id } } }));
  });
}

export function useRegistrarPrecoManual() {
  const { cliente } = useClienteApi();
  return useGravacao(
    async ({ ativoId, data, valor }: { ativoId: number; data: string; valor: string }) =>
      exigir(
        await cliente.POST("/api/ativos/{ativo_id}/precos", {
          params: { path: { ativo_id: ativoId } },
          body: { data, valor },
        }),
      ),
  );
}

export function useExcluirPreco() {
  const { cliente } = useClienteApi();
  return useGravacao(async (id: number) => {
    exigir(await cliente.DELETE("/api/precos/{preco_id}", { params: { path: { preco_id: id } } }));
  });
}
