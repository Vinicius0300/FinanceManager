import { describe, expect, it } from "vitest";
import { separarAltasEBaixas, type VariacaoAtivo } from "./variacoes";

function item(ativo_id: number, variacao: string | null): VariacaoAtivo {
  return {
    ativo_id,
    nome: `Ativo ${ativo_id}`,
    variacao: {
      preco_atual: "1",
      data_atual: "2026-10-29",
      preco_anterior: "1",
      data_anterior: "2026-10-28",
      variacao,
      variacao_brl: null,
    },
  };
}

describe("altas e baixas do dia", () => {
  it("ordena cada lado pela razão decimal e limita a 3", () => {
    const { altas, baixas } = separarAltasEBaixas([
      item(1, "0.0312"),
      item(2, "0.0148"),
      item(3, "0.1"), // 10% vem antes de 3,12% (comparação decimal, não de texto)
      item(4, "0.002"),
      item(5, "-0.0205"),
      item(6, "-0.011"),
      item(7, "-0.15"),
    ]);
    expect(altas.map((a) => a.ativo_id)).toEqual([3, 1, 2]);
    expect(baixas.map((a) => a.ativo_id)).toEqual([7, 5, 6]);
  });

  it("variação zero ou sem razão não entra", () => {
    const { altas, baixas } = separarAltasEBaixas([item(1, "0"), item(2, null), item(3, "-0.00")]);
    expect(altas).toEqual([]);
    expect(baixas).toEqual([]);
  });
});
