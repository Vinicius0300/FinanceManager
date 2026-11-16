import { z } from "zod";
import {
  CASAS,
  dataObrigatoria,
  decimalObrigatorio,
  textoObrigatorio,
  textoOpcional,
} from "@/lib/formularios";

export const esquemaLancamento = z.object({
  tipo: z.enum(["receita", "despesa"]),
  data: dataObrigatoria,
  valor: decimalObrigatorio({ casas: CASAS.moeda, sinal: "positivo" }),
  instituicao_id: z
    .string()
    .min(1, "Escolha a instituição.")
    .transform((v) => Number(v)),
  categoria_id: z.string().transform((v) => (v ? Number(v) : null)),
  descricao: textoObrigatorio(200),
  observacao: textoOpcional(500),
});
