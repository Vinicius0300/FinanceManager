import { describe, expect, it } from "vitest";
import { buscarTermos, normalizar } from "./busca";
import { CATEGORIAS, tokenCategoria } from "./categorias";
import { grau, montarIndice, relacionados } from "./indice";
import { ajustarProporcao, calcularPosicoes } from "./layout";
import { converterLinks, extrairLinks } from "./links";
import { contarPalavras, lerTermo, secoesDoCorpo, separarFrontmatter, type Termo } from "./termo";
import { validarConteudo } from "./validacao";

// ---------------------------------------------------------------- dados sintéticos

/** Corpo válido com N palavras de enchimento (o modelo exige de 150 a 350 palavras). */
function corpoValido(links: string[] = [], palavras = 160): string {
  const enchimento = Array.from({ length: palavras }, () => "palavra").join(" ");
  return [
    "## Em uma a três frases",
    enchimento,
    "## Como funciona",
    links.map((l) => `[[${l}]]`).join(" "),
    "## Exemplo",
    "R$ 100",
    "## Atenção",
    "fim",
  ].join("\n\n");
}

function arquivo(
  slug: string,
  campos: Record<string, string | undefined> = {}, // undefined tira o campo do arquivo
  corpo = corpoValido(),
): string {
  const valores: Record<string, string | undefined> = {
    titulo: slug.toUpperCase(),
    categoria: "indicadores",
    resumo: `Resumo de ${slug}.`,
    revisado_em: "2026-11",
    ...campos,
  };
  const cabecalho = Object.entries(valores)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${k}: ${v ?? ""}`)
    .join("\n");
  return `---\n${cabecalho}\n---\n\n${corpo}\n`;
}

function termo(slug: string, links: string[] = [], extra: Partial<Termo> = {}): Termo {
  return {
    slug,
    titulo: slug.toUpperCase(),
    categoria: "indicadores",
    sinonimos: [],
    resumo: "",
    revisadoEm: "2026-11",
    corpo: "",
    links,
    ...extra,
  };
}

// ---------------------------------------------------------------- frontmatter

describe("leitura do frontmatter", () => {
  it("lê os campos, os sinônimos separados por vírgula e o corpo sem o cabeçalho", () => {
    const bruto = arquivo("cdi", {
      titulo: "CDI",
      sinonimos: "DI, Taxa DI ,  Certificado de Depósito Interbancário",
      resumo: "Taxa: referência da renda fixa.", // dois-pontos no valor são preservados
    });
    const { termo: lido, erros } = lerTermo("cdi", bruto);
    expect(erros).toEqual([]);
    expect(lido).toMatchObject({
      slug: "cdi",
      titulo: "CDI",
      categoria: "indicadores",
      sinonimos: ["DI", "Taxa DI", "Certificado de Depósito Interbancário"],
      resumo: "Taxa: referência da renda fixa.",
      revisadoEm: "2026-11",
    });
    expect(lido?.corpo.startsWith("## Em uma a três frases")).toBe(true);
  });

  it("aceita quebra de linha do Windows e BOM no início do arquivo", () => {
    const bruto = String.fromCharCode(0xfeff) + arquivo("selic").replace(/\n/g, "\r\n");
    expect(lerTermo("selic", bruto).erros).toEqual([]);
  });

  it("sinônimos são opcionais", () => {
    expect(lerTermo("cdi", arquivo("cdi")).termo?.sinonimos).toEqual([]);
  });

  it("aponta campo obrigatório ausente", () => {
    const { termo: lido, erros } = lerTermo("cdi", arquivo("cdi", { resumo: undefined }));
    expect(lido).toBeNull();
    expect(erros).toContain('campo obrigatório ausente: "resumo"');
  });

  it("aponta categoria inválida, data fora do formato, campo desconhecido e repetido", () => {
    const bruto = arquivo("cdi", { categoria: "cripto", revisado_em: "11/2026" }).replace(
      "titulo: CDI",
      "titulo: CDI\ntitulo: Outro\ncor: azul",
    );
    const { erros } = lerTermo("cdi", bruto);
    expect(erros).toEqual(
      expect.arrayContaining([
        'categoria inválida: "cripto"',
        'revisado_em fora do formato AAAA-MM: "11/2026"',
        'campo desconhecido no frontmatter: "cor"',
        'campo repetido no frontmatter: "titulo"',
      ]),
    );
  });

  it("aponta arquivo sem frontmatter e slug fora do formato", () => {
    expect(separarFrontmatter("## Só corpo").erros).toEqual([
      "frontmatter ausente (o arquivo deve começar com ---)",
    ]);
    expect(lerTermo("Ação", arquivo("acao")).erros[0]).toMatch(/slug "Ação" fora do formato/);
  });
});

// ---------------------------------------------------------------- links

describe("links [[...]]", () => {
  it("extrai com e sem texto exibido, vários na mesma linha, sem repetir", () => {
    const corpo = "A [[selic]] e o [[cdi|CDI de hoje]] e de novo a [[ selic ]].";
    expect(extrairLinks(corpo)).toEqual(["selic", "cdi"]);
  });

  it("extrai link dentro de tabela, com a barra escapada", () => {
    const corpo = "| Coluna | Outra |\n|---|---|\n| [[ipca\\|inflação]] | [[cdb]] |";
    expect(extrairLinks(corpo)).toEqual(["ipca", "cdb"]);
  });

  it("converte para link Markdown da rota; sem texto usa o título; inexistente vira texto", () => {
    const titulos: Record<string, string> = { selic: "Selic", cdi: "CDI" };
    const corpo = "[[selic]], [[cdi|o DI]] e [[nada|algo]] e [[sumiu]]";
    expect(converterLinks(corpo, (s) => titulos[s])).toBe(
      "[Selic](/glossario/selic), [o DI](/glossario/cdi) e algo e sumiu",
    );
  });

  it("na tabela, o texto convertido não traz barra solta que quebre a coluna", () => {
    const convertido = converterLinks("| [[ipca\\|a|b]] |", () => "IPCA");
    expect(convertido).toBe("| [a\\|b](/glossario/ipca) |");
  });
});

// ---------------------------------------------------------------- índice e grafo

describe("índice", () => {
  // A cita B e C; B cita A (mesma aresta A–B); C cita X (inexistente) e a si mesmo.
  const indice = montarIndice([
    termo("a", ["b", "c"]),
    termo("b", ["a"]),
    termo("c", ["x", "c"]),
    termo("d", ["c"]),
    termo("e"),
  ]);

  it("arestas não direcionadas e sem duplicata; ignora link quebrado e autocitação", () => {
    expect(indice.arestas).toEqual([
      { a: "a", b: "b" },
      { a: "a", b: "c" },
      { a: "c", b: "d" },
    ]);
  });

  it("vizinhos incluem quem cita e quem é citado; grau é o número de vizinhos", () => {
    expect([...(indice.vizinhos.get("c") ?? [])].sort()).toEqual(["a", "d"]);
    expect(grau(indice, "a")).toBe(2);
    expect(grau(indice, "e")).toBe(0);
    expect(grau(indice, "nao-existe")).toBe(0);
  });

  it("relacionados em ordem alfabética de título", () => {
    expect(relacionados(indice, "c").map((t) => t.slug)).toEqual(["a", "d"]);
  });

  it("termos ordenados por categoria (ordem fixa) e depois por título, sem acento pesar", () => {
    const ordenado = montarIndice([
      termo("z", [], { categoria: "impostos", titulo: "Zeta" }),
      termo("b", [], { categoria: "conceitos", titulo: "Ética" }),
      termo("a", [], { categoria: "conceitos", titulo: "Ação" }),
    ]);
    expect(ordenado.termos.map((t) => t.titulo)).toEqual(["Ação", "Ética", "Zeta"]);
  });
});

describe("posições do grafo", () => {
  const slugs = ["a", "b", "c", "d"];
  const arestas = [
    { a: "a", b: "b" },
    { a: "b", b: "c" },
  ];

  it("é determinístico: mesma entrada, mesmas posições", () => {
    expect(calcularPosicoes(slugs, arestas)).toEqual(calcularPosicoes(slugs, arestas));
  });

  it("posições finitas, distintas e com nós ligados mais perto que os não ligados", () => {
    const pos = calcularPosicoes(slugs, arestas);
    const p = (s: string) => pos.get(s) ?? { x: NaN, y: NaN };
    const dist = (s: string, t: string) => Math.hypot(p(s).x - p(t).x, p(s).y - p(t).y);
    for (const s of slugs) {
      expect(Number.isFinite(p(s).x) && Number.isFinite(p(s).y)).toBe(true);
    }
    expect(dist("a", "b")).toBeGreaterThan(1);
    // a–b ligados; a–c a dois passos: a distância direta é maior.
    expect(dist("a", "b")).toBeLessThan(dist("a", "c"));
  });

  it("ajusta a proporção: só estica o eixo que precisa crescer", () => {
    const quadrado = new Map([
      ["a", { x: 0, y: 0 }],
      ["b", { x: 100, y: 100 }],
    ]);
    // 100 × 100 com proporção 2: largura vira 200 (x × 2), altura fica.
    expect(ajustarProporcao(quadrado, 2).get("b")).toEqual({ x: 200, y: 100 });
    // 400 × 100 (já mais largo que 2): altura vira 200 (y × 2), largura fica.
    const largo = new Map([
      ["a", { x: 0, y: 0 }],
      ["b", { x: 400, y: 100 }],
    ]);
    expect(ajustarProporcao(largo, 2).get("b")).toEqual({ x: 400, y: 200 });
    // Um nó só, ou todos alinhados, não mudam.
    const reta = new Map([
      ["a", { x: 0, y: 5 }],
      ["b", { x: 50, y: 5 }],
    ]);
    expect(ajustarProporcao(reta, 2)).toEqual(reta);
  });

  it("casos de borda: nenhum nó e um nó só", () => {
    expect(calcularPosicoes([], []).size).toBe(0);
    expect(calcularPosicoes(["a"], []).get("a")).toEqual({ x: 0, y: 0 });
  });
});

// ---------------------------------------------------------------- busca

describe("busca", () => {
  const termos = [
    termo("acao", [], { titulo: "Ação", resumo: "Pedaço de uma empresa." }),
    termo("ipca", [], { titulo: "IPCA", sinonimos: ["Inflação oficial"], resumo: "Índice." }),
    termo("inflacao", [], { titulo: "Inflação", resumo: "Alta dos preços." }),
    termo("acoes-x", [], { titulo: "Zebra", resumo: "Fala de ação no resumo." }),
  ];

  it("ignora acentos e maiúsculas", () => {
    expect(normalizar("  AÇÃO  Ética ")).toBe("acao etica");
    expect(buscarTermos(termos, "ipca").map((t) => t.slug)).toEqual(["ipca"]);
    // "Ação" é igual (nota 0); "Inflação" (título e sinônimo do IPCA) e o resumo de Zebra
    // contêm "acao" no meio (nota 2, desempate por título: Inflação, IPCA, Zebra).
    expect(buscarTermos(termos, "acao").map((t) => t.slug)).toEqual([
      "acao",
      "inflacao",
      "ipca",
      "acoes-x",
    ]);
  });

  it("ordem: nome igual, depois nome começando com o texto, depois o resto", () => {
    // "inflacao": título igual (Inflação) > sinônimo começando ("Inflação oficial", IPCA).
    expect(buscarTermos(termos, "inflacao").map((t) => t.slug)).toEqual(["inflacao", "ipca"]);
    // "preco": só aparece no meio do resumo ("preços"), nota 2.
    expect(buscarTermos(termos, "preco").map((t) => t.slug)).toEqual(["inflacao"]);
  });

  it("busca vazia devolve todos; sem resultado devolve lista vazia", () => {
    expect(buscarTermos(termos, "   ")).toHaveLength(4);
    expect(buscarTermos(termos, "bitcoin")).toEqual([]);
  });
});

// ---------------------------------------------------------------- modelo e validação

describe("modelo do verbete", () => {
  it("lista as seções ## na ordem, sem contar ###", () => {
    expect(secoesDoCorpo("## Um\ntexto\n### Sub\n## Dois  ")).toEqual(["Um", "Dois"]);
  });

  it("conta palavras sem marcação e com o texto exibido dos links", () => {
    // "Juros" "sobre" "o" "Banco" "Central" "e" "a" = 7 (marcação de título, tabela e
    // lista não conta; o link conta o texto exibido). No segundo, "10%" conta: 5 palavras.
    expect(contarPalavras("## Juros\n\n| sobre | o |\n|---|---|\n- [[bc|Banco Central]] e a")).toBe(
      7,
    );
    expect(contarPalavras("**taxa** [[selic]] de 10% - fim")).toBe(5);
  });

  it("cada categoria tem rótulo e um token de cor próprio", () => {
    expect(CATEGORIAS).toHaveLength(6);
    expect(new Set(CATEGORIAS.map((c) => tokenCategoria(c.id))).size).toBe(6);
    expect(tokenCategoria("conceitos")).toBe("var(--grafico-1)");
  });
});

describe("validação do conteúdo", () => {
  it("conteúdo correto não tem erros", () => {
    expect(
      validarConteudo([
        { slug: "a", bruto: arquivo("a", {}, corpoValido(["b"])) },
        { slug: "b", bruto: arquivo("b") },
      ]),
    ).toEqual([]);
  });

  it("aponta link quebrado, autocitação e termo isolado", () => {
    const erros = validarConteudo([
      { slug: "a", bruto: arquivo("a", {}, corpoValido(["b", "a", "fantasma"])) },
      { slug: "b", bruto: arquivo("b") },
      { slug: "c", bruto: arquivo("c") },
    ]);
    expect(erros).toEqual([
      "a.md: o termo cita a si mesmo ([[a]])",
      "a.md: link quebrado [[fantasma]] (não existe fantasma.md)",
      "c.md: termo isolado (não cita nem é citado por nenhum outro)",
    ]);
  });

  it("aponta slug repetido, título repetido, seções fora do modelo e tamanho", () => {
    const semSecao = corpoValido(["b"]).replace("## Exemplo", "## Exemplos");
    const erros = validarConteudo([
      { slug: "a", bruto: arquivo("a", { titulo: "Igual" }, semSecao) },
      { slug: "b", bruto: arquivo("b", { titulo: "igual" }, corpoValido(["a"], 400)) },
      { slug: "b", bruto: arquivo("b", {}, corpoValido(["a"], 10)) },
    ]);
    expect(erros).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/^a\.md: seções devem ser exatamente .*encontradas: .*"Exemplos"/),
        'b.md: título "igual" igual ao de a.md',
        expect.stringMatching(/^b\.md: 4\d\d palavras \(o verbete deve ter de 150 a 350\)$/),
        "b.md: slug repetido",
        expect.stringMatching(/^b\.md: \d\d palavras/),
      ]),
    );
  });

  it("erros de leitura saem com o nome do arquivo", () => {
    expect(validarConteudo([{ slug: "a", bruto: "sem cabeçalho" }])).toContain(
      "a.md: frontmatter ausente (o arquivo deve começar com ---)",
    );
  });
});
