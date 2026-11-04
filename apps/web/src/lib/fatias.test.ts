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

  it("acima de 6 categorias as menores viram Outros (soma exata, cor de caixa)", () => {
    // 10 tipos + caixa, valores crescentes na ordem fixa (ação BR 10,10 ... ETF EUA 100,10):
    // as 6 maiores são ETF EUA, ETF BR, fundo listado, poupança, cripto e Tesouro.
    const entrada = [
      ...ORDEM_TIPOS_ATIVO.map((t, i) => fatia(t, `${i + 1}0.10`, "0.1")),
      fatia("desconhecido", "0.05", "0.005"),
      fatia("caixa", "100"),
    ];
    const prontas = prepararFatias(entrada, ORDEM_TIPOS_ATIVO, CORES);
    expect(prontas.map((f) => [f.categoria, f.cor])).toEqual([
      ["etf_us", "c1"], // sem cor própria: 1ª livre (ação BR caiu em Outros)
      ["etf_br", "c2"], // 2ª livre (renda fixa)
      ["fundo_listado", "c3"], // 3ª livre (fundo)
      ["poupanca", "c4"], // 4ª livre (ação EUA)
      ["cripto", "c6"], // cor fixa
      ["tesouro_direto", "c5"], // cor fixa
      ["outros", "cx"],
      ["caixa", "cx"],
    ]);
    // ação BR 10,10 + renda fixa 20,10 + fundo 30,10 + ação EUA 40,10 + desconhecido 0,05
    // = 100,45; percentuais 4 × 0,1 + 0,005 = 0,405.
    expect(prontas.find((f) => f.categoria === "outros")).toMatchObject({
      rotulo: "Outros",
      valor: "100.45",
      percentual: "0.405",
    });
  });

  it("exemplo do dono: as 6 maiores com as cores de sempre e Outros 7%", () => {
    const prontas = prepararFatias(
      [
        fatia("acao_br", "40", "0.40"),
        fatia("renda_fixa", "20", "0.20"),
        fatia("fundo", "10", "0.10"),
        fatia("acao_us", "10", "0.10"),
        fatia("tesouro_direto", "8", "0.08"),
        fatia("cripto", "5", "0.05"),
        fatia("fundo_listado", "4", "0.04"),
        fatia("etf_br", "3", "0.03"),
      ],
      ORDEM_TIPOS_ATIVO,
      CORES,
    );
    expect(prontas.map((f) => [f.categoria, f.cor, f.percentual])).toEqual([
      ["acao_br", "c1", "0.40"],
      ["renda_fixa", "c2", "0.20"],
      ["fundo", "c3", "0.10"], // empate com ação EUA: vale a ordem fixa
      ["acao_us", "c4", "0.10"],
      ["tesouro_direto", "c5", "0.08"],
      ["cripto", "c6", "0.05"],
      ["outros", "cx", "0.07"], // fundo listado 4% + ETF BR 3%
    ]);
  });

  it("tipo sem cor própria no top 6 usa a cor de quem caiu em Outros ou está ausente", () => {
    // Fundo listado 12%: entra no top 6; cripto (5%) cai em Outros e cede a cor c6.
    const comCripto = prepararFatias(
      [
        fatia("acao_br", "40"),
        fatia("renda_fixa", "20"),
        fatia("fundo_listado", "12"),
        fatia("fundo", "10"),
        fatia("acao_us", "10"),
        fatia("tesouro_direto", "8"),
        fatia("cripto", "5"),
      ],
      ORDEM_TIPOS_ATIVO,
      CORES,
    );
    expect(comCripto.find((f) => f.categoria === "fundo_listado")?.cor).toBe("c6");
    expect(comCripto.find((f) => f.categoria === "outros")?.valor).toBe("5");
    // Sem renda fixa na carteira: a cor dela (c2) é a primeira livre.
    const semRendaFixa = prepararFatias(
      [fatia("acao_br", "40"), fatia("fundo_listado", "12"), fatia("cripto", "5")],
      ORDEM_TIPOS_ATIVO,
      CORES,
    );
    expect(semRendaFixa.map((f) => [f.categoria, f.cor])).toEqual([
      ["acao_br", "c1"],
      ["fundo_listado", "c2"],
      ["cripto", "c6"],
    ]);
  });

  it("empate: desempata pela ordem fixa, depois pela ordem de chegada", () => {
    const prontas = prepararFatias(
      [
        fatia("etf_br", "5"),
        fatia("x", "5"),
        fatia("fundo_listado", "5"),
        fatia("acao_br", "5"),
        fatia("renda_fixa", "5"),
        fatia("fundo", "5"),
        fatia("acao_us", "5"),
      ],
      ORDEM_TIPOS_ATIVO,
      CORES,
    );
    expect(prontas.map((f) => f.categoria)).toEqual([
      "acao_br",
      "renda_fixa",
      "fundo",
      "acao_us",
      "fundo_listado",
      "etf_br",
      "outros", // "x" (fora da ordem fixa) perde o empate
    ]);
    expect(prontas.map((f) => f.cor)).toEqual(["c1", "c2", "c3", "c4", "c5", "c6", "cx"]);
  });

  it("Outros sem percentual quando algum item não tem", () => {
    const entrada = Array.from({ length: 8 }, (_, i) => fatia(`cat${i}`, "1"));
    const prontas = prepararFatias(entrada, [], CORES);
    expect(prontas.at(-1)).toMatchObject({ categoria: "outros", valor: "2", percentual: null });
    expect(new Set(prontas.slice(0, 6).map((f) => f.cor)).size).toBe(6);
  });
});
