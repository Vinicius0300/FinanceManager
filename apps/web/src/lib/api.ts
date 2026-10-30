import type { QueryClient } from "@tanstack/react-query";
import { FalhaApi, type ErroApi } from "./backend";

interface RespostaApi<D> {
  data?: D;
  error?: unknown;
  response: Response;
}

function ehErroApi(valor: unknown): valor is ErroApi {
  return (
    typeof valor === "object" &&
    valor !== null &&
    "mensagem" in valor &&
    typeof valor.mensagem === "string" &&
    "codigo" in valor &&
    typeof valor.codigo === "string"
  );
}

/**
 * Desembrulha a resposta do cliente gerado (openapi-fetch): devolve `data` ou lança
 * `FalhaApi` com a mensagem em pt-BR e os `detalhes` por campo vindos da API.
 */
export function exigir<D>(resposta: RespostaApi<D>): D {
  const { data, error, response } = resposta;
  if (error !== undefined || !response.ok) {
    const corpo: ErroApi = ehErroApi(error)
      ? error
      : {
          codigo: "erro_inesperado",
          mensagem: `O serviço interno respondeu com erro (${response.status}).`,
        };
    throw new FalhaApi(corpo, response.status);
  }
  return data as D;
}

/** Chave da consulta da conexão com o backend: nunca é invalidada junto com os dados. */
const CHAVES_PRESERVADAS = new Set(["conexao-backend", "health"]);

/**
 * Depois de qualquer gravação, marca como desatualizados todos os dados do app (são
 * poucos e locais): Dashboard, Carteira, Caixa e histórico refletem a mudança sem
 * recarregar a tela. Só as consultas visíveis são buscadas de novo.
 */
export function invalidarDados(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({
    predicate: (consulta) => !CHAVES_PRESERVADAS.has(String(consulta.queryKey[0])),
  });
}
