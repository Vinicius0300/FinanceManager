import { describe, expect, it } from "vitest";
import { subtotalResultado } from "./subtotais";

const com = (resultado: string) => ({ metricas_brl: { resultado_total: resultado } });

describe("subtotal de resultado por instituição", () => {
  it("soma exata em decimal (exemplo do dono: 4.210,40 + 3.012,50 = 7.222,90)", () => {
    expect(subtotalResultado([com("4210.40"), com("3012.50")])).toBe("7222.90");
  });

  it("sem perda de precisão onde o number erraria (0,1 + 0,2)", () => {
    expect(subtotalResultado([com("0.1"), com("0.2")])).toBe("0.3");
    expect(subtotalResultado([com("-1083.20"), com("1083.20")])).toBe("0.00");
  });

  it("posição sem resultado deixa o subtotal indisponível", () => {
    expect(subtotalResultado([com("10"), { metricas_brl: null }])).toBeNull();
    expect(subtotalResultado([com("10"), {}])).toBeNull();
  });

  it("instituição só com caixa: subtotal zero", () => {
    expect(subtotalResultado([])).toBe("0");
  });
});
