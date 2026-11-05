import { ehCategoria, type IdCategoria } from "./categorias";
import { extrairLinks } from "./links";

/** Um verbete do glossário, já lido do arquivo `conteudo/<slug>.md`. */
export interface Termo {
  slug: string;
  titulo: string;
  categoria: IdCategoria;
  sinonimos: string[];
  resumo: string;
  revisadoEm: string; // AAAA-MM
  corpo: string; // Markdown sem o frontmatter
  links: string[]; // slugs citados no corpo, sem repetição, na ordem em que aparecem
}

export interface ResultadoLeitura {
  termo: Termo | null;
  erros: string[];
}

/** Seções `##` obrigatórias de todo verbete, nesta ordem. */
export const SECOES_VERBETE = ["Em uma a três frases", "Como funciona", "Exemplo", "Atenção"];

export const PALAVRAS_MINIMAS = 150;
export const PALAVRAS_MAXIMAS = 350;

const FORMATO_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const FORMATO_REVISAO = /^\d{4}-(0[1-9]|1[0-2])$/;
const CAMPOS_CONHECIDOS = new Set(["titulo", "categoria", "sinonimos", "resumo", "revisado_em"]);

export function slugValido(slug: string): boolean {
  return FORMATO_SLUG.test(slug);
}

/**
 * Separa o frontmatter (`---` ... `---` no topo) do corpo. O formato é restrito de
 * propósito: uma linha `chave: valor` por campo, sem aspas nem listas YAML. Assim o
 * parser cabe em poucas linhas e não depende de bibliotecas do Node.
 */
export function separarFrontmatter(bruto: string): {
  campos: Map<string, string>;
  corpo: string;
  erros: string[];
} {
  // Sem o BOM (U+FEFF) que alguns editores do Windows gravam no início do arquivo.
  const semBom = bruto.charCodeAt(0) === 0xfeff ? bruto.slice(1) : bruto;
  const texto = semBom.replace(/\r\n?/g, "\n");
  const campos = new Map<string, string>();
  const erros: string[] = [];
  const blocos = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(texto);
  if (!blocos) {
    return {
      campos,
      corpo: texto,
      erros: ["frontmatter ausente (o arquivo deve começar com ---)"],
    };
  }
  const [, cabecalho = "", corpo = ""] = blocos;
  for (const linha of cabecalho.split("\n")) {
    if (!linha.trim()) continue;
    const separador = linha.indexOf(":");
    if (separador <= 0) {
      erros.push(`linha inválida no frontmatter: "${linha}"`);
      continue;
    }
    const chave = linha.slice(0, separador).trim();
    const valor = linha.slice(separador + 1).trim();
    if (!CAMPOS_CONHECIDOS.has(chave)) erros.push(`campo desconhecido no frontmatter: "${chave}"`);
    else if (campos.has(chave)) erros.push(`campo repetido no frontmatter: "${chave}"`);
    else campos.set(chave, valor);
  }
  return { campos, corpo: corpo.trim(), erros };
}

/** Lê um arquivo de verbete. Com erro, devolve `termo: null` e a lista de problemas. */
export function lerTermo(slug: string, bruto: string): ResultadoLeitura {
  const { campos, corpo, erros } = separarFrontmatter(bruto);
  if (!slugValido(slug)) {
    erros.push(`slug "${slug}" fora do formato (minúsculas, sem acento, separadas por hífen)`);
  }
  const obrigatorio = (chave: string): string => {
    const valor = campos.get(chave) ?? "";
    if (!valor) erros.push(`campo obrigatório ausente: "${chave}"`);
    return valor;
  };
  const titulo = obrigatorio("titulo");
  const categoria = obrigatorio("categoria");
  const resumo = obrigatorio("resumo");
  const revisadoEm = obrigatorio("revisado_em");
  if (categoria && !ehCategoria(categoria)) erros.push(`categoria inválida: "${categoria}"`);
  if (revisadoEm && !FORMATO_REVISAO.test(revisadoEm)) {
    erros.push(`revisado_em fora do formato AAAA-MM: "${revisadoEm}"`);
  }
  if (!corpo) erros.push("corpo vazio");
  if (erros.length > 0 || !ehCategoria(categoria)) return { termo: null, erros };

  const sinonimos = (campos.get("sinonimos") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    termo: {
      slug,
      titulo,
      categoria,
      sinonimos,
      resumo,
      revisadoEm,
      corpo,
      links: extrairLinks(corpo),
    },
    erros,
  };
}

/** "2026-11" → "novembro de 2026" (data de revisão mostrada no verbete). */
export function formatarRevisao(revisadoEm: string): string {
  const [ano, mes] = revisadoEm.split("-").map(Number);
  if (!ano || !mes) return revisadoEm;
  return new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(
    new Date(ano, mes - 1, 1),
  );
}

/** Títulos das seções `##` do corpo, na ordem (subseções `###` não contam). */
export function secoesDoCorpo(corpo: string): string[] {
  return [...corpo.matchAll(/^##\s+(.+?)\s*$/gm)].map((m) => m[1] ?? "");
}

/**
 * Palavras do texto como um leitor as conta: sem a marcação do Markdown (#, |, *, -, >),
 * com `[[slug|texto]]` contando só o texto exibido.
 */
export function contarPalavras(corpo: string): number {
  const texto = corpo
    .replace(
      /\[\[([^\]|\\]+)(?:\\?\|([^\]]+))?\]\]/g,
      (_, slug: string, exibido?: string) => exibido ?? slug.replace(/-/g, " "),
    )
    .replace(/[#|*_>`]/g, " ")
    .replace(/(^|\s)-{1,}(?=\s)/g, " ");
  return texto.split(/\s+/).filter((p) => /[\p{L}\p{N}]/u.test(p)).length;
}
