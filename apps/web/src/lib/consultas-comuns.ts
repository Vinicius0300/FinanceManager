import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { create } from "zustand";
import type { components } from "@/api/schema";
import { exigir, invalidarDados } from "./api";
import { useClienteApi } from "./cliente-api";

export type Instituicao = components["schemas"]["InstituicaoSaida"];
export type Ativo = components["schemas"]["AtivoSaida"];
export type TipoAtivo = components["schemas"]["TipoAtivoSaida"];

/** Cadastros usados por várias telas (filtros, formulários, rótulos). */
export function useInstituicoes() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["instituicoes"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/instituicoes", { signal })),
  });
}

export function useAtivos() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["ativos"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/ativos", { signal })),
  });
}

/** Tipos de ativo do registry (campos do formulário gerado, moedas, operações aceitas). */
export function useTiposAtivo() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["tipos-ativo"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/tipos-ativo", { signal })),
    staleTime: Infinity,
  });
}

/** Mapas id → registro para montar rótulos nas tabelas. */
export function indexarPorId<T extends { id: number }>(
  itens: readonly T[] | undefined,
): Map<number, T> {
  return new Map((itens ?? []).map((item) => [item.id, item]));
}

export function nomeDoTipo(tipos: readonly TipoAtivo[] | undefined, slug: string): string {
  return tipos?.find((t) => t.slug === slug)?.nome ?? slug;
}

/** Rótulo curto de um ativo: símbolo (ou nome, para renda fixa e poupança). */
export function rotuloAtivo(ativo: Pick<Ativo, "simbolo" | "nome"> | undefined): string {
  if (!ativo) return "—";
  return ativo.simbolo ?? ativo.nome;
}

/**
 * Mutação padrão do app: chama a API, e no sucesso invalida os dados de todas as telas
 * (a interface continua respondendo; só as consultas visíveis são refeitas).
 */
export function useGravacao<E, S>(executar: (entrada: E) => Promise<S>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: executar,
    onSuccess: () => invalidarDados(queryClient),
  });
}

/** Seletor "Análise Geral / por Instituição" (compartilhado entre Dashboard e Carteira). */
interface EstadoAnalise {
  instituicaoId: number | null;
  definirInstituicao: (id: number | null) => void;
}

export const useAnaliseStore = create<EstadoAnalise>()((set) => ({
  instituicaoId: null,
  definirInstituicao: (instituicaoId) => {
    set({ instituicaoId });
  },
}));

/** Instituição escolhida no seletor, ignorando uma que tenha sido excluída. */
export function useInstituicaoAnalise(): number | null {
  const instituicoes = useInstituicoes();
  const instituicaoId = useAnaliseStore((s) => s.instituicaoId);
  if (instituicaoId === null) return null;
  return instituicoes.data?.some((i) => i.id === instituicaoId) ? instituicaoId : null;
}
