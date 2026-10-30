import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { endOfMonth, format } from "date-fns";
import type { components } from "@/api/schema";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";

export type Categoria = components["schemas"]["CategoriaSaida"];
export type Lancamento = components["schemas"]["LancamentoSaida"];
export type LancamentoEntrada = components["schemas"]["LancamentoEntrada"];
export type TipoLancamento = Categoria["tipo"];

export interface Mes {
  ano: number;
  mes: number; // 1 a 12
}

export function limitesDoMes({ ano, mes }: Mes): { inicio: string; fim: string } {
  const primeiro = new Date(ano, mes - 1, 1);
  return {
    inicio: format(primeiro, "yyyy-MM-dd"),
    fim: format(endOfMonth(primeiro), "yyyy-MM-dd"),
  };
}

export function somarMes({ ano, mes }: Mes, delta: number): Mes {
  const indice = ano * 12 + (mes - 1) + delta;
  return { ano: Math.floor(indice / 12), mes: (indice % 12) + 1 };
}

export function useCategorias() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["categorias"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/categorias", { signal })),
  });
}

/** Lançamentos do mês (até 500, o máximo por página da API). */
export function useLancamentos(mes: Mes) {
  const { cliente } = useClienteApi();
  const { inicio, fim } = limitesDoMes(mes);
  return useQuery({
    queryKey: ["lancamentos", mes.ano, mes.mes],
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/lancamentos", {
          params: { query: { inicio, fim, limite: 500 } },
          signal,
        }),
      ),
  });
}

export function useSalvarLancamento() {
  const { cliente } = useClienteApi();
  return useGravacao(async ({ id, corpo }: { id?: number; corpo: LancamentoEntrada }) =>
    id === undefined
      ? exigir(await cliente.POST("/api/lancamentos", { body: corpo }))
      : exigir(
          await cliente.PUT("/api/lancamentos/{lancamento_id}", {
            params: { path: { lancamento_id: id } },
            body: corpo,
          }),
        ),
  );
}

export function useExcluirLancamento() {
  const { cliente } = useClienteApi();
  return useGravacao(async (id: number) => {
    exigir(
      await cliente.DELETE("/api/lancamentos/{lancamento_id}", {
        params: { path: { lancamento_id: id } },
      }),
    );
  });
}

export function useSalvarCategoria() {
  const { cliente } = useClienteApi();
  return useGravacao(
    async ({ id, nome, tipo }: { id?: number; nome: string; tipo: TipoLancamento }) =>
      id === undefined
        ? exigir(await cliente.POST("/api/categorias", { body: { nome, tipo } }))
        : exigir(
            await cliente.PUT("/api/categorias/{categoria_id}", {
              params: { path: { categoria_id: id } },
              body: { nome },
            }),
          ),
  );
}

export function useExcluirCategoria() {
  const { cliente } = useClienteApi();
  return useGravacao(async (id: number) => {
    exigir(
      await cliente.DELETE("/api/categorias/{categoria_id}", {
        params: { path: { categoria_id: id } },
      }),
    );
  });
}
