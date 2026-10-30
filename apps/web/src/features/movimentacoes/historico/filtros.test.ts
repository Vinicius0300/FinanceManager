import { describe, expect, it } from "vitest";
import {
  consultaDaApi,
  etiquetasDosFiltros,
  FILTROS_PADRAO,
  gravarEstado,
  lerEstado,
  OPERACOES,
  type EstadoHistorico,
} from "./filtros";
import { agruparPorMes } from "./rotulos";
import type { Operacao } from "./consultas";

const AGORA = new Date(2026, 9, 29, 12);
const PADRAO: EstadoHistorico = {
  filtros: FILTROS_PADRAO,
  ordem: "data",
  direcao: "desc",
  pagina: 1,
  visao: "operacoes",
};
const NOMES = { tipoAtivo: (s: string) => `T:${s}`, instituicao: (i: number) => `I:${i}` };

describe("filtros do histórico na URL", () => {
  it("URL vazia = padrão (todas as operações, últimos 12 meses, data desc)", () => {
    expect(lerEstado(new URLSearchParams())).toEqual(PADRAO);
  });

  it("o padrão não polui a URL e preserva outros parâmetros (aba)", () => {
    const params = gravarEstado(PADRAO, new URLSearchParams("aba=caixa&busca=velha"));
    expect(params.toString()).toBe("aba=caixa");
  });

  it("ida e volta de todos os filtros", () => {
    const estado: EstadoHistorico = {
      filtros: {
        busca: "petr",
        tipoAtivo: "acao_br",
        instituicaoId: 1,
        operacoes: ["venda", "resgate"],
        periodo: "personalizado",
        inicio: "2026-01-01",
        fim: "2026-06-30",
        moeda: "BRL",
        situacao: "encerrada",
        apenasPrejuizo: true,
        apenasComCustos: true,
      },
      ordem: "resultado",
      direcao: "asc",
      pagina: 3,
      visao: "ativos",
    };
    const params = gravarEstado(estado, new URLSearchParams());
    expect(params.get("ops")).toBe("venda,resgate");
    expect(lerEstado(params)).toEqual(estado);
  });

  it("valores inválidos na URL voltam ao padrão", () => {
    const estado = lerEstado(
      new URLSearchParams(
        "periodo=semana&instituicao=abc&situacao=talvez&ordem=cor&pagina=-2&ops=compra,doacao&inicio=2026-01-01",
      ),
    );
    expect(estado.filtros.periodo).toBe("12m");
    expect(estado.filtros.instituicaoId).toBeNull();
    expect(estado.filtros.situacao).toBe("");
    expect(estado.filtros.operacoes).toEqual(["compra"]);
    expect(estado.filtros.inicio).toBeNull(); // só vale no período personalizado
    expect(estado.ordem).toBe("data");
    expect(estado.pagina).toBe(1);
  });

  it("nenhuma operação marcada fica registrada na URL (ops vazio)", () => {
    const vazio = { ...PADRAO, filtros: { ...FILTROS_PADRAO, operacoes: [] } };
    const params = gravarEstado(vazio, new URLSearchParams());
    expect(params.get("ops")).toBe("");
    expect(lerEstado(params).filtros.operacoes).toEqual([]);
  });
});

describe("consulta da API", () => {
  it("padrão: só o período de 12 meses (todas as operações = sem `tipos`)", () => {
    expect(consultaDaApi(FILTROS_PADRAO, AGORA)).toEqual({
      inicio: "2025-11-01",
      fim: "2026-10-29",
    });
  });

  it("todos os filtros no formato da API", () => {
    expect(
      consultaDaApi(
        {
          ...FILTROS_PADRAO,
          busca: "  wege ",
          tipoAtivo: "acao_br",
          instituicaoId: 2,
          operacoes: ["compra", "aporte"],
          periodo: "tudo",
          moeda: "USD",
          situacao: "aberta",
          apenasPrejuizo: true,
          apenasComCustos: true,
        },
        AGORA,
      ),
    ).toEqual({
      busca: "wege",
      tipo_ativo: "acao_br",
      instituicao_id: 2,
      tipos: ["compra", "aporte"],
      moeda: "USD",
      situacao: "aberta",
      apenas_prejuizo: true,
      apenas_com_custos: true,
    });
  });

  it("sem operação marcada não consulta (a API trataria lista vazia como todas)", () => {
    expect(consultaDaApi({ ...FILTROS_PADRAO, operacoes: [] }, AGORA)).toBeNull();
  });
});

describe("etiquetas removíveis", () => {
  it("só os filtros diferentes do padrão viram etiqueta", () => {
    expect(etiquetasDosFiltros(FILTROS_PADRAO, NOMES)).toEqual([]);
    const filtros = {
      ...FILTROS_PADRAO,
      tipoAtivo: "acao_br",
      instituicaoId: 1,
      operacoes: OPERACOES.filter((o) => o !== "provento"),
      periodo: "ano" as const,
    };
    const etiquetas = etiquetasDosFiltros(filtros, NOMES);
    expect(etiquetas.map((e) => e.texto)).toEqual([
      "Tipo: T:acao_br",
      "Instituição: I:1",
      "Operações: Compra, Aporte, Venda, Resgate",
      "Período: Este ano",
    ]);
  });

  it("remover uma etiqueta volta só aquele filtro ao padrão", () => {
    const filtros = { ...FILTROS_PADRAO, instituicaoId: 1, apenasPrejuizo: true };
    const [instituicao, prejuizo] = etiquetasDosFiltros(filtros, NOMES);
    expect(instituicao?.remover(filtros)).toEqual({ ...filtros, instituicaoId: null });
    expect(prejuizo?.remover(filtros)).toEqual({ ...filtros, apenasPrejuizo: false });
  });
});

describe("agrupamento por mês da tabela", () => {
  const op = (id: number, data: string) => ({ id, data }) as Operacao;

  it("respeita a ordem recebida e conta por mês", () => {
    const grupos = agruparPorMes([
      op(1, "2026-10-24"),
      op(2, "2026-10-08"),
      op(3, "2026-07-22"),
      op(4, "2026-02-03"),
    ]);
    expect(grupos.map((g) => [g.mes, g.itens.map((i) => i.id)])).toEqual([
      ["2026-10-01", [1, 2]],
      ["2026-07-01", [3]],
      ["2026-02-01", [4]],
    ]);
  });
});
