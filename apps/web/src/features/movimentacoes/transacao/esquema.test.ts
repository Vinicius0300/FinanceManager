import { describe, expect, it } from "vitest";
import {
  criarEsquemaTransacao,
  valoresIniciais,
  type RegrasDoAtivo,
  type ValoresTransacao,
} from "./esquema";

const REGRAS: Record<number, RegrasDoAtivo> = {
  10: { moeda: "BRL", tiposAceitos: ["compra", "venda", "provento"], aceitaTaxas: true },
  11: { moeda: "USD", tiposAceitos: ["compra", "venda", "provento"], aceitaTaxas: true },
  12: { moeda: "BRL", tiposAceitos: ["aporte", "resgate"], aceitaTaxas: false },
};
const esquema = criarEsquemaTransacao((id) => REGRAS[id]);
const base = valoresIniciais("2026-10-29");

function validar(v: Partial<ValoresTransacao>) {
  return esquema.safeParse({ ...base, ativo_id: "10", instituicao_id: "1", ...v });
}

function errosPorCampo(v: Partial<ValoresTransacao>): Record<string, string> {
  const r = validar(v);
  if (r.success) return {};
  return Object.fromEntries(r.error.issues.map((i) => [String(i.path[0]), i.message]));
}

describe("esquema da transação", () => {
  it("compra: quantidade, preço e taxas normalizados", () => {
    const r = validar({ quantidade: "200", preco_unitario: "38,12", taxas: "2" });
    expect(r.success).toBe(true);
    expect(r.data).toMatchObject({
      tipo: "compra",
      ativo_id: 10,
      instituicao_id: 1,
      quantidade: "200",
      preco_unitario: "38.12",
      taxas: "2",
      aceitar_ajuste: false,
      observacao: null,
    });
    expect(r.data).not.toHaveProperty("valor");
    expect(r.data).not.toHaveProperty("cambio"); // ativo em BRL não manda câmbio
  });

  it("compra sem quantidade e preço aponta os dois campos", () => {
    expect(errosPorCampo({})).toEqual({
      quantidade: "Campo obrigatório.",
      preco_unitario: "Campo obrigatório.",
    });
  });

  it("casas: quantidade até 8, dinheiro até 2", () => {
    expect(
      errosPorCampo({ quantidade: "0,123456789", preco_unitario: "1", taxas: "0,001" }),
    ).toEqual({
      quantidade: "Use no máximo 8 casas decimais.",
      taxas: "Use no máximo 2 casas decimais.",
    });
  });

  it("aporte/resgate/provento usam valor (e não quantidade)", () => {
    const r = validar({ tipo: "aporte", ativo_id: "12", valor: "10.000,00" });
    expect(r.success).toBe(true);
    expect(r.data).toMatchObject({ tipo: "aporte", valor: "10000.00", taxas: "0" });
    expect(r.data).not.toHaveProperty("quantidade");
    expect(errosPorCampo({ tipo: "resgate", ativo_id: "12" })).toEqual({
      valor: "Campo obrigatório.",
    });
  });

  it("provento: líquido, tipo e imposto retido", () => {
    const r = validar({
      tipo: "provento",
      valor: "85",
      imposto_retido: "15",
      subtipo_provento: "jcp",
    });
    expect(r.data).toMatchObject({ valor: "85", imposto_retido: "15", subtipo_provento: "jcp" });
    expect(errosPorCampo({ tipo: "provento", valor: "85", subtipo_provento: "" })).toEqual({
      subtipo_provento: "Escolha o tipo do provento.",
    });
  });

  it("câmbio pago só para ativo estrangeiro; vazio = PTAX (null)", () => {
    const sem = validar({ ativo_id: "11", quantidade: "10", preco_unitario: "100" });
    expect(sem.data?.cambio).toBeNull();
    const com = validar({
      ativo_id: "11",
      quantidade: "10",
      preco_unitario: "100",
      cambio: "5,4321",
    });
    expect(com.data?.cambio).toBe("5.4321");
    expect(
      errosPorCampo({ ativo_id: "11", quantidade: "1", preco_unitario: "1", cambio: "5,1234567" }),
    ).toEqual({ cambio: "Use no máximo 6 casas decimais." });
    // Ativo em BRL: um câmbio esquecido no campo oculto não vai para a API.
    expect(validar({ quantidade: "1", preco_unitario: "1", cambio: "5" }).data).not.toHaveProperty(
      "cambio",
    );
  });

  it("operação que o tipo de ativo não aceita", () => {
    expect(errosPorCampo({ tipo: "aporte", valor: "10" })).toEqual({
      tipo: "Este tipo de ativo não aceita aporte.",
    });
  });

  it("renda fixa não manda taxas", () => {
    expect(validar({ tipo: "aporte", ativo_id: "12", valor: "1", taxas: "9" }).data?.taxas).toBe(
      "0",
    );
  });

  it("valores iniciais da edição vêm da API com vírgula", () => {
    const v = valoresIniciais("2026-10-29", {
      id: 1,
      ativo_id: 11,
      instituicao_id: 2,
      tipo: "compra",
      data: "2026-02-02",
      quantidade: "10",
      preco_unitario: "100.5",
      valor: null,
      taxas: "1",
      moeda: "USD",
      cambio: "5",
      subtipo_provento: null,
      imposto_retido: "0",
      observacao: null,
      criado_em: "",
      movimentos: [],
      valor_total: "1006",
      valor_total_brl: "5030",
      taxas_brl: "5",
      imposto_retido_brl: "0",
      resultado: null,
      resultado_brl: null,
      situacao: "aberta",
    });
    expect(v).toMatchObject({
      ativo_id: "11",
      preco_unitario: "100,5",
      taxas: "1",
      cambio: "5",
      imposto_retido: "",
    });
  });
});
