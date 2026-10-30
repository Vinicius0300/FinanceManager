import type { components } from "@/api/schema";

type TipoEvento = components["schemas"]["EventoSaida"]["tipo"];

export const NOMES_EVENTO: Record<TipoEvento, string> = {
  desdobramento: "Desdobramento",
  grupamento: "Grupamento",
  bonificacao: "Bonificação",
};
