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
export type Posicao = components["schemas"]["PosicaoSaida"];

/** Operações por vez no painel de uma instituição (visão Por ativo). */
export const ITENS_PAINEL = 100;

/** Página do histórico; `consulta === null` = nenhuma operação marcada (resultado vazio). */
export function useHistorico(
  consulta: ConsultaHistorico | null,
  ordem: CampoOrdem,
  direcao: Direcao,
  pagina: number,
  tamanho: number,
) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["historico", "lista", consulta, ordem, direcao, pagina, tamanho],
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
              limite: tamanho,
              deslocamento: (pagina - 1) * tamanho,
            },
          },
          signal,
        }),
      ),
  });
}

/**
 * Operações de um ativo numa instituição, com os filtros do topo, da mais antiga para a
 * mais recente (painel da visão Por ativo). Só consulta com o painel aberto.
 */
export function useOperacoesDaInstituicao(
  consulta: ConsultaHistorico,
  ativoId: number,
  instituicaoId: number,
  pagina: number,
) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["historico", "instituicao", consulta, ativoId, instituicaoId, pagina],
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/transacoes", {
          params: {
            query: {
              ...consulta,
              ativo_id: ativoId,
              instituicao_id: instituicaoId,
              ordem: "data",
              direcao: "asc",
              limite: ITENS_PAINEL,
              deslocamento: (pagina - 1) * ITENS_PAINEL,
            },
          },
          signal,
        }),
      ),
  });
}

/**
 * Data da última operação do painel quando ela não está na página aberta (mais de
 * `ITENS_PAINEL` operações): uma consulta de 1 item em ordem decrescente.
 */
export function useUltimaOperacao(
  consulta: ConsultaHistorico,
  ativoId: number,
  instituicaoId: number,
  habilitada: boolean,
) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["historico", "instituicao-ultima", consulta, ativoId, instituicaoId],
    enabled: habilitada,
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/transacoes", {
          params: {
            query: {
              ...consulta,
              ativo_id: ativoId,
              instituicao_id: instituicaoId,
              ordem: "data",
              direcao: "desc",
              limite: 1,
            },
          },
          signal,
        }),
      ),
  });
}

/** Posições abertas de hoje numa instituição (mesma chave da Carteira: o cache é dividido). */
export function usePosicoesDaInstituicao(instituicaoId: number) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["portfolio", "posicoes", instituicaoId],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/portfolio/posicoes", {
          params: { query: { instituicao_id: instituicaoId } },
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
