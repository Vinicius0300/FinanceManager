import { z } from "zod";
import type { components } from "@/api/schema";
import { CASAS } from "@/lib/formularios";

type TipoIndicador = components["schemas"]["IndicadorSaida"]["tipo"];

export interface DefinicaoIndicador {
  tipo: TipoIndicador;
  moeda: string;
  nome: string;
  unidade: string;
  casas: number;
  ajuda: string;
}

export const INDICADORES: readonly DefinicaoIndicador[] = [
  {
    tipo: "selic",
    moeda: "BRL",
    nome: "Selic",
    unidade: "% a.a.",
    casas: CASAS.preco,
    ajuda: "Meta da Selic em % ao ano.",
  },
  {
    tipo: "cdi",
    moeda: "BRL",
    nome: "CDI",
    unidade: "% a.a.",
    casas: CASAS.preco,
    ajuda: "CDI anualizado (base 252) em % ao ano.",
  },
  {
    tipo: "ipca",
    moeda: "BRL",
    nome: "IPCA",
    unidade: "% no mês",
    casas: CASAS.preco,
    ajuda: "Variação no mês; use o dia 1º do mês de referência.",
  },
  {
    tipo: "cambio",
    moeda: "USD",
    nome: "Dólar (PTAX)",
    unidade: "R$ por US$",
    casas: CASAS.cambio,
    ajuda: "Reais por dólar (até 6 casas).",
  },
];

export const esquemaIntervalo = z.object({
  intervalo_atualizacao_min: z
    .string()
    .trim()
    .regex(/^\d+$/, "Use um número inteiro de minutos.")
    .transform(Number)
    .refine((v) => v >= 1 && v <= 15, "Escolha entre 1 e 15 minutos."),
});
