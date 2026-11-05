import { montarIndice, type IndiceGlossario } from "../dominio/indice";
import { lerTermo, type Termo } from "../dominio/termo";
import type { ArquivoTermo } from "../dominio/validacao";

/**
 * Conteúdo fixo do glossário: um arquivo `<slug>.md` por termo nesta pasta, embutido no
 * build pelo Vite (texto puro, sem rede e sem banco). Para acrescentar um termo basta criar
 * o arquivo no modelo dos outros; o teste de conteúdo confere formato e links.
 */
const BRUTOS = import.meta.glob<string>("./*.md", {
  query: "?raw",
  import: "default",
  eager: true,
});

export const ARQUIVOS: readonly ArquivoTermo[] = Object.entries(BRUTOS)
  .map(([caminho, bruto]) => ({ slug: caminho.replace(/^\.\//, "").replace(/\.md$/, ""), bruto }))
  .sort((a, b) => a.slug.localeCompare(b.slug));

// Um arquivo com erro fica de fora em vez de derrubar a tela (o teste de conteúdo o aponta).
const TERMOS: Termo[] = ARQUIVOS.map((a) => lerTermo(a.slug, a.bruto).termo).filter(
  (t): t is Termo => t !== null,
);

export const GLOSSARIO: IndiceGlossario = montarIndice(TERMOS);
