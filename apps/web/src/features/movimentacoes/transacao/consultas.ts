import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { components } from "@/api/schema";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import type { MovimentacaoEntrada, TransacaoEntrada } from "./esquema";

export type ItemBusca = components["schemas"]["ItemBuscaSaida"];
export type ResultadoBusca = components["schemas"]["BuscaSimbolosSaida"];
export type Posicao = components["schemas"]["PosicaoSaida"];

export const ESPERA_BUSCA_MS = 300;

/** Substitui (PUT) uma transação existente (o ativo não muda na edição). */
export function useEditarTransacao() {
  const { cliente } = useClienteApi();
  return useGravacao(async ({ id, corpo }: { id: number; corpo: TransacaoEntrada }) =>
    exigir(
      await cliente.PUT("/api/transacoes/{transacao_id}", {
        params: { path: { transacao_id: id } },
        body: corpo,
      }),
    ),
  );
}

/** Movimentação nova: escolhe ou cria o ativo junto com a transação (atômico na API). */
export function useRegistrarMovimentacao() {
  const { cliente } = useClienteApi();
  return useGravacao(async (corpo: MovimentacaoEntrada) =>
    exigir(await cliente.POST("/api/movimentacoes", { body: corpo })),
  );
}

/** Texto com espera: só muda depois que o usuário para de digitar. */
export function useTextoComEspera(texto: string, espera = ESPERA_BUSCA_MS): string {
  const [atrasado, setAtrasado] = useState(texto);
  useEffect(() => {
    const temporizador = setTimeout(() => {
      setAtrasado(texto);
    }, espera);
    return () => {
      clearTimeout(temporizador);
    };
  }, [texto, espera]);
  return atrasado;
}

/**
 * Busca do cadastro: carteira + lista oficial da bolsa + pesquisa externa. A chave começa
 * por "simbolos" para o evento `lista_atualizada` refazer a busca visível.
 */
export function useBuscaSimbolos(tipo: string, texto: string) {
  const { cliente } = useClienteApi();
  const termo = texto.trim();
  return useQuery({
    queryKey: ["simbolos", "busca", tipo, termo],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/simbolos/busca", { params: { query: { tipo, q: termo } }, signal }),
      ),
    enabled: tipo !== "" && termo !== "",
    staleTime: 60_000,
  });
}

/** Posições abertas numa instituição na data da operação (venda, resgate e provento). */
export function usePosicoesNaData(instituicaoId: number | null, data: string) {
  const { cliente } = useClienteApi();
  const dataValida = /^\d{4}-\d{2}-\d{2}$/.test(data);
  return useQuery({
    queryKey: ["portfolio", "posicoes-movimentacao", instituicaoId, data],
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/portfolio/posicoes", {
          params: { query: { instituicao_id: instituicaoId ?? undefined, data } },
          signal,
        }),
      ),
    enabled: instituicaoId !== null && dataValida,
  });
}
