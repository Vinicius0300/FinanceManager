import { describe, expect, it } from "vitest";
import {
  absoluto,
  casasDecimais,
  comparar,
  ehDecimal,
  ehZero,
  moverVirgula,
  normalizarDecimal,
  paraGrafico,
  sinal,
  somar,
} from "./decimal";

describe("decimais exatos em texto", () => {
  it("reconhece números no formato da API", () => {
    expect(ehDecimal("1234.56")).toBe(true);
    expect(ehDecimal("-0.5")).toBe(true);
    expect(ehDecimal("10")).toBe(true);
    expect(ehDecimal("1,5")).toBe(false);
    expect(ehDecimal("abc")).toBe(false);
    expect(ehDecimal("")).toBe(false);
  });

  it("sinal e zero", () => {
    expect(sinal("195.00")).toBe(1);
    expect(sinal("-0.01")).toBe(-1);
    expect(sinal("0.00")).toBe(0);
    expect(sinal("-0")).toBe(0);
    expect(ehZero("0.00")).toBe(true);
    expect(ehZero(null)).toBe(true);
    expect(ehZero("0.01")).toBe(false);
  });

  it("compara sem float, com casas diferentes", () => {
    expect(comparar("0.1", "0.10")).toBe(0);
    expect(comparar("1039.5", "1039.49")).toBe(1);
    expect(comparar("-300", "195")).toBe(-1);
    // Em float, 0.1 + 0.2 != 0.3; aqui a soma é exata.
    expect(comparar(somar(["0.1", "0.2"]), "0.3")).toBe(0);
  });

  it("soma exata mantendo a maior quantidade de casas", () => {
    expect(somar(["0.1", "0.2"])).toBe("0.3");
    expect(somar(["1000.00", "-40", "20.5"])).toBe("980.50");
    expect(somar(["-0.05", "0.02"])).toBe("-0.03");
    expect(somar(["99999999999999999.99", "0.01"])).toBe("100000000000000000.00");
    expect(somar([])).toBe("0");
  });

  it("move a vírgula para exibir razões como percentual", () => {
    expect(moverVirgula("0.1234", 2)).toBe("12.34");
    expect(moverVirgula("-0.004", 2)).toBe("-0.4");
    expect(moverVirgula("1", 2)).toBe("100");
    expect(moverVirgula("0.25", 2)).toBe("25");
  });

  it("valor absoluto e casas", () => {
    expect(absoluto("-12.30")).toBe("12.30");
    expect(absoluto("+5")).toBe("5");
    expect(casasDecimais("1.2345")).toBe(4);
    expect(casasDecimais("10")).toBe(0);
  });

  it("converte para número só para desenhar gráficos", () => {
    expect(paraGrafico("1234.5")).toBe(1234.5);
    expect(paraGrafico(null)).toBe(0);
    expect(paraGrafico("x")).toBe(0);
  });
});

describe("normalizarDecimal (o que o usuário digita)", () => {
  it.each([
    ["1.234,56", "1234.56"],
    ["1234,56", "1234.56"],
    ["1234.56", "1234.56"],
    ["0,5", "0.5"],
    ["0.00012345", "0.00012345"],
    ["10", "10"],
    ["10,", "10"],
    [" 1 234,50 ", "1234.50"],
    ["-3,5", "-3.5"],
    ["+7", "7"],
    ["1.234.567,89", "1234567.89"],
  ])("%s → %s", (entrada, esperado) => {
    expect(normalizarDecimal(entrada)).toBe(esperado);
  });

  it.each(["", "abc", "1,2,3", "1.2.3", "12.34,5.6", "1.23,45", "R$ 10"])(
    "recusa %s",
    (entrada) => {
      expect(normalizarDecimal(entrada)).toBeNull();
    },
  );
});
