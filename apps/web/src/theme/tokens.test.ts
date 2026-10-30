import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { comAlfa, corDaCategoria, TOKENS_GRAFICO } from "./cores";

/**
 * Garante que cada token da paleta existe nos dois temas (:root = claro, .dark = escuro),
 * em oklch, e que está exposto ao Tailwind no @theme inline.
 */
const css = readFileSync(path.resolve(import.meta.dirname, "index.css"), "utf-8");

function bloco(seletor: string): string {
  const inicio = css.indexOf(`${seletor} {`);
  expect(inicio, `bloco ${seletor}`).toBeGreaterThanOrEqual(0);
  return css.slice(inicio, css.indexOf("\n}", inicio));
}

function tokensDe(seletor: string): Map<string, string> {
  const mapa = new Map<string, string>();
  for (const m of bloco(seletor).matchAll(/(--[\w-]+):\s*([^;]+);/g)) {
    if (m[1] && m[2]) mapa.set(m[1], m[2].trim());
  }
  return mapa;
}

const TOKENS_BASE = [
  "--background",
  "--foreground",
  "--card",
  "--card-foreground",
  "--popover",
  "--popover-foreground",
  "--primary",
  "--primary-foreground",
  "--secondary",
  "--secondary-foreground",
  "--muted",
  "--muted-foreground",
  "--accent",
  "--accent-foreground",
  "--destructive",
  "--border",
  "--input",
  "--ring",
];
const TOKENS_NOVOS = [
  "--lateral",
  "--lateral-foreground",
  "--lateral-ativo",
  "--lateral-ativo-foreground",
  "--positivo",
  "--negativo",
  "--sucesso",
  "--sucesso-foreground",
  "--perigo",
  "--perigo-foreground",
  "--aviso",
  "--aviso-foreground",
  "--aviso-texto",
  "--info",
  ...TOKENS_GRAFICO,
];
const TODOS = [...TOKENS_BASE, ...TOKENS_NOVOS];

describe("paleta definitiva (Parte 4)", () => {
  const claro = tokensDe(":root");
  const escuro = tokensDe(".dark");

  it.each(TODOS)("%s existe nos dois temas, em oklch", (token) => {
    expect(claro.get(token), `claro ${token}`).toMatch(/^oklch\(/);
    expect(escuro.get(token), `escuro ${token}`).toMatch(/^oklch\(/);
  });

  it.each(TODOS)("%s está exposto ao Tailwind", (token) => {
    expect(bloco("@theme inline")).toContain(`--color-${token.slice(2)}: var(${token});`);
  });

  it("valores conferidos da tabela aprovada", () => {
    expect(claro.get("--primary")).toBe("oklch(0.522 0.255 280.3)");
    expect(escuro.get("--primary")).toBe("oklch(0.661 0.189 285.5)");
    expect(claro.get("--lateral")).toBe("oklch(0.227 0.078 280.4)");
    expect(escuro.get("--background")).toBe("oklch(0.171 0.037 284.3)");
    expect(claro.get("--positivo")).toBe("oklch(0.513 0.11 161.9)");
    expect(escuro.get("--negativo")).toBe("oklch(0.716 0.181 13.8)");
    expect(claro.get("--grafico-caixa")).toBe("oklch(0.716 0.035 291.2)");
  });

  it("nada de cinza puro: os tons neutros têm croma arroxeado", () => {
    for (const token of ["--muted", "--border", "--muted-foreground", "--background"]) {
      const croma = Number(/oklch\([\d.]+ ([\d.]+)/.exec(claro.get(token) ?? "")?.[1]);
      expect(croma, token).toBeGreaterThan(0);
    }
  });
});

describe("cores dos gráficos", () => {
  it("cor fixa por categoria; caixa e Outros usam a cor de caixa", () => {
    const cores = { series: ["a", "b", "c"], caixa: "cx" };
    expect(corDaCategoria("y", ["x", "y"], cores)).toBe("b");
    expect(corDaCategoria("caixa", ["caixa"], cores)).toBe("cx");
    expect(corDaCategoria("outros", [], cores)).toBe("cx");
    expect(corDaCategoria("z", ["x", "y"], cores)).toBe("cx");
  });

  it("transparência para o degradê da área", () => {
    expect(comAlfa("rgb(91, 61, 245)", 0.35)).toBe("rgba(91, 61, 245, 0.35)");
    expect(comAlfa("oklch(1 0 0)", 0.5)).toBe("oklch(1 0 0)");
  });
});
