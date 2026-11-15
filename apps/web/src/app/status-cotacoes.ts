/**
 * Chip e painel de status das cotações (Parte 5A, decisão 10; painel em 15/11/2026): só
 * ativos com posição aberta. A situação de cada ativo vem pronta do backend
 * (`situacao`, prioridade erro > manual > defasado > em dia); aqui só contamos e ordenamos.
 */
export type Situacao = "em_dia" | "defasado" | "com_erro" | "manual";

export interface StatusParaContagem {
  ativo_id: number;
  situacao: Situacao;
}

export interface ContagemStatus {
  emDia: number;
  defasadas: number;
  comErro: number;
  manuais: number;
}

const CHAVE_CONTAGEM: Record<Situacao, keyof ContagemStatus> = {
  em_dia: "emDia",
  defasado: "defasadas",
  com_erro: "comErro",
  manual: "manuais",
};

/** Ordem das seções do painel: o que pede atenção primeiro. */
export const ORDEM_SITUACOES: readonly Situacao[] = ["com_erro", "defasado", "manual", "em_dia"];

export const TITULO_SITUACAO: Record<Situacao, string> = {
  com_erro: "Com erro",
  defasado: "Defasados",
  manual: "Manuais",
  em_dia: "Em dia",
};

/** Classe de fundo (token) da bolinha de cada situação. */
export const COR_SITUACAO: Record<Situacao, string> = {
  com_erro: "bg-perigo",
  defasado: "bg-aviso",
  manual: "bg-muted-foreground",
  em_dia: "bg-sucesso",
};

export function soAbertos<T extends StatusParaContagem>(
  status: readonly T[],
  abertos: ReadonlySet<number>,
): T[] {
  return status.filter((item) => abertos.has(item.ativo_id));
}

export function contarStatus(
  status: readonly StatusParaContagem[],
  abertos: ReadonlySet<number>,
): ContagemStatus {
  const contagem: ContagemStatus = { emDia: 0, defasadas: 0, comErro: 0, manuais: 0 };
  for (const item of soAbertos(status, abertos)) contagem[CHAVE_CONTAGEM[item.situacao]] += 1;
  return contagem;
}

export function quantidade(contagem: ContagemStatus, situacao: Situacao): number {
  return contagem[CHAVE_CONTAGEM[situacao]];
}

/** Partes do chip, sem as categorias zeradas (tudo zero: "0 em dia"). */
export function partesStatus({
  emDia,
  defasadas,
  comErro,
  manuais,
}: ContagemStatus): { situacao: Situacao; texto: string }[] {
  const partes: { situacao: Situacao; texto: string }[] = [];
  if (emDia > 0) partes.push({ situacao: "em_dia", texto: `${emDia} em dia` });
  if (defasadas > 0)
    partes.push({
      situacao: "defasado",
      texto: `${defasadas} ${defasadas === 1 ? "defasada" : "defasadas"}`,
    });
  if (comErro > 0) partes.push({ situacao: "com_erro", texto: `${comErro} com erro` });
  if (manuais > 0)
    partes.push({
      situacao: "manual",
      texto: `${manuais} ${manuais === 1 ? "manual" : "manuais"}`,
    });
  return partes.length > 0 ? partes : [{ situacao: "em_dia", texto: "0 em dia" }];
}

/** "N em dia · N defasadas · N com erro · N manuais". */
export function textoStatus(contagem: ContagemStatus): string {
  return partesStatus(contagem)
    .map((p) => p.texto)
    .join(" · ");
}

/** Rótulo curto de uma linha do painel: símbolo (ou nome, para renda fixa e poupança). */
export function rotuloStatus(item: { simbolo?: string | null; nome: string }): string {
  return item.simbolo ?? item.nome;
}

/** Itens agrupados na ordem do painel; dentro do grupo, pelo rótulo (ordem alfabética pt-BR). */
export function agruparPorSituacao<T extends StatusParaContagem>(
  itens: readonly T[],
  rotulo: (item: T) => string,
): { situacao: Situacao; itens: T[] }[] {
  return ORDEM_SITUACOES.map((situacao) => ({
    situacao,
    itens: itens
      .filter((i) => i.situacao === situacao)
      .sort((a, b) => rotulo(a).localeCompare(rotulo(b), "pt-BR")),
  })).filter((grupo) => grupo.itens.length > 0);
}

/** Ids a mandar para `POST /api/cotacoes/atualizar-ativos` (só uma situação). */
export function idsDaSituacao(itens: readonly StatusParaContagem[], situacao: Situacao): number[] {
  return itens.filter((i) => i.situacao === situacao).map((i) => i.ativo_id);
}
