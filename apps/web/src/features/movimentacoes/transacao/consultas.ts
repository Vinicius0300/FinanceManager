import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import type { TransacaoEntrada } from "./esquema";

/** Grava (POST) ou substitui (PUT) uma transação. */
export function useSalvarTransacao() {
  const { cliente } = useClienteApi();
  return useGravacao(async ({ id, corpo }: { id?: number; corpo: TransacaoEntrada }) =>
    id === undefined
      ? exigir(await cliente.POST("/api/transacoes", { body: corpo }))
      : exigir(
          await cliente.PUT("/api/transacoes/{transacao_id}", {
            params: { path: { transacao_id: id } },
            body: corpo,
          }),
        ),
  );
}
