import {
  contarPalavras,
  lerTermo,
  PALAVRAS_MAXIMAS,
  PALAVRAS_MINIMAS,
  SECOES_VERBETE,
  secoesDoCorpo,
  type Termo,
} from "./termo";

export interface ArquivoTermo {
  slug: string;
  bruto: string;
}

/**
 * Confere todo o conteúdo do glossário e devolve a lista de problemas (vazia = tudo certo).
 * Roda como teste sobre os arquivos reais: um termo novo com erro faz o `npm test` falhar
 * com a mensagem apontando o arquivo.
 */
export function validarConteudo(arquivos: readonly ArquivoTermo[]): string[] {
  const erros: string[] = [];
  const termos: Termo[] = [];
  const slugs = new Set<string>();
  const titulos = new Map<string, string>();

  for (const { slug, bruto } of arquivos) {
    const local = `${slug}.md`;
    if (slugs.has(slug)) erros.push(`${local}: slug repetido`);
    slugs.add(slug);
    const { termo, erros: errosLeitura } = lerTermo(slug, bruto);
    erros.push(...errosLeitura.map((e) => `${local}: ${e}`));
    if (!termo) continue;
    termos.push(termo);

    const chaveTitulo = termo.titulo.toLocaleLowerCase("pt-BR");
    const outro = titulos.get(chaveTitulo);
    if (outro) erros.push(`${local}: título "${termo.titulo}" igual ao de ${outro}.md`);
    titulos.set(chaveTitulo, slug);

    const secoes = secoesDoCorpo(termo.corpo);
    if (secoes.join("|") !== SECOES_VERBETE.join("|")) {
      erros.push(
        `${local}: seções devem ser exatamente ${SECOES_VERBETE.map((s) => `"## ${s}"`).join(", ")} nesta ordem (encontradas: ${secoes.map((s) => `"${s}"`).join(", ") || "nenhuma"})`,
      );
    }
    const palavras = contarPalavras(termo.corpo);
    if (palavras < PALAVRAS_MINIMAS || palavras > PALAVRAS_MAXIMAS) {
      erros.push(
        `${local}: ${String(palavras)} palavras (o verbete deve ter de ${String(PALAVRAS_MINIMAS)} a ${String(PALAVRAS_MAXIMAS)})`,
      );
    }
  }

  const ligados = new Set<string>();
  for (const termo of termos) {
    for (const alvo of termo.links) {
      if (alvo === termo.slug) {
        erros.push(`${termo.slug}.md: o termo cita a si mesmo ([[${alvo}]])`);
      } else if (!slugs.has(alvo)) {
        erros.push(`${termo.slug}.md: link quebrado [[${alvo}]] (não existe ${alvo}.md)`);
      } else {
        ligados.add(termo.slug);
        ligados.add(alvo);
      }
    }
  }
  for (const termo of termos) {
    if (!ligados.has(termo.slug)) {
      erros.push(`${termo.slug}.md: termo isolado (não cita nem é citado por nenhum outro)`);
    }
  }
  return erros;
}
