import { describe, expect, it } from "vitest";
import type { TipoAtivo } from "@/lib/consultas-comuns";
import { TIPOS_ATIVO } from "@/test/api-falsa";
import { criarEsquemaAtivo, paraEntradaAtivo } from "./esquemaAtivo";

const tipo = (slug: string) =>
  (TIPOS_ATIVO as TipoAtivo[]).find((t) => t.slug === slug) as TipoAtivo;

describe("esquema gerado a partir do schema do tipo de ativo (registry real)", () => {
  it("os 10 tipos estão no contrato", () => {
    expect(TIPOS_ATIVO.map((t) => t.slug).sort()).toEqual([
      "acao_br",
      "acao_us",
      "cripto",
      "etf_br",
      "etf_us",
      "fundo",
      "fundo_listado",
      "poupanca",
      "renda_fixa",
      "tesouro_direto",
    ]);
  });

  it("renda fixa: todos os campos obrigatórios com mensagens em pt-BR", () => {
    const resultado = criarEsquemaAtivo(tipo("renda_fixa")).safeParse({
      nome: "CDB",
      simbolo: "",
      moeda: "BRL",
      simbolo_externo: "",
      metadados: {
        indexador: "",
        taxa: "",
        data_aplicacao: "",
        vencimento: "",
        emissor: "",
        liquidez: "",
      },
    });
    expect(resultado.success).toBe(false);
    const erros = Object.fromEntries(
      resultado.error?.issues.map((i) => [i.path.join("."), i.message]) ?? [],
    );
    expect(erros).toMatchObject({
      "metadados.indexador": "Escolha uma opção.",
      "metadados.taxa": "Campo obrigatório.",
      "metadados.data_aplicacao": "Informe a data.",
      "metadados.emissor": "Campo obrigatório.",
    });
  });

  it("renda fixa válida vira o corpo da API (decimal normalizado, sem símbolo)", () => {
    const t = tipo("renda_fixa");
    const dados = criarEsquemaAtivo(t).parse({
      nome: " CDB Banco X ",
      simbolo: "IGNORADO",
      moeda: "BRL",
      simbolo_externo: "",
      metadados: {
        indexador: "cdi",
        taxa: "110,5",
        data_aplicacao: "2026-01-02",
        vencimento: "2028-01-03",
        emissor: "Banco X",
        liquidez: "diaria",
      },
    });
    expect(paraEntradaAtivo(t, dados)).toEqual({
      tipo: "renda_fixa",
      nome: "CDB Banco X",
      simbolo: null,
      moeda: "BRL",
      simbolo_externo: null,
      metadados: {
        indexador: "cdi",
        taxa: "110.5",
        data_aplicacao: "2026-01-02",
        vencimento: "2028-01-03",
        emissor: "Banco X",
        liquidez: "diaria",
      },
    });
  });

  it("fundo: CNPJ obrigatório e classe opcional omitida quando vazia", () => {
    const t = tipo("fundo");
    const dados = criarEsquemaAtivo(t).parse({
      nome: "Fundo X",
      simbolo: "FUNDOX",
      moeda: "BRL",
      simbolo_externo: "123",
      metadados: { cnpj: "12.345.678/0001-90", classe: "" },
    });
    expect(paraEntradaAtivo(t, dados).metadados).toEqual({ cnpj: "12.345.678/0001-90" });
    expect(paraEntradaAtivo(t, dados).simbolo_externo).toBe("123");
  });

  it("ação: campos opcionais podem ficar vazios", () => {
    const t = tipo("acao_br");
    const vazios = Object.fromEntries(t.campos.map((c) => [c.nome, ""]));
    const dados = criarEsquemaAtivo(t).parse({
      nome: "Petrobras",
      simbolo: "petr4",
      moeda: "BRL",
      simbolo_externo: "",
      metadados: vazios,
    });
    expect(paraEntradaAtivo(t, dados)).toMatchObject({ simbolo: "petr4", metadados: {} });
  });

  it("limites do campo decimal vêm do schema (mínimo/máximo do backend)", () => {
    const t = tipo("renda_fixa");
    const taxa = t.campos.find((c) => c.nome === "taxa");
    if (!taxa?.maximo) return; // o backend pode não declarar limite
    const acima = `${taxa.maximo}1`;
    const r = criarEsquemaAtivo(t).safeParse({
      nome: "x",
      simbolo: "",
      moeda: "BRL",
      simbolo_externo: "",
      metadados: {
        indexador: "cdi",
        taxa: acima,
        data_aplicacao: "2026-01-01",
        vencimento: "2027-01-01",
        emissor: "x",
        liquidez: "diaria",
      },
    });
    expect(r.success).toBe(false);
  });
});
