import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { FalhaApi } from "./backend";
import {
  aplicarErrosDaApi,
  CASAS,
  decimalObrigatorio,
  decimalOpcional,
  lerDecimal,
  paraCampo,
  textoOpcional,
} from "./formularios";

function erros(esquema: z.ZodType, valor: unknown): string[] {
  const resultado = esquema.safeParse(valor);
  return resultado.success ? [] : resultado.error.issues.map((i) => i.message);
}

describe("números digitados (pt-BR) com as casas do backend", () => {
  const preco = decimalObrigatorio({ casas: CASAS.preco, sinal: "positivo" });

  it("normaliza para o formato da API", () => {
    expect(preco.parse("1.234,56")).toBe("1234.56");
    expect(preco.parse("0,00012345")).toBe("0.00012345");
  });

  it("recusa mais casas que o permitido (não arredonda)", () => {
    expect(erros(decimalObrigatorio({ casas: CASAS.moeda }), "10,123")).toEqual([
      "Use no máximo 2 casas decimais.",
    ]);
    expect(erros(decimalObrigatorio({ casas: CASAS.cambio }), "5,1234567")).toEqual([
      "Use no máximo 6 casas decimais.",
    ]);
  });

  it("mensagens em pt-BR", () => {
    expect(erros(preco, "")).toEqual(["Campo obrigatório."]);
    expect(erros(preco, "abc")).toEqual(["Informe um número (ex.: 1.234,56)."]);
    expect(erros(preco, "0")).toEqual(["Informe um valor maior que zero."]);
    expect(erros(decimalObrigatorio({ casas: 2, sinal: "naoNegativo" }), "-1")).toEqual([
      "O valor não pode ser negativo.",
    ]);
    expect(erros(decimalObrigatorio({ casas: 2, minimo: "0.5", maximo: "300" }), "301")).toEqual([
      "O máximo é 300.",
    ]);
    expect(erros(decimalObrigatorio({ casas: 2, minimo: "0.5" }), "0,4")).toEqual([
      "O mínimo é 0,5.",
    ]);
  });

  it("opcional vazio vira null", () => {
    expect(decimalOpcional({ casas: 2 }).parse("  ")).toBeNull();
    expect(textoOpcional(10).parse(" ")).toBeNull();
    expect(erros(textoOpcional(3), "abcd")).toEqual(["Use no máximo 3 caracteres."]);
  });

  it("lerDecimal marca o erro no campo certo", () => {
    const esquema = z
      .object({ q: z.string() })
      .transform((v, ctx) => lerDecimal(ctx, "q", v.q, { casas: 2, obrigatorio: true }));
    const resultado = esquema.safeParse({ q: "" });
    expect(resultado.success).toBe(false);
    expect(resultado.error?.issues[0]?.path).toEqual(["q"]);
  });

  it("paraCampo mostra o decimal da API com vírgula", () => {
    expect(paraCampo("38.12")).toBe("38,12");
    expect(paraCampo(null)).toBe("");
  });
});

describe("aplicarErrosDaApi", () => {
  it("coloca os detalhes por campo vindos da API nos campos do formulário", () => {
    const setError = vi.fn();
    const falha = new FalhaApi(
      {
        codigo: "validacao",
        mensagem: "Dados inválidos.",
        detalhes: [
          { campo: "cnpj", mensagem: "CNPJ inválido." },
          { campo: "nome", mensagem: "Campo obrigatório." },
          { campo: "desconhecido", mensagem: "x" },
        ],
      },
      422,
    );
    const aplicou = aplicarErrosDaApi(falha, setError, ["nome", "metadados.cnpj"], {
      cnpj: "metadados.cnpj",
    });
    expect(aplicou).toBe(true);
    expect(setError).toHaveBeenCalledWith("metadados.cnpj", {
      type: "api",
      message: "CNPJ inválido.",
    });
    expect(setError).toHaveBeenCalledWith("nome", { type: "api", message: "Campo obrigatório." });
    expect(setError).toHaveBeenCalledTimes(2);
  });

  it("ignora erros que não são da API", () => {
    expect(aplicarErrosDaApi(new Error("x"), vi.fn(), ["nome"])).toBe(false);
  });
});
