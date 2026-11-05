import { readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { IDS_CATEGORIA } from "../dominio/categorias";
import { validarConteudo } from "../dominio/validacao";
import { ARQUIVOS, GLOSSARIO } from "./glossario";

/**
 * Confere os arquivos reais do glossário. Se um termo novo tiver erro (link quebrado,
 * seção faltando, categoria inválida, tamanho fora do modelo…), a mensagem aponta o arquivo.
 */
describe("conteúdo do glossário", () => {
  it("todos os arquivos seguem o modelo, sem links quebrados nem termos isolados", () => {
    expect(validarConteudo(ARQUIVOS)).toEqual([]);
  });

  it("todo arquivo vira um termo do índice", () => {
    expect(GLOSSARIO.termos).toHaveLength(ARQUIVOS.length);
  });

  it("o índice enxerga todos os .md da pasta (sem lista antiga em cache)", () => {
    // Lido direto do disco: se o cache do Vitest congelasse o import.meta.glob, um termo
    // novo ficaria de fora da validação sem ninguém perceber (ver vite.config.ts).
    const noDisco = readdirSync(import.meta.dirname)
      .filter((nome) => nome.endsWith(".md"))
      .map((nome) => nome.replace(/\.md$/, ""))
      .sort();
    expect(ARQUIVOS.map((a) => a.slug).sort()).toEqual(noDisco);
  });

  it("todas as seis categorias têm termos", () => {
    const usadas = new Set(GLOSSARIO.termos.map((t) => t.categoria));
    expect([...usadas].sort()).toEqual([...IDS_CATEGORIA].sort());
  });
});
