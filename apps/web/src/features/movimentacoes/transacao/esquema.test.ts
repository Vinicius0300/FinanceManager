import { describe, expect, it } from "vitest";
import type { TipoAtivo } from "@/lib/consultas-comuns";
import { TIPOS_ATIVO } from "@/test/api-falsa";
import {
  criarEsquemaTransacao,
  novoAtivoVazio,
  operacaoAceita,
  paraTransacaoEntrada,
  valoresIniciais,
  type ValoresTransacao,
} from "./esquema";

const TIPOS = new Map((TIPOS_ATIVO as TipoAtivo[]).map((t) => [t.slug, t]));
const tipo = (slug: string) => {
  const encontrado = TIPOS.get(slug);
  if (!encontrado) throw new Error(`tipo ${slug} ausente no schema de teste`);
  return encontrado;
};
const MOEDAS: Record<number, string> = { 10: "BRL", 11: "USD", 12: "BRL" };
const esquema = criarEsquemaTransacao({
  tipo: (slug) => TIPOS.get(slug),
  moedaDoAtivo: (id) => MOEDAS[id],
});
const base: ValoresTransacao = {
  ...valoresIniciais("2026-10-29", undefined, tipo("acao_br")),
  modo_ativo: "existente",
  ativo_id: "10",
  instituicao_id: "1",
};

function validar(v: Partial<ValoresTransacao>) {
  return esquema.safeParse({ ...base, ...v });
}

function errosPorCampo(v: Partial<ValoresTransacao>): Record<string, string> {
  const r = validar(v);
  if (r.success) return {};
  return Object.fromEntries(r.error.issues.map((i) => [i.path.join("."), i.message]));
}

function novo(slug: string, dados: Partial<ValoresTransacao["novo_ativo"]>) {
  const vazio = novoAtivoVazio(tipo(slug));
  return { ...vazio, ...dados, metadados: { ...vazio.metadados, ...dados.metadados } };
}

describe("esquema da movimentação", () => {
  it("compra de ativo cadastrado: quantidade, preço e taxas normalizados", () => {
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
      confirmar_novo: false,
      observacao: null,
    });
    expect(r.data).not.toHaveProperty("novo_ativo");
    expect(r.data).not.toHaveProperty("valor");
    expect(r.data).not.toHaveProperty("cambio"); // ativo em BRL não manda câmbio
  });

  it("tudo vazio: tipo, ativo e instituição apontados de uma vez", () => {
    expect(
      errosPorCampo({ tipo_ativo: "", modo_ativo: "", ativo_id: "", instituicao_id: "" }),
    ).toEqual({
      tipo_ativo: "Escolha o tipo de ativo.",
      instituicao_id: "Escolha a instituição.",
      ativo_id: "Escolha o ativo.",
      quantidade: "Campo obrigatório.",
      preco_unitario: "Campo obrigatório.",
    });
  });

  it("compra de ativo novo: valida e monta o novo_ativo pelo schema do tipo", () => {
    const r = validar({
      tipo_ativo: "fundo_listado",
      modo_ativo: "novo",
      ativo_id: "",
      novo_ativo: novo("fundo_listado", {
        simbolo: "HGLG11",
        nome: "Pátria Log",
        simbolo_externo: "HGLG11.SA",
      }),
      quantidade: "10",
      preco_unitario: "160",
    });
    expect(r.success).toBe(true);
    expect(r.data?.novo_ativo).toEqual({
      tipo: "fundo_listado",
      nome: "Pátria Log",
      simbolo: "HGLG11",
      moeda: "BRL",
      simbolo_externo: "HGLG11.SA",
      metadados: {},
    });
    expect(r.data).not.toHaveProperty("ativo_id");
  });

  it("ativo novo sem ticker e sem nome: erros nos campos do novo ativo", () => {
    expect(
      errosPorCampo({
        tipo_ativo: "etf_br",
        modo_ativo: "novo",
        ativo_id: "",
        novo_ativo: novo("etf_br", {}),
        quantidade: "1",
        preco_unitario: "1",
      }),
    ).toEqual({
      "novo_ativo.nome": "Campo obrigatório.",
      "novo_ativo.simbolo": "Informe o ticker.",
    });
  });

  it("renda fixa nova: data de aplicação = data da operação; campos do tipo exigidos", () => {
    const r = validar({
      tipo_ativo: "renda_fixa",
      tipo: "aporte",
      modo_ativo: "novo",
      ativo_id: "",
      data: "2026-10-15",
      valor: "1.000,00",
      novo_ativo: novo("renda_fixa", {
        nome: "CDB X",
        metadados: {
          indexador: "cdi",
          taxa: "110",
          vencimento: "2028-01-03",
          emissor: "Banco X",
          liquidez: "diaria",
        },
      }),
    });
    expect(r.success).toBe(true);
    expect(r.data?.novo_ativo?.metadados).toMatchObject({ data_aplicacao: "2026-10-15" });
    expect(r.data?.valor).toBe("1000.00");
    const faltando = errosPorCampo({
      tipo_ativo: "renda_fixa",
      tipo: "aporte",
      modo_ativo: "novo",
      ativo_id: "",
      valor: "1",
      novo_ativo: novo("renda_fixa", { nome: "CDB X" }),
    });
    expect(Object.keys(faltando).sort()).toEqual([
      "novo_ativo.metadados.emissor",
      "novo_ativo.metadados.indexador",
      "novo_ativo.metadados.liquidez",
      "novo_ativo.metadados.taxa",
      "novo_ativo.metadados.vencimento",
    ]);
  });

  it("venda não cria ativo", () => {
    expect(
      errosPorCampo({
        tipo: "venda",
        modo_ativo: "novo",
        ativo_id: "",
        novo_ativo: novo("acao_br", { simbolo: "PETR4", nome: "Petrobras" }),
        quantidade: "1",
        preco_unitario: "1",
      }),
    ).toEqual({ ativo_id: "Venda, resgate e provento só em ativos já cadastrados." });
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
    const r = validar({ tipo_ativo: "renda_fixa", tipo: "aporte", ativo_id: "12", valor: "10" });
    expect(r.success).toBe(true);
    expect(r.data).toMatchObject({ tipo: "aporte", valor: "10", taxas: "0" });
    expect(r.data).not.toHaveProperty("quantidade");
    expect(errosPorCampo({ tipo_ativo: "renda_fixa", tipo: "resgate", ativo_id: "12" })).toEqual({
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

  it("câmbio pago só fora do real (cadastrado ou novo); vazio = PTAX (null)", () => {
    const us = { tipo_ativo: "acao_us", ativo_id: "11", quantidade: "10", preco_unitario: "100" };
    expect(validar(us).data?.cambio).toBeNull();
    expect(validar({ ...us, cambio: "5,4321" }).data?.cambio).toBe("5.4321");
    expect(errosPorCampo({ ...us, cambio: "5,1234567" })).toEqual({
      cambio: "Use no máximo 6 casas decimais.",
    });
    const etfNovo = validar({
      tipo_ativo: "etf_us",
      modo_ativo: "novo",
      ativo_id: "",
      novo_ativo: novo("etf_us", { simbolo: "SPY", nome: "SPDR S&P 500", moeda: "USD" }),
      quantidade: "1",
      preco_unitario: "500",
      cambio: "5",
    });
    expect(etfNovo.data?.cambio).toBe("5");
    // Ativo em BRL: um câmbio esquecido no campo oculto não vai para a API.
    expect(validar({ quantidade: "1", preco_unitario: "1", cambio: "5" }).data).not.toHaveProperty(
      "cambio",
    );
  });

  it("operação que o tipo de ativo não aceita", () => {
    expect(errosPorCampo({ tipo: "aporte", valor: "10" })).toEqual({
      tipo: "Ação (Brasil) não aceita aporte.",
    });
  });

  it("tipos sem taxas (renda fixa, Tesouro) não mandam taxas", () => {
    expect(
      validar({ tipo_ativo: "renda_fixa", tipo: "aporte", ativo_id: "12", valor: "1", taxas: "9" })
        .data?.taxas,
    ).toBe("0");
  });

  it("operação aceita ao trocar de tipo", () => {
    expect(operacaoAceita(tipo("renda_fixa"), "compra")).toBe("aporte");
    expect(operacaoAceita(tipo("acao_br"), "venda")).toBe("venda");
    expect(operacaoAceita(tipo("cripto"), "provento")).toBe("compra");
    expect(operacaoAceita(undefined, "venda")).toBe("venda");
  });

  it("edição: corpo do PUT sem os campos de cadastro", () => {
    const r = validar({ quantidade: "1", preco_unitario: "2" });
    expect(r.data).toBeDefined();
    if (!r.data) return;
    const corpo = paraTransacaoEntrada({ ...r.data, usar_ativo_id: 3 }, 10);
    expect(corpo).toMatchObject({ ativo_id: 10, quantidade: "1", preco_unitario: "2" });
    expect(corpo).not.toHaveProperty("novo_ativo");
    expect(corpo).not.toHaveProperty("usar_ativo_id");
    expect(corpo).not.toHaveProperty("confirmar_novo");
  });

  it("valores iniciais da edição vêm da API com vírgula", () => {
    const v = valoresIniciais(
      "2026-10-29",
      {
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
      },
      tipo("acao_us"),
    );
    expect(v).toMatchObject({
      tipo_ativo: "acao_us",
      modo_ativo: "existente",
      ativo_id: "11",
      preco_unitario: "100,5",
      taxas: "1",
      cambio: "5",
      imposto_retido: "",
    });
  });
});
