import { intervaloDoPeriodo, isoValida, PERIODO_PADRAO, PERIODOS, type Periodo } from "@/lib/datas";

/**
 * Filtros do Histórico de operações, guardados na **URL** (query string) para manter o
 * estado ao trocar de tela e voltar. Funções puras: ler/gravar a URL, montar a consulta
 * da API e listar as etiquetas removíveis.
 */
export const OPERACOES = ["compra", "aporte", "venda", "resgate", "provento"] as const;
export type Operacao = (typeof OPERACOES)[number];

export const NOMES_OPERACAO: Record<Operacao, string> = {
  compra: "Compra",
  aporte: "Aporte",
  venda: "Venda",
  resgate: "Resgate",
  provento: "Provento",
};

/** Cor de cada operação (selo e gráfico), sempre por token. */
export const CLASSES_OPERACAO: Record<Operacao, { selo: string; ponto: string }> = {
  compra: { selo: "border-grafico-4 bg-grafico-4/15", ponto: "bg-grafico-4" },
  aporte: { selo: "border-grafico-1 bg-grafico-1/15", ponto: "bg-grafico-1" },
  venda: { selo: "border-grafico-3 bg-grafico-3/15", ponto: "bg-grafico-3" },
  resgate: { selo: "border-grafico-6 bg-grafico-6/15", ponto: "bg-grafico-6" },
  provento: { selo: "border-grafico-5 bg-grafico-5/15", ponto: "bg-grafico-5" },
};

export type Situacao = "" | "aberta" | "encerrada";
export type CampoOrdem =
  | "data"
  | "operacao"
  | "ativo"
  | "instituicao"
  | "quantidade"
  | "preco_unitario"
  | "taxas"
  | "valor_total"
  | "resultado";
export type Direcao = "asc" | "desc";
export type Visao = "operacoes" | "ativos";

export interface FiltrosHistorico {
  busca: string;
  tipoAtivo: string;
  instituicaoId: number | null;
  operacoes: Operacao[];
  periodo: Periodo;
  inicio: string | null; // só no período personalizado
  fim: string | null;
  moeda: string;
  situacao: Situacao;
  apenasPrejuizo: boolean;
  apenasComCustos: boolean;
}

export interface EstadoHistorico {
  filtros: FiltrosHistorico;
  ordem: CampoOrdem;
  direcao: Direcao;
  pagina: number;
  visao: Visao;
}

export const FILTROS_PADRAO: FiltrosHistorico = {
  busca: "",
  tipoAtivo: "",
  instituicaoId: null,
  operacoes: [...OPERACOES],
  periodo: PERIODO_PADRAO,
  inicio: null,
  fim: null,
  moeda: "",
  situacao: "",
  apenasPrejuizo: false,
  apenasComCustos: false,
};

const CAMPOS_ORDEM: readonly CampoOrdem[] = [
  "data",
  "operacao",
  "ativo",
  "instituicao",
  "quantidade",
  "preco_unitario",
  "taxas",
  "valor_total",
  "resultado",
];

/** Parâmetros da URL que pertencem ao histórico (o resto, como `aba`, é preservado). */
const PARAMETROS = [
  "busca",
  "tipo_ativo",
  "instituicao",
  "ops",
  "periodo",
  "inicio",
  "fim",
  "moeda",
  "situacao",
  "prejuizo",
  "custos",
  "ordem",
  "direcao",
  "pagina",
  "visao",
] as const;

export function lerEstado(params: URLSearchParams): EstadoHistorico {
  const ops = params.get("ops");
  const operacoes =
    ops === null ? [...OPERACOES] : OPERACOES.filter((o) => ops.split(",").includes(o));
  const periodoBruto = params.get("periodo");
  const periodo = PERIODOS.some((p) => p.valor === periodoBruto)
    ? (periodoBruto as Periodo)
    : PERIODO_PADRAO;
  const instituicao = Number(params.get("instituicao"));
  const situacao = params.get("situacao");
  const ordem = params.get("ordem") as CampoOrdem | null;
  const pagina = Number(params.get("pagina"));
  const inicio = params.get("inicio");
  const fim = params.get("fim");
  return {
    filtros: {
      busca: params.get("busca") ?? "",
      tipoAtivo: params.get("tipo_ativo") ?? "",
      instituicaoId: Number.isInteger(instituicao) && instituicao > 0 ? instituicao : null,
      operacoes,
      periodo,
      inicio: periodo === "personalizado" && isoValida(inicio) ? inicio : null,
      fim: periodo === "personalizado" && isoValida(fim) ? fim : null,
      moeda: params.get("moeda") ?? "",
      situacao: situacao === "aberta" || situacao === "encerrada" ? situacao : "",
      apenasPrejuizo: params.get("prejuizo") === "1",
      apenasComCustos: params.get("custos") === "1",
    },
    ordem: ordem && CAMPOS_ORDEM.includes(ordem) ? ordem : "data",
    direcao: params.get("direcao") === "asc" ? "asc" : "desc",
    pagina: Number.isInteger(pagina) && pagina > 0 ? pagina : 1,
    visao: params.get("visao") === "ativos" ? "ativos" : "operacoes",
  };
}

/** Grava o estado na URL omitindo os valores padrão (URL curta e legível). */
export function gravarEstado(estado: EstadoHistorico, base: URLSearchParams): URLSearchParams {
  const params = new URLSearchParams(base);
  for (const nome of PARAMETROS) params.delete(nome);
  const { filtros: f } = estado;
  if (f.busca.trim()) params.set("busca", f.busca.trim());
  if (f.tipoAtivo) params.set("tipo_ativo", f.tipoAtivo);
  if (f.instituicaoId !== null) params.set("instituicao", String(f.instituicaoId));
  if (f.operacoes.length !== OPERACOES.length) params.set("ops", f.operacoes.join(","));
  if (f.periodo !== PERIODO_PADRAO) params.set("periodo", f.periodo);
  if (f.periodo === "personalizado") {
    if (f.inicio) params.set("inicio", f.inicio);
    if (f.fim) params.set("fim", f.fim);
  }
  if (f.moeda) params.set("moeda", f.moeda);
  if (f.situacao) params.set("situacao", f.situacao);
  if (f.apenasPrejuizo) params.set("prejuizo", "1");
  if (f.apenasComCustos) params.set("custos", "1");
  if (estado.ordem !== "data") params.set("ordem", estado.ordem);
  if (estado.direcao !== "desc") params.set("direcao", estado.direcao);
  if (estado.pagina > 1) params.set("pagina", String(estado.pagina));
  if (estado.visao !== "operacoes") params.set("visao", estado.visao);
  return params;
}

export interface ConsultaHistorico {
  busca?: string;
  tipo_ativo?: string;
  instituicao_id?: number;
  tipos?: Operacao[];
  inicio?: string;
  fim?: string;
  moeda?: string;
  situacao?: "aberta" | "encerrada";
  apenas_prejuizo?: boolean;
  apenas_com_custos?: boolean;
}

/**
 * Filtros no formato da API. Devolve `null` quando nenhuma operação está marcada (a API
 * entende lista vazia como "todas", então nem consultamos: o resultado é vazio).
 */
export function consultaDaApi(filtros: FiltrosHistorico, agora: Date): ConsultaHistorico | null {
  if (filtros.operacoes.length === 0) return null;
  const { inicio, fim } = intervaloDoPeriodo(filtros.periodo, agora, filtros);
  const consulta: ConsultaHistorico = {};
  if (filtros.busca.trim()) consulta.busca = filtros.busca.trim();
  if (filtros.tipoAtivo) consulta.tipo_ativo = filtros.tipoAtivo;
  if (filtros.instituicaoId !== null) consulta.instituicao_id = filtros.instituicaoId;
  if (filtros.operacoes.length !== OPERACOES.length) consulta.tipos = filtros.operacoes;
  if (inicio) consulta.inicio = inicio;
  if (fim) consulta.fim = fim;
  if (filtros.moeda) consulta.moeda = filtros.moeda;
  if (filtros.situacao) consulta.situacao = filtros.situacao;
  if (filtros.apenasPrejuizo) consulta.apenas_prejuizo = true;
  if (filtros.apenasComCustos) consulta.apenas_com_custos = true;
  return consulta;
}

export interface Etiqueta {
  chave: string;
  texto: string;
  remover: (f: FiltrosHistorico) => FiltrosHistorico;
}

/** Etiquetas removíveis ("×") dos filtros diferentes do padrão. */
export function etiquetasDosFiltros(
  f: FiltrosHistorico,
  nomes: { tipoAtivo: (slug: string) => string; instituicao: (id: number) => string },
): Etiqueta[] {
  const etiquetas: Etiqueta[] = [];
  if (f.busca.trim()) {
    etiquetas.push({
      chave: "busca",
      texto: `Ativo: ${f.busca.trim()}`,
      remover: (x) => ({ ...x, busca: "" }),
    });
  }
  if (f.tipoAtivo) {
    etiquetas.push({
      chave: "tipo",
      texto: `Tipo: ${nomes.tipoAtivo(f.tipoAtivo)}`,
      remover: (x) => ({ ...x, tipoAtivo: "" }),
    });
  }
  if (f.instituicaoId !== null) {
    etiquetas.push({
      chave: "instituicao",
      texto: `Instituição: ${nomes.instituicao(f.instituicaoId)}`,
      remover: (x) => ({ ...x, instituicaoId: null }),
    });
  }
  if (f.operacoes.length !== OPERACOES.length) {
    const texto =
      f.operacoes.length === 0 ? "nenhuma" : f.operacoes.map((o) => NOMES_OPERACAO[o]).join(", ");
    etiquetas.push({
      chave: "operacoes",
      texto: `Operações: ${texto}`,
      remover: (x) => ({ ...x, operacoes: [...OPERACOES] }),
    });
  }
  if (f.periodo !== PERIODO_PADRAO) {
    const rotulo = PERIODOS.find((p) => p.valor === f.periodo)?.rotulo ?? f.periodo;
    etiquetas.push({
      chave: "periodo",
      texto: `Período: ${rotulo}`,
      remover: (x) => ({ ...x, periodo: PERIODO_PADRAO, inicio: null, fim: null }),
    });
  }
  if (f.moeda) {
    etiquetas.push({
      chave: "moeda",
      texto: `Moeda: ${f.moeda}`,
      remover: (x) => ({ ...x, moeda: "" }),
    });
  }
  if (f.situacao) {
    etiquetas.push({
      chave: "situacao",
      texto: f.situacao === "aberta" ? "Ainda na carteira" : "Posição encerrada",
      remover: (x) => ({ ...x, situacao: "" }),
    });
  }
  if (f.apenasPrejuizo) {
    etiquetas.push({
      chave: "prejuizo",
      texto: "Só vendas com prejuízo",
      remover: (x) => ({ ...x, apenasPrejuizo: false }),
    });
  }
  if (f.apenasComCustos) {
    etiquetas.push({
      chave: "custos",
      texto: "Só com taxas ou imposto",
      remover: (x) => ({ ...x, apenasComCustos: false }),
    });
  }
  return etiquetas;
}
