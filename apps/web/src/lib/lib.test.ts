import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ehFalhaDeRede,
  MENSAGEM_INESPERADA,
  MENSAGEM_SEM_CONEXAO,
  mensagemDeErro,
} from "./backend";
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

  it.each([
    "Failed to fetch",
    "network error",
    "NetworkError when attempting to fetch resource.",
    "Load failed",
  ])("reconhece a falha de rede do fetch: %s", (texto) => {
    expect(ehFalhaDeRede(new TypeError(texto))).toBe(true);
    expect(mensagemDeErro(new TypeError(texto))).toBe(MENSAGEM_SEM_CONEXAO);
  });

  describe("TypeError de código (bug)", () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("não vira falha de conexão: mensagem genérica e console, uma vez por erro", () => {
      const consoleErro = vi.spyOn(console, "error").mockImplementation(() => undefined);
      const bug = new TypeError("Cannot read properties of undefined (reading 'valor')");
      expect(ehFalhaDeRede(bug)).toBe(false);
      expect(mensagemDeErro(bug)).toBe(MENSAGEM_INESPERADA);
      // A tela pede a mensagem a cada renderização: o console recebe o erro uma vez só.
      expect(mensagemDeErro(bug)).toBe(MENSAGEM_INESPERADA);
      expect(consoleErro).toHaveBeenCalledOnce();
      expect(consoleErro).toHaveBeenCalledWith("Erro inesperado no app:", bug);
    });

    it("erro comum continua mostrando a própria mensagem, sem console", () => {
      const consoleErro = vi.spyOn(console, "error").mockImplementation(() => undefined);
      expect(mensagemDeErro(new Error("O serviço interno não respondeu."))).toBe(
        "O serviço interno não respondeu.",
      );
      expect(consoleErro).not.toHaveBeenCalled();
    });
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
