import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";

export type ResumoPortfolio = components["schemas"]["ResumoSaida"];
export type Fatia = components["schemas"]["FatiaSaida"];
export type Posicao = components["schemas"]["PosicaoSaida"];
export type Evolucao = components["schemas"]["EvolucaoSaida"];
export type ResumoMensal = components["schemas"]["ResumoMensalSaida"];

/** `instituicao_id` só vai na consulta na análise por instituição. */
function filtroInstituicao(instituicaoId: number | null) {
  return instituicaoId === null ? {} : { instituicao_id: instituicaoId };
}

export function useResumoPortfolio(instituicaoId: number | null) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["portfolio", "resumo", instituicaoId],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/portfolio/resumo", {
          params: { query: filtroInstituicao(instituicaoId) },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useAlocacao(instituicaoId: number | null) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["portfolio", "alocacao", instituicaoId],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/portfolio/alocacao", {
          params: { query: filtroInstituicao(instituicaoId) },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useMaiores(instituicaoId: number | null, limite = 5) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["portfolio", "maiores", instituicaoId, limite],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/portfolio/maiores", {
          params: { query: { ...filtroInstituicao(instituicaoId), limite } },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function usePosicoes(instituicaoId: number | null) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["portfolio", "posicoes", instituicaoId],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/portfolio/posicoes", {
          params: { query: filtroInstituicao(instituicaoId) },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useEvolucao(instituicaoId: number | null, inicio: string) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["portfolio", "evolucao", instituicaoId, inicio],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/portfolio/evolucao", {
          params: { query: { ...filtroInstituicao(instituicaoId), inicio } },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useResumoMensal(ano: number, mes: number) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["resumo-mensal", ano, mes],
    queryFn: async ({ signal }) =>
      exigir(await cliente.GET("/api/resumo-mensal", { params: { query: { ano, mes } }, signal })),
    placeholderData: keepPreviousData,
  });
}
