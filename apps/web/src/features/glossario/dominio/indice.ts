import { IDS_CATEGORIA } from "./categorias";
import type { Termo } from "./termo";

/** Aresta não direcionada, com as pontas em ordem alfabética (`a < b`). */
export interface Aresta {
  a: string;
  b: string;
}

export interface IndiceGlossario {
  /** Termos ordenados por categoria (ordem fixa) e depois por título. */
  termos: Termo[];
  porSlug: Map<string, Termo>;
  /** Vizinhos de cada termo: quem ele cita e quem cita ele (links para termos existentes). */
  vizinhos: Map<string, Set<string>>;
  arestas: Aresta[];
}

const COMPARADOR_TITULO = new Intl.Collator("pt-BR", { sensitivity: "base" });

export function compararTitulos(a: string, b: string): number {
  return COMPARADOR_TITULO.compare(a, b);
}

/**
 * Monta o índice a partir dos termos lidos. As arestas saem dos `[[links]]`: A cita B
 * (ou B cita A, ou os dois) gera uma aresta só. Links para termos inexistentes e um termo
 * citando a si mesmo são ignorados aqui (a validação do conteúdo os aponta como erro).
 */
export function montarIndice(lista: readonly Termo[]): IndiceGlossario {
  const termos = [...lista].sort(
    (x, y) =>
      IDS_CATEGORIA.indexOf(x.categoria) - IDS_CATEGORIA.indexOf(y.categoria) ||
      compararTitulos(x.titulo, y.titulo),
  );
  const porSlug = new Map(termos.map((t) => [t.slug, t]));
  const vizinhos = new Map(termos.map((t) => [t.slug, new Set<string>()]));
  const chaves = new Set<string>();
  const arestas: Aresta[] = [];

  for (const termo of termos) {
    for (const alvo of termo.links) {
      if (alvo === termo.slug || !porSlug.has(alvo)) continue;
      vizinhos.get(termo.slug)?.add(alvo);
      vizinhos.get(alvo)?.add(termo.slug);
      const [a, b] = termo.slug < alvo ? [termo.slug, alvo] : [alvo, termo.slug];
      const chave = `${a}\u0000${b}`;
      if (!chaves.has(chave)) {
        chaves.add(chave);
        arestas.push({ a, b });
      }
    }
  }
  return { termos, porSlug, vizinhos, arestas };
}

/** Número de ligações do termo (define o tamanho da bolinha no grafo). */
export function grau(indice: IndiceGlossario, slug: string): number {
  return indice.vizinhos.get(slug)?.size ?? 0;
}

/** Termos relacionados a um verbete, em ordem alfabética de título. */
export function relacionados(indice: IndiceGlossario, slug: string): Termo[] {
  return [...(indice.vizinhos.get(slug) ?? [])]
    .map((s) => indice.porSlug.get(s))
    .filter((t): t is Termo => t !== undefined)
    .sort((x, y) => compararTitulos(x.titulo, y.titulo));
}
