import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import type { components } from "@/api/schema";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import {
  CASAS,
  dataObrigatoria,
  decimalObrigatorio,
  decimalOpcional,
  textoOpcional,
} from "@/lib/formularios";

/** Transferências entre instituições: esquema do formulário e consultas. */
export type Transferencia = components["schemas"]["TransferenciaSaida"];
export type TransferenciaEntrada = components["schemas"]["TransferenciaEntrada"];

export const MOEDAS_TRANSFERENCIA = ["BRL", "USD"] as const;
export const DICA_TARIFA_USD = "Tarifa só em reais: em dólar, lance a tarifa como saque.";

export const esquemaTransferencia = z
  .object({
    data: dataObrigatoria,
    origem_id: z.string().min(1, "Escolha a instituição de origem."),
    destino_id: z.string().min(1, "Escolha a instituição de destino."),
    moeda: z.enum(MOEDAS_TRANSFERENCIA),
    valor: decimalObrigatorio({ casas: CASAS.moeda, sinal: "positivo" }),
    tarifa: decimalOpcional({ casas: CASAS.moeda, sinal: "naoNegativo" }),
    categoria_tarifa_id: z.string(),
    descricao: textoOpcional(300),
  })
  .refine((v) => v.origem_id === "" || v.origem_id !== v.destino_id, {
    path: ["destino_id"],
    message: "Escolha um destino diferente da origem.",
  })
  .transform((v): TransferenciaEntrada => ({
    data: v.data,
    origem_id: Number(v.origem_id),
    destino_id: Number(v.destino_id),
    moeda: v.moeda,
    valor: v.valor,
    // Tarifa só em BRL (no dólar o campo fica desabilitado e vai zero).
    tarifa: v.moeda === "BRL" ? (v.tarifa ?? "0") : "0",
    categoria_tarifa_id:
      v.moeda === "BRL" && v.tarifa && v.categoria_tarifa_id ? Number(v.categoria_tarifa_id) : null,
    descricao: v.descricao,
  }));

export function useTransferencia(id: number | null) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["transferencias", id],
    enabled: id !== null,
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/transferencias/{transferencia_id}", {
          params: { path: { transferencia_id: id ?? 0 } },
          signal,
        }),
      ),
  });
}

export function useExcluirTransferencia() {
  const { cliente } = useClienteApi();
  return useGravacao(async (id: number) => {
    exigir(
      await cliente.DELETE("/api/transferencias/{transferencia_id}", {
        params: { path: { transferencia_id: id } },
      }),
    );
  });
}
