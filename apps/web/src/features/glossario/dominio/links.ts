/**
 * Links no estilo do Obsidian: `[[slug]]` ou `[[slug|texto exibido]]`. Dentro de tabelas
 * Markdown a barra separa colunas, então lá o link usa `[[slug\|texto]]` (como no próprio
 * Obsidian); as duas formas são aceitas em qualquer lugar.
 */
const PADRAO_LINK = /\[\[([^\]|\\]+?)\s*(?:\\?\|\s*([^\]]+?)\s*)?\]\]/g;

/** Prefixo das rotas de verbete (também usado pela tela para reconhecer links internos). */
export const ROTA_GLOSSARIO = "/glossario";

export function rotaDoTermo(slug: string): string {
  return `${ROTA_GLOSSARIO}/${slug}`;
}

/** Slugs citados no texto, sem repetição, na ordem da primeira citação. */
export function extrairLinks(corpo: string): string[] {
  const vistos = new Set<string>();
  for (const [, slug = ""] of corpo.matchAll(PADRAO_LINK)) {
    vistos.add(slug.trim());
  }
  return [...vistos];
}

/**
 * Troca os `[[links]]` por links Markdown comuns para a rota do verbete. O texto exibido é
 * o informado no link ou, sem ele, o título do termo. Link para termo inexistente vira
 * texto simples (a validação do conteúdo impede isso; aqui é só para nunca quebrar a tela).
 */
export function converterLinks(
  corpo: string,
  tituloDe: (slug: string) => string | undefined,
): string {
  return corpo.replace(PADRAO_LINK, (_, bruto: string, exibido?: string) => {
    const slug = bruto.trim();
    const titulo = tituloDe(slug);
    const texto = escaparTextoLink(exibido ?? titulo ?? slug);
    return titulo === undefined ? texto : `[${texto}](${rotaDoTermo(slug)})`;
  });
}

/** Colchetes e barras no texto exibido quebrariam o link ou a tabela do Markdown. */
function escaparTextoLink(texto: string): string {
  return texto.replace(/([[\]|])/g, "\\$1");
}
