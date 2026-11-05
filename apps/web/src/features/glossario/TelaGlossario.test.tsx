import { act, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GlossarioSobDemanda } from "@/app/GlossarioSobDemanda";
import { NAVEGACAO } from "@/app/navegacao";
import { renderizar } from "@/test/api-falsa";
import { GLOSSARIO } from "./conteudo/glossario";
import { montarIndice } from "./dominio/indice";
import { TelaGlossario } from "./TelaGlossario";

/*
 * O setup troca o GraficoECharts por um marcador. Aqui o marcador também desenha um botão
 * por nó do grafo (para simular o clique numa bolinha) e pode simular a falha do ECharts.
 */
const grafico = vi.hoisted(() => ({ falhar: false }));
vi.mock("@/components/graficos/GraficoECharts", () => ({
  GraficoECharts: ({
    rotulo,
    opcoes,
    aoClicar,
  }: {
    rotulo: string;
    opcoes: { series: { data: { id: string }[] }[] };
    aoClicar?: (e: unknown) => void;
  }) =>
    grafico.falhar ? (
      <p role="alert">Não foi possível desenhar o gráfico.</p>
    ) : (
      <div role="img" aria-label={rotulo} data-opcoes={JSON.stringify(opcoes)}>
        {opcoes.series[0]?.data.map((no) => (
          <button
            key={no.id}
            type="button"
            data-testid={`no-${no.id}`}
            onClick={() => aoClicar?.({ dataType: "node", data: { id: no.id } })}
          />
        ))}
      </div>
    ),
}));

beforeEach(() => {
  grafico.falhar = false;
});

const CAMINHO = "/glossario/:termo?";
const abrir = (url: string) => renderizar(<TelaGlossario />, { url, caminho: CAMINHO });
const url = () => screen.getByTestId("url-atual").textContent;
const listaTermos = () => screen.getByRole("navigation", { name: "Termos do glossário" });
const nosDoGrafo = () => {
  const opcoes = JSON.parse(screen.getByRole("img").getAttribute("data-opcoes") ?? "{}") as {
    series: { data: { id: string }[] }[];
  };
  return opcoes.series[0]?.data.map((n) => n.id) ?? [];
};

describe("menu e rota", () => {
  it("o item Glossário fica no menu antes de Configurações", () => {
    const rotulos = NAVEGACAO.map((i) => i.rotulo);
    expect(rotulos.indexOf("Glossário")).toBe(rotulos.indexOf("Configurações") - 1);
    expect(NAVEGACAO.find((i) => i.rotulo === "Glossário")?.para).toBe("/glossario");
  });

  it("a rota carrega a tela sob demanda e abre o termo da URL", async () => {
    renderizar(<GlossarioSobDemanda />, { url: "/glossario/cdi", caminho: CAMINHO });
    expect(await screen.findByRole("heading", { level: 2, name: "CDI" })).toBeInTheDocument();
  });
});

describe("tela do glossário", () => {
  it("sem termo aberto mostra como usar, as sugestões e o aviso educativo", () => {
    abrir("/glossario");
    expect(screen.getByRole("heading", { name: "Como usar o glossário" })).toBeInTheDocument();
    expect(screen.getByText(/Não é recomendação de investimento/)).toBeInTheDocument();
    const sugestoes = screen.getByText("Por onde começar").parentElement as HTMLElement;
    expect(
      within(sugestoes)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Inflação", "Selic", "CDI", "Juros simples e compostos", "Diversificação"]);
    // A tela abre no grafo, com todos os termos.
    expect(screen.getByRole("group", { name: "Visualização" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Grafo" })).toHaveAttribute("aria-pressed", "true");
    expect(nosDoGrafo()).toHaveLength(GLOSSARIO.termos.length);
  });

  it("sugestões que não existem no conteúdo são ignoradas", () => {
    // Índice só com Selic e CDI: as outras três sugestões somem sem quebrar a tela.
    const reduzido = montarIndice(
      GLOSSARIO.termos.filter((t) => t.slug === "selic" || t.slug === "cdi"),
    );
    renderizar(<TelaGlossario indice={reduzido} />, { url: "/glossario", caminho: CAMINHO });
    const sugestoes = screen.getByText("Por onde começar").parentElement as HTMLElement;
    expect(
      within(sugestoes)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Selic", "CDI"]);
  });

  it("abre o verbete: título, categoria, sinônimos, corpo, relacionados e revisão", () => {
    abrir("/glossario/cdi");
    const verbete = screen.getByRole("article");
    expect(within(verbete).getByRole("heading", { level: 2, name: "CDI" })).toHaveFocus();
    expect(within(verbete).getByText("Indicadores")).toBeInTheDocument();
    expect(within(verbete).getByText(/Também chamado de: DI, Taxa DI/)).toBeInTheDocument();
    expect(within(verbete).getByRole("heading", { name: "Exemplo" })).toBeInTheDocument();
    // Link do corpo ([[selic]]) vira link interno com o título do termo.
    expect(within(verbete).getAllByRole("link", { name: "Selic" })[0]).toHaveAttribute(
      "href",
      "/glossario/selic",
    );
    const relacionados = within(verbete).getByText("Relacionados").parentElement as HTMLElement;
    expect(
      within(relacionados)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(expect.arrayContaining(["CDB", "Selic", "Tabela regressiva de IR"]));
    expect(within(verbete).getByText("Revisado em novembro de 2026.")).toBeInTheDocument();
  });

  it("clicar num link do texto abre o outro verbete", async () => {
    const { usuario } = abrir("/glossario/cdi");
    const verbete = screen.getByRole("article");
    await usuario.click(within(verbete).getAllByRole("link", { name: "Selic" })[0] as HTMLElement);
    expect(url()).toBe("/glossario/selic");
    expect(screen.getByRole("heading", { level: 2, name: "Selic" })).toBeInTheDocument();
  });

  it("clicar numa bolinha do grafo abre o verbete", async () => {
    const { usuario } = abrir("/glossario");
    await usuario.click(screen.getByTestId("no-fgc"));
    expect(url()).toBe("/glossario/fgc");
    expect(screen.getByRole("heading", { level: 2, name: "FGC" })).toBeInTheDocument();
  });

  it("termo aberto: só ele fica destacado no grafo; não há opção de vizinhança", () => {
    abrir("/glossario/fgc");
    expect(screen.queryByRole("button", { name: "Só a vizinhança" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Todos os termos" })).not.toBeInTheDocument();
    // O grafo continua com todos os termos (o destaque do aberto é testado em grafo.test.ts).
    expect(nosDoGrafo().length).toBeGreaterThanOrEqual(8);
  });

  it("alterna entre Grafo e Lista de termos, mantendo o termo aberto", async () => {
    const { usuario } = abrir("/glossario/cdi");
    const grafo = screen.getByRole("button", { name: "Grafo" });
    const lista = screen.getByRole("button", { name: "Lista de termos" });
    expect(grafo).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("navigation", { name: "Termos do glossário" })).toBeNull();
    await usuario.click(lista);
    expect(lista).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(within(listaTermos()).getByRole("link", { name: "CDI" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // Abrir outro termo pela lista mantém a lista na tela.
    await usuario.click(within(listaTermos()).getByRole("link", { name: "Selic" }));
    expect(url()).toBe("/glossario/selic");
    expect(listaTermos()).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Grafo" }));
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("busca sem acento filtra a lista; Enter abre o primeiro resultado", async () => {
    const { usuario } = abrir("/glossario");
    await usuario.click(screen.getByRole("button", { name: "Lista de termos" }));
    await usuario.type(screen.getByRole("searchbox", { name: "Buscar termo" }), "inflacao");
    expect(screen.getByRole("status")).toHaveTextContent(/^Resultado da busca: \d+ termos?\.$/);
    // "Inflação" (título igual) vem antes do IPCA (sinônimo "Inflação oficial").
    expect(
      within(listaTermos())
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(expect.arrayContaining(["Inflação", "IPCA"]));
    expect(within(listaTermos()).queryByRole("link", { name: "CDB" })).not.toBeInTheDocument();
    await usuario.keyboard("{Enter}");
    expect(url()).toBe("/glossario/inflacao");
  });

  it("no grafo, a busca diz quantos achou e Enter abre o primeiro", async () => {
    const { usuario } = abrir("/glossario");
    await usuario.type(screen.getByRole("searchbox", { name: "Buscar termo" }), "selic");
    expect(screen.getByRole("status")).toHaveTextContent(
      /termos? encontrados?\. Aperte Enter para abrir “Selic” ou veja todos em Lista de termos\./,
    );
    await usuario.keyboard("{Enter}");
    expect(url()).toBe("/glossario/selic");
  });

  it("busca sem resultado: aviso no grafo e estado vazio na lista", async () => {
    const { usuario } = abrir("/glossario");
    await usuario.type(screen.getByRole("searchbox", { name: "Buscar termo" }), "bitcoin");
    expect(screen.getByRole("status")).toHaveTextContent("Nenhum termo encontrado para “bitcoin”.");
    await usuario.click(screen.getByRole("button", { name: "Lista de termos" }));
    expect(screen.getByText("Nenhum termo encontrado para “bitcoin”.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Termos do glossário" })).toBeNull();
  });

  it("filtro de categoria esconde os termos do grafo e da lista", async () => {
    const { usuario } = abrir("/glossario");
    const chip = screen.getByRole("button", { name: "Indicadores" });
    expect(chip).toHaveAttribute("aria-pressed", "true");
    await usuario.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "false");
    expect(nosDoGrafo()).not.toContain("cdi");
    expect(nosDoGrafo()).toContain("cdb");
    await usuario.click(screen.getByRole("button", { name: "Lista de termos" }));
    expect(within(listaTermos()).queryByRole("link", { name: "CDI" })).not.toBeInTheDocument();
    await usuario.click(chip);
    expect(within(listaTermos()).getByRole("link", { name: "CDI" })).toBeInTheDocument();
  });

  it("desligar todas as categorias mostra os estados vazios", async () => {
    const { usuario } = abrir("/glossario");
    const chips = within(screen.getByRole("group", { name: "Categorias" })).getAllByRole("button");
    for (const chip of chips) await usuario.click(chip);
    expect(screen.getByText("Nenhuma categoria selecionada")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Lista de termos" }));
    expect(screen.getByText("Nenhum termo nas categorias selecionadas.")).toBeInTheDocument();
  });

  it("termo inexistente mostra aviso com link para o início", async () => {
    const { usuario } = abrir("/glossario/bitcoin");
    expect(screen.getByText("Termo não encontrado")).toBeInTheDocument();
    await usuario.click(screen.getByRole("link", { name: "Voltar ao início do glossário" }));
    expect(url()).toBe("/glossario");
  });

  it("a lista de termos funciona pelo teclado", async () => {
    const { usuario } = abrir("/glossario");
    await usuario.click(screen.getByRole("button", { name: "Lista de termos" }));
    const link = within(listaTermos()).getByRole("link", { name: "IPCA" });
    act(() => {
      link.focus();
    });
    await usuario.keyboard("{Enter}");
    expect(url()).toBe("/glossario/ipca");
    await waitFor(() => {
      expect(within(listaTermos()).getByRole("link", { name: "IPCA" })).toHaveAttribute(
        "aria-current",
        "page",
      );
    });
    // Tab sai do link atual para o próximo da lista.
    act(() => {
      within(listaTermos()).getByRole("link", { name: "IPCA" }).focus();
    });
    await usuario.tab();
    expect(document.activeElement?.tagName).toBe("A");
  });

  it("falha ao desenhar o grafo não impede a busca nem a lista", async () => {
    grafico.falhar = true;
    const { usuario } = abrir("/glossario");
    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível desenhar o gráfico.");
    await usuario.click(screen.getByRole("button", { name: "Lista de termos" }));
    await usuario.click(within(listaTermos()).getByRole("link", { name: "CDB" }));
    expect(screen.getByRole("heading", { level: 2, name: "CDB" })).toBeInTheDocument();
  });
});
