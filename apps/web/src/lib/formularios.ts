import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { z } from "zod";
import { FalhaApi } from "./backend";
import { casasDecimais, comparar, normalizarDecimal, sinal } from "./decimal";

/**
 * Peças de validação (Zod) com mensagens em pt-BR. Números são digitados como texto
 * (aceitando "1.234,56") e saem normalizados para a API ("1234.56"), sem passar por
 * `number`. As casas máximas seguem as regras do backend (dinheiro 2, quantidade e preço
 * 8, câmbio 6): valores com mais casas são recusados, não arredondados.
 */
export const CASAS = { moeda: 2, quantidade: 8, preco: 8, cambio: 6 } as const;

export interface OpcoesDecimal {
  casas: number;
  /** "positivo" (> 0), "naoNegativo" (≥ 0) ou sem restrição. */
  sinal?: "positivo" | "naoNegativo";
  minimo?: string | null;
  maximo?: string | null;
}

function validarDecimal(
  texto: string,
  opcoes: OpcoesDecimal,
  ctx: z.RefinementCtx,
  caminho?: string,
): string {
  const path = caminho ? [caminho] : undefined;
  const erro = (message: string) => {
    ctx.addIssue({ code: "custom", message, ...(path ? { path } : {}) });
  };
  const normalizado = normalizarDecimal(texto);
  if (normalizado === null) {
    erro("Informe um número (ex.: 1.234,56).");
    return texto;
  }
  if (casasDecimais(normalizado) > opcoes.casas) {
    erro(
      opcoes.casas === 0
        ? "Use um número sem casas decimais."
        : `Use no máximo ${opcoes.casas} casas decimais.`,
    );
  }
  if (opcoes.sinal === "positivo" && sinal(normalizado) <= 0) {
    erro("Informe um valor maior que zero.");
  }
  if (opcoes.sinal === "naoNegativo" && sinal(normalizado) < 0) {
    erro("O valor não pode ser negativo.");
  }
  if (opcoes.minimo && comparar(normalizado, opcoes.minimo) < 0) {
    erro(`O mínimo é ${opcoes.minimo.replace(".", ",")}.`);
  }
  if (opcoes.maximo && comparar(normalizado, opcoes.maximo) > 0) {
    erro(`O máximo é ${opcoes.maximo.replace(".", ",")}.`);
  }
  return normalizado;
}

/**
 * Valida um número dentro de um `transform`/`superRefine` de objeto, marcando o erro no
 * campo `caminho`. Devolve o texto normalizado ou `null` se vazio (e não obrigatório).
 */
export function lerDecimal(
  ctx: z.RefinementCtx,
  caminho: string,
  texto: string,
  opcoes: OpcoesDecimal & { obrigatorio?: boolean },
): string | null {
  const limpo = texto.trim();
  if (limpo === "") {
    if (opcoes.obrigatorio)
      ctx.addIssue({ code: "custom", message: "Campo obrigatório.", path: [caminho] });
    return null;
  }
  return validarDecimal(limpo, opcoes, ctx, caminho);
}

/** Número obrigatório digitado como texto → texto decimal normalizado. */
export function decimalObrigatorio(opcoes: OpcoesDecimal) {
  return z
    .string()
    .trim()
    .min(1, "Campo obrigatório.")
    .transform((texto, ctx) => validarDecimal(texto, opcoes, ctx));
}

/** Número opcional: vazio vira `null`. */
export function decimalOpcional(opcoes: OpcoesDecimal) {
  return z
    .string()
    .trim()
    .transform((texto, ctx) => (texto === "" ? null : validarDecimal(texto, opcoes, ctx)));
}

export const textoObrigatorio = (maximo: number) =>
  z.string().trim().min(1, "Campo obrigatório.").max(maximo, `Use no máximo ${maximo} caracteres.`);

export const textoOpcional = (maximo: number) =>
  z
    .string()
    .trim()
    .max(maximo, `Use no máximo ${maximo} caracteres.`)
    .transform((texto) => (texto === "" ? null : texto));

export const dataObrigatoria = z
  .string()
  .min(1, { message: "Informe a data.", abort: true })
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Data inválida.");

/** Decimal da API ("1234.5") → texto para o campo, no padrão brasileiro ("1234,5"). */
export function paraCampo(valor: string | null | undefined): string {
  return valor ? valor.replace(".", ",") : "";
}

/**
 * Coloca os `detalhes` por campo vindos da API nos campos do formulário. `mapa` traduz o
 * nome do campo da API para o caminho no formulário quando eles diferem (ex.: "cnpj" →
 * "metadados.cnpj"). Devolve `true` se algum erro foi colocado num campo.
 */
export function aplicarErrosDaApi<T extends FieldValues>(
  erro: unknown,
  setError: UseFormSetError<T>,
  camposDoFormulario: readonly string[],
  mapa: Record<string, string> = {},
): boolean {
  if (!(erro instanceof FalhaApi)) return false;
  let aplicou = false;
  for (const detalhe of erro.detalhes) {
    const caminho = mapa[detalhe.campo] ?? detalhe.campo;
    if (camposDoFormulario.includes(caminho)) {
      setError(caminho as Path<T>, { type: "api", message: detalhe.mensagem });
      aplicou = true;
    }
  }
  return aplicou;
}
