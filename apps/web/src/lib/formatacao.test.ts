import { describe, expect, it } from "vitest";
import {
  formatarData,
  formatarMesAno,
  formatarMesCurto,
  formatarMoeda,
  formatarMoedaComSinal,
  formatarNumero,
  formatarPercentual,
  formatarPreco,
  formatarRazao,
  formatarRazaoComSinal,
  plural,
  tomDoValor,
} from "./formatacao";

// Intl usa espaço não separável depois do símbolo em algumas versões; normalizamos.
const limpo = (texto: string) => texto.replace(/\u00a0/g, " ");

describe("formatação de dinheiro (sem perder precisão)", () => {
  it("BRL e USD com 2 casas", () => {
    expect(limpo(formatarMoeda("1234.5"))).toBe("R$ 1.234,50");
    expect(limpo(formatarMoeda("7626"))).toBe("R$ 7.626,00");
    expect(limpo(formatarMoeda("229.1", "USD"))).toBe("US$ 229,10");
    expect(limpo(formatarMoeda("0"))).toBe("R$ 0,00");
  });

  it("negativos com sinal de menos antes do símbolo", () => {
    expect(limpo(formatarMoeda("-2456.4"))).toBe("−R$ 2.456,40");
  });

  it("não arredonda pelo float: valores enormes saem exatos", () => {
    expect(limpo(formatarMoeda("12345678901234567.89"))).toBe("R$ 12.345.678.901.234.567,89");
  });

  it("valor ausente ou inválido vira traço", () => {
    expect(formatarMoeda(null)).toBe("—");
    expect(formatarMoeda("abc")).toBe("—");
  });

  it("com sinal explícito para ganho", () => {
    expect(limpo(formatarMoedaComSinal("195"))).toBe("+R$ 195,00");
    expect(limpo(formatarMoedaComSinal("-40"))).toBe("−R$ 40,00");
    expect(limpo(formatarMoedaComSinal("0"))).toBe("R$ 0,00");
  });
});

describe("números, preços e percentuais", () => {
  it("quantidades com até 8 casas", () => {
    expect(formatarNumero("0.12345678")).toBe("0,12345678");
    expect(formatarNumero("1500")).toBe("1.500");
    expect(formatarNumero("-2.5")).toBe("−2,5");
  });

  it("preço unitário na moeda do ativo, mínimo 2 casas", () => {
    expect(limpo(formatarPreco("38.12"))).toBe("R$ 38,12");
    expect(limpo(formatarPreco("61400", "USD"))).toBe("US$ 61.400,00");
    expect(limpo(formatarPreco("1.23456789"))).toBe("R$ 1,23456789");
  });

  it("razão da API como percentual", () => {
    expect(formatarRazao("0.1234")).toBe("12,34%");
    expect(formatarRazao("0.25")).toBe("25,00%");
    expect(formatarRazaoComSinal("0.0125")).toBe("+1,25%");
    expect(formatarRazaoComSinal("-0.004")).toBe("−0,40%");
    expect(formatarPercentual("10.5")).toBe("10,50%");
  });

  it("tom do valor (zero é neutro)", () => {
    expect(tomDoValor("1")).toBe("positivo");
    expect(tomDoValor("-1")).toBe("negativo");
    expect(tomDoValor("0.00")).toBe("neutro");
    expect(tomDoValor(undefined)).toBe("neutro");
  });
});

describe("datas de calendário (sem fuso)", () => {
  it("dd/mm/aaaa", () => {
    expect(formatarData("2026-10-29")).toBe("29/10/2026");
    expect(formatarData("2026-01-01")).toBe("01/01/2026");
    expect(formatarData(null)).toBe("—");
  });

  it("mês por extenso e curto", () => {
    expect(formatarMesAno("2026-10-01")).toBe("outubro de 2026");
    expect(formatarMesCurto("2026-03-01")).toBe("mar/26");
  });

  it("plural", () => {
    expect(plural(1, "operação", "operações")).toBe("1 operação");
    expect(plural(1500, "operação", "operações")).toBe("1.500 operações");
    expect(plural(0, "operação", "operações")).toBe("0 operações");
  });
});
