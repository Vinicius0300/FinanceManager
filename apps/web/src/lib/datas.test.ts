import { describe, expect, it } from "vitest";
import { hojeIso, inicioDaJanela, intervaloDoPeriodo, isoValida, tempoDecorrido } from "./datas";

// 29/10/2026, meio-dia local (evita qualquer borda de fuso).
const AGORA = new Date(2026, 9, 29, 12);

describe("períodos do histórico em meses de calendário", () => {
  it("últimos 12 meses = do dia 1º de 11 meses atrás até hoje (nov a out)", () => {
    expect(intervaloDoPeriodo("12m", AGORA)).toEqual({ inicio: "2025-11-01", fim: "2026-10-29" });
  });

  it("este mês, 3 meses e este ano", () => {
    expect(intervaloDoPeriodo("mes", AGORA)).toEqual({ inicio: "2026-10-01", fim: "2026-10-29" });
    expect(intervaloDoPeriodo("3m", AGORA)).toEqual({ inicio: "2026-08-01", fim: "2026-10-29" });
    expect(intervaloDoPeriodo("ano", AGORA)).toEqual({ inicio: "2026-01-01", fim: "2026-10-29" });
  });

  it("todo o histórico não tem limites", () => {
    expect(intervaloDoPeriodo("tudo", AGORA)).toEqual({ inicio: null, fim: null });
  });

  it("personalizado usa as datas válidas informadas", () => {
    expect(
      intervaloDoPeriodo("personalizado", AGORA, { inicio: "2026-02-01", fim: "2026-03-31" }),
    ).toEqual({ inicio: "2026-02-01", fim: "2026-03-31" });
    expect(intervaloDoPeriodo("personalizado", AGORA, { inicio: "31/12/2026" })).toEqual({
      inicio: null,
      fim: null,
    });
  });

  it("janeiro: 12 meses começam em fevereiro do ano anterior", () => {
    expect(intervaloDoPeriodo("12m", new Date(2026, 0, 15, 12)).inicio).toBe("2025-02-01");
  });
});

describe("janelas da evolução (máximo 1 ano na API)", () => {
  it("1A = 365 dias contando hoje", () => {
    expect(inicioDaJanela("1a", AGORA)).toBe("2025-10-30");
    expect(inicioDaJanela("1m", AGORA)).toBe("2026-09-29");
    expect(inicioDaJanela("6m", AGORA)).toBe("2026-04-29");
  });

  it("hoje e validação de datas ISO", () => {
    expect(hojeIso(AGORA)).toBe("2026-10-29");
    expect(isoValida("2026-02-30")).toBe(false);
    expect(isoValida("2026-02-28")).toBe(true);
    expect(isoValida(null)).toBe(false);
  });
});

describe("tempo decorrido (painel de status das cotações)", () => {
  const agora = new Date("2026-11-15T12:00:00Z");
  it.each([
    ["2026-11-15T11:59:30Z", "agora há pouco"], // 30 s
    ["2026-11-15T12:05:00Z", "agora há pouco"], // relógio adiantado
    ["2026-11-15T11:59:00Z", "há 1 minuto"],
    ["2026-11-15T11:50:00Z", "há 10 minutos"],
    ["2026-11-15T11:00:01Z", "há 59 minutos"], // 59 min 59 s: arredonda para baixo
    ["2026-11-15T11:00:00Z", "há 1 hora"],
    ["2026-11-14T13:00:00Z", "há 23 horas"],
    ["2026-11-14T12:00:00Z", "há 1 dia"],
    ["2026-11-12T12:00:00Z", "há 3 dias"],
    ["2026-10-17T12:00:00Z", "há 29 dias"],
    ["2026-10-16T12:00:00Z", "há 1 mês"], // 30 dias
    ["2026-03-15T12:00:00Z", "há 8 meses"], // 245 dias / 30 = 8
    ["2025-11-15T12:00:00Z", "há 1 ano"], // 365 dias
    ["2023-11-15T12:00:00Z", "há 3 anos"],
  ])("%s → %s", (iso, esperado) => {
    expect(tempoDecorrido(iso, agora)).toBe(esperado);
  });

  it("instante inválido vira traço", () => {
    expect(tempoDecorrido("ontem", agora)).toBe("—");
  });
});
