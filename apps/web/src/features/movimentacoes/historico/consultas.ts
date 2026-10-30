import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import type { CampoOrdem, ConsultaHistorico, Direcao } from "./filtros";

export type Operacao = components["schemas"]["TransacaoSaida"];
export type ResumoHistorico = components["schemas"]["ResumoHistoricoSaida"];
export type GrupoAtivo = components["schemas"]["GrupoAtivoSaida"];
export type Totais = components["schemas"]["TotaisHistoricoSaida"];

export const ITENS_POR_PAGINA = 50;

/** Página do histórico; `consulta === null` = nenhuma operação marcada (resultado vazio). */
export function useHistorico(
  consulta: ConsultaHistorico | null,
  ordem: CampoOrdem,
  direcao: Direcao,
  pagina: number,
) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["historico", "lista", consulta, ordem, direcao, pagina],
    enabled: consulta !== null,
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/transacoes", {
          params: {
            query: {
              ...consulta,
              ordem,
              direcao,
              limite: ITENS_POR_PAGINA,
              deslocamento: (pagina - 1) * ITENS_POR_PAGINA,
            },
          },
          signal,
        }),
      ),
  });
}

export function useResumoHistorico(consulta: ConsultaHistorico | null) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["historico", "resumo", consulta],
    enabled: consulta !== null,
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/transacoes/resumo", { params: { query: { ...consulta } }, signal }),
      ),
  });
}

/** Grava a planilha no caminho escolhido no diálogo nativo (todos os filtros, todas as páginas). */
export function useExportarHistorico() {
  const { cliente } = useClienteApi();
  return useMutation({
    mutationFn: async ({
      consulta,
      ordem,
      direcao,
      caminho,
    }: {
      consulta: ConsultaHistorico;
      ordem: CampoOrdem;
      direcao: Direcao;
      caminho: string;
    }) =>
      exigir(
        await cliente.POST("/api/transacoes/exportar", {
          params: { query: { ...consulta, ordem, direcao } },
          body: { caminho },
        }),
      ),
  });
}

export function useExcluirTransacao() {
  const { cliente } = useClienteApi();
  return useGravacao(async (id: number) => {
    exigir(
      await cliente.DELETE("/api/transacoes/{transacao_id}", {
        params: { path: { transacao_id: id } },
      }),
    );
  });
}
