import { describe, expect, it } from "vitest";
import { ORDEM_TIPOS_ATIVO, prepararFatias, type FatiaEntrada } from "./fatias";

const CORES = { series: ["c1", "c2", "c3", "c4", "c5", "c6"], caixa: "cx" };

const fatia = (categoria: string, valor: string, percentual?: string): FatiaEntrada => ({
  categoria,
  rotulo: categoria,
  valor,
  percentual: percentual ?? null,
});

describe("fatias com cor fixa por categoria", () => {
  it("a cor vem da posição fixa, não da ordem de chegada; caixa fica por último", () => {
    const prontas = prepararFatias(
      [fatia("caixa", "50"), fatia("fundo", "10"), fatia("acao_br", "300")],
      ORDEM_TIPOS_ATIVO,
      CORES,
    );
    expect(prontas.map((f) => [f.categoria, f.cor])).toEqual([
      ["acao_br", "c1"],
      ["fundo", "c3"],
      ["caixa", "cx"],
    ]);
  });

  it("a mesma categoria tem a mesma cor em gráficos diferentes", () => {
    const a = prepararFatias([fatia("cripto", "1")], ORDEM_TIPOS_ATIVO, CORES);
    const b = prepararFatias(
      [fatia("acao_br", "1"), fatia("cripto", "5")],
      ORDEM_TIPOS_ATIVO,
      CORES,
    );
    expect(a[0]?.cor).toBe("c6");
    expect(b.find((f) => f.categoria === "cripto")?.cor).toBe("c6");
  });

  it("categoria sem posição fixa usa a primeira cor livre (até 6 categorias)", () => {
    const prontas = prepararFatias(
      [fatia("poupanca", "10"), fatia("acao_br", "20")],
      ORDEM_TIPOS_ATIVO,
      CORES,
    );
    expect(prontas.map((f) => [f.categoria, f.cor])).toEqual([
      ["acao_br", "c1"],
      ["poupanca", "c2"],
    ]);
  });

  it("acima de 6 categorias o resto vira Outros (soma exata, cor de caixa)", () => {
    // 10 tipos + caixa: da 7ª categoria na ordem fixa em diante (poupança, fundo listado,
    // ETF BR e ETF EUA) tudo vai para "Outros".
    const entrada = [
      ...ORDEM_TIPOS_ATIVO.map((t, i) => fatia(t, `${i + 1}0.10`, "0.1")),
      fatia("desconhecido", "0.05", "0.005"),
      fatia("caixa", "100"),
    ];
    const prontas = prepararFatias(entrada, ORDEM_TIPOS_ATIVO, CORES);
    expect(prontas).toHaveLength(8);
    const outros = prontas.find((f) => f.categoria === "outros");
    // 70,10 + 80,10 + 90,10 + 100,10 + desconhecido 0,05 = 340,45;
    // percentuais 4 × 0,1 + 0,005 = 0,405.
    expect(outros).toMatchObject({
      rotulo: "Outros",
      valor: "340.45",
      percentual: "0.405",
      cor: "cx",
    });
    expect(prontas.at(-1)?.categoria).toBe("caixa");
  });

  it("Outros sem percentual quando algum item não tem", () => {
    const entrada = Array.from({ length: 8 }, (_, i) => fatia(`cat${i}`, "1"));
    const prontas = prepararFatias(entrada, [], CORES);
    expect(prontas.at(-1)).toMatchObject({ categoria: "outros", valor: "2", percentual: null });
    expect(new Set(prontas.slice(0, 6).map((f) => f.cor)).size).toBe(6);
  });
});
