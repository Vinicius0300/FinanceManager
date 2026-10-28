import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FalhaApi, obterConexaoBackend, reiniciarBackend } from "@/lib/backend";
import { useClienteApi } from "@/lib/cliente-api";

export const CHAVE_CONEXAO = ["conexao-backend"] as const;
const INTERVALO_HEALTH_MS = 10_000;

/** Espera o backend ficar pronto (Tauri faz o /health com timeout). */
export function useConexaoBackend() {
  return useQuery({
    queryKey: CHAVE_CONEXAO,
    queryFn: obterConexaoBackend,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/** Reinicia o processo do backend e volta a aguardar a conexão. */
export function useReiniciarBackend() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: reiniciarBackend,
    onSettled: () => queryClient.resetQueries({ queryKey: CHAVE_CONEXAO }),
  });
}

/** Monitora o backend periodicamente depois que a UI foi liberada. */
export function useHealth() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["health"],
    queryFn: async ({ signal }) => {
      const { data } = await cliente.GET("/health", { signal });
      if (!data) throw new Error("O serviço interno não respondeu corretamente.");
      return data;
    },
    refetchInterval: INTERVALO_HEALTH_MS,
    retry: 1,
  });
}

/** Chama a rota protegida de exemplo (exige o token de sessão). */
export function usePing() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["ping"],
    queryFn: async ({ signal }) => {
      const { data, error } = await cliente.GET("/api/ping", { signal });
      if (error) throw new FalhaApi(error);
      return data;
    },
    retry: false,
  });
}
