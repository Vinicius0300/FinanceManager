import { describe, expect, it } from "vitest";
import { mensagemDeErro } from "./backend";
import { formatarDataHora } from "./formatacao";

describe("mensagemDeErro", () => {
  it("usa a mensagem padronizada da API", () => {
    expect(mensagemDeErro({ codigo: "nao_autorizado", mensagem: "Token inválido." })).toBe(
      "Token inválido.",
    );
  });

  it("traduz falha de rede", () => {
    expect(mensagemDeErro(new TypeError("Failed to fetch"))).toMatch(/Não foi possível conectar/);
  });

  it("tem mensagem genérica para valores desconhecidos", () => {
    expect(mensagemDeErro(42)).toBe("Ocorreu um erro inesperado.");
  });
});

describe("formatarDataHora", () => {
  it("formata em pt-BR (dd/mm/aaaa hh:mm:ss)", () => {
    expect(formatarDataHora("2026-01-02T03:04:05")).toBe("02/01/2026, 03:04:05");
  });

  it("não quebra com data inválida", () => {
    expect(formatarDataHora("xyz")).toBe("data inválida");
  });
});
