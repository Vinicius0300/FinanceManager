import { casasDecimais, comparar, ehDecimal, normalizarDecimal, sinal, somar } from "@/lib/decimal";
import { ORDEM_TIPOS_ATIVO } from "@/lib/fatias";
import { formatarNumero, SINAL_NEGATIVO } from "@/lib/formatacao";
import { SERIES_GRAFICO } from "@/theme/cores";
import type { ModoPlano } from "./consultas";

/**
 * Regras de apresentação do Rebalanceamento (puras e testadas). Nenhuma conta financeira
 * em `number`: somas e comparações por `lib/decimal`; os valores do plano vêm prontos da API.
 */

export const MODOS: readonly { valor: ModoPlano; rotulo: string }[] = [
  { valor: "aportes", rotulo: "Só com aportes" },
  { valor: "completo", rotulo: "Completo (com vendas)" },
];

export const TOLERANCIAS = Array.from({ length: 20 }, (_, i) => i + 1);

/** Modo da URL; qualquer outro valor cai no padrão (`aportes`). */
export function lerModo(texto: string | null): ModoPlano {
  return texto === "completo" ? "completo" : "aportes";
}

/** Aporte válido para a API: número ≥ 0 com até 2 casas ("1.234,5" → "1234.5"); senão `null`. */
export function lerAporte(texto: string | null | undefined): string | null {
  if (!texto) return null;
  const normalizado = normalizarDecimal(texto);
  if (normalizado === null || sinal(normalizado) < 0 || casasDecimais(normalizado) > 2) return null;
  return normalizado;
}

/** Mensagem do campo de aporte (ou `null` se estiver certo ou vazio). */
export function erroDoAporte(texto: string): string | null {
  const limpo = texto.trim();
  if (limpo === "") return null;
  const normalizado = normalizarDecimal(limpo);
  if (normalizado === null) return "Informe um número (ex.: 1.234,56).";
  if (sinal(normalizado) < 0) return "O aporte não pode ser negativo.";
  if (casasDecimais(normalizado) > 2) return "Use no máximo 2 casas decimais.";
  return null;
}

/** Desvio em pontos percentuais com sinal: "+7,00 p.p.", "−6,00 p.p.", "0,00 p.p.". */
export function formatarPp(valor: string | null | undefined): string {
  if (valor === null || valor === undefined || !ehDecimal(valor)) return "—";
  const numero = formatarNumero(valor, { minimo: 2, maximo: 2 });
  return `${sinal(valor) > 0 ? "+" : ""}${numero} p.p.`;
}

/** Cor da classe (mesma ordem fixa das fatias de alocação), como variável CSS. */
export function corDaClasse(tipo: string): string {
  const indice = (ORDEM_TIPOS_ATIVO as readonly string[]).indexOf(tipo);
  const token = indice >= 0 ? SERIES_GRAFICO[indice] : undefined;
  return `var(${token ?? "--grafico-caixa"})`;
}

export interface SomaPercentuais {
  soma: string;
  completa: boolean;
  texto: string; // "Soma: 97,5% (faltam 2,5%)"
}

/**
 * Soma ao vivo de percentuais digitados (vazios e inválidos ficam de fora), comparada com
 * 100%: "Soma: 100%", "Soma: 97,5% (faltam 2,5%)" ou "Soma: 101% (passou 1%)".
 */
export function somarPercentuais(textos: readonly string[]): SomaPercentuais {
  const validos = textos
    .map((t) => normalizarDecimal(t))
    .filter((t): t is string => t !== null && ehDecimal(t));
  const soma = somar(validos);
  const diferenca = somar(["100", sinal(soma) < 0 ? soma.slice(1) : `-${soma}`]);
  const legivel = (v: string) => formatarNumero(v, { maximo: 8 }).replace(SINAL_NEGATIVO, "");
  const relacao = comparar(soma, "100");
  const texto =
    relacao === 0
      ? `Soma: ${legivel(soma)}%`
      : relacao < 0
        ? `Soma: ${legivel(soma)}% (faltam ${legivel(diferenca)}%)`
        : `Soma: ${legivel(soma)}% (passou ${legivel(diferenca)}%)`;
  return { soma, completa: relacao === 0, texto };
}
