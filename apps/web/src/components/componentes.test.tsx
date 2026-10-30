import { QueryClient } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LayoutApp } from "@/app/LayoutApp";
import {
  invalidarCotacoes,
  JANELA_INVALIDACAO_MS,
  useEstadoAtualizacao,
} from "@/features/tempo-real/atualizacao";
import { FalhaApi } from "@/lib/backend";
import { CONEXAO, renderizar } from "@/test/api-falsa";
import { CartaoMetrica } from "./CartaoMetrica";
import { DialogoConfirmacao } from "./DialogoConfirmacao";
import { EstadoErro, EstadoVazio } from "./Estados";
import { IndicadorDefasado } from "./IndicadorDefasado";
import { ValorFinanceiro } from "./ValorFinanceiro";

const limpo = (t: string | null) => (t ?? "").replace(/\u00a0/g, " ");

describe("ValorFinanceiro: ganho/perda nunca só pela cor", () => {
  it("ganho com +, seta e token positivo", () => {
    const { container } = render(<ValorFinanceiro valor="195" />);
    const span = container.firstElementChild;
    expect(span).toHaveClass("text-positivo");
    expect(limpo(span?.textContent ?? "")).toBe("ganho: +R$ 195,00");
    expect(span?.querySelector("svg")).not.toBeNull();
  });

  it("perda com −, seta e token negativo", () => {
    const { container } = render(<ValorFinanceiro valor="-40.5" />);
    expect(container.firstElementChild).toHaveClass("text-negativo");
    expect(limpo(container.textContent)).toBe("perda: −R$ 40,50");
  });

  it("zero usa a cor neutra e sem seta", () => {
    const { container } = render(<ValorFinanceiro valor="0.00" />);
    expect(container.firstElementChild).toHaveClass("text-muted-foreground");
    expect(container.querySelector("svg")).toBeNull();
  });

  it("razão como percentual e moeda estrangeira", () => {
    expect(
      limpo(render(<ValorFinanceiro valor="0.0734" percentual />).container.textContent),
    ).toContain("+7,34%");
    expect(
      limpo(render(<ValorFinanceiro valor="98" moeda="USD" />).container.textContent),
    ).toContain("+US$ 98,00");
  });
});

describe("componentes compartilhados", () => {
  it("cartão de métrica com carregando acessível", () => {
    render(<CartaoMetrica titulo="Total" valor="R$ 1,00" apoio="apoio" carregando />);
    expect(screen.getByRole("region", { name: "Total" })).toHaveTextContent("…");
  });

  it("indicador de defasado e de erro com o motivo", () => {
    render(<IndicadorDefasado defasado aviso="Cotação de 5 dias." erro="HTTP 503" />);
    expect(screen.getByText("Defasado").closest("[title]")).toHaveAttribute(
      "title",
      "Cotação de 5 dias.",
    );
    expect(screen.getByText("Erro").closest("[title]")).toHaveAttribute("title", "HTTP 503");
    const { container } = render(<IndicadorDefasado defasado={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("estado vazio e estado de erro com nova tentativa", async () => {
    const tentar = vi.fn();
    render(
      <>
        <EstadoVazio titulo="Nada aqui" descricao="Cadastre algo." />
        <EstadoErro erro={new TypeError("Failed to fetch")} aoTentarNovamente={tentar} />
      </>,
    );
    expect(screen.getByText("Nada aqui")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Não foi possível conectar ao serviço interno",
    );
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(tentar).toHaveBeenCalled();
  });

  it("diálogo de confirmação mostra a recusa da API e bloqueia durante a operação", async () => {
    const confirmar = vi.fn();
    const { rerender } = render(
      <DialogoConfirmacao
        aberto
        aoMudar={vi.fn()}
        titulo="Excluir?"
        descricao="Tem certeza?"
        aoConfirmar={confirmar}
        erro={new FalhaApi({ codigo: "conflito", mensagem: "Há transações." }, 409)}
      />,
    );
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Há transações.");
    await userEvent.click(screen.getByRole("button", { name: "Excluir" }));
    expect(confirmar).toHaveBeenCalledTimes(1);
    rerender(
      <DialogoConfirmacao
        aberto
        aoMudar={vi.fn()}
        titulo="Excluir?"
        descricao="x"
        aoConfirmar={confirmar}
        ocupado
      />,
    );
    expect(screen.getByRole("button", { name: "Excluir" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
  });
});

describe("tempo real (SSE)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("invalida só as consultas que dependem de cotação", async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["portfolio", "resumo", null], 1);
    queryClient.setQueryData(["status-cotacoes"], 1);
    queryClient.setQueryData(["categorias"], 1);
    await invalidarCotacoes(queryClient);
    expect(queryClient.getQueryState(["portfolio", "resumo", null])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["status-cotacoes"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["categorias"])?.isInvalidated).toBe(false);
  });

  it("guarda o fim do ciclo e o último erro de provider", () => {
    const { registrarEvento } = useEstadoAtualizacao.getState();
    registrarEvento({ tipo: "erro_provider", dados: { mensagem: "CoinGecko fora do ar." } });
    registrarEvento({ tipo: "fim_ciclo", dados: { fim: "2026-10-29T17:00:00Z", erros: 1 } });
    expect(useEstadoAtualizacao.getState()).toMatchObject({
      ultimoFim: "2026-10-29T17:00:00Z",
      ultimosErros: 1,
      ultimaMensagemErro: "CoinGecko fora do ar.",
    });
  });

  it("layout consome o stream: eventos em sequência viram uma só invalidação; topo mostra o ciclo", async () => {
    useEstadoAtualizacao.setState({ ultimoFim: null, ultimosErros: 0, ultimaMensagemErro: null });
    const codificador = new TextEncoder();
    let controle: ReadableStreamDefaultController<Uint8Array> | undefined;
    const corpo = new ReadableStream<Uint8Array>({
      start(c) {
        controle = c;
      },
    });
    // O stream usa o fetch global (com o token no cabeçalho), não o cliente gerado.
    const fetchStream = vi.fn((recurso: RequestInfo | URL, init?: RequestInit) => {
      const cabecalhos = new Headers(init?.headers);
      expect(recurso instanceof Request ? recurso.url : recurso.toString()).toBe(
        `${CONEXAO.urlBase}/api/eventos`,
      );
      expect(cabecalhos.get("Authorization")).toBe(`Bearer ${CONEXAO.token}`);
      return Promise.resolve(
        new Response(corpo, { headers: { "Content-Type": "text/event-stream" } }),
      );
    });
    vi.stubGlobal("fetch", fetchStream);
    const { queryClient } = renderizar(<LayoutApp />);
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
    for (const rotulo of [
      "Dashboard",
      "Carteira",
      "Movimentações",
      "Receitas e Despesas",
      "Configurações",
    ]) {
      expect(screen.getByRole("link", { name: rotulo })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveClass("bg-lateral-ativo");

    const invalidar = vi.spyOn(queryClient, "invalidateQueries");
    await waitFor(() => {
      expect(controle).toBeDefined();
    });
    act(() => {
      for (const id of [1, 2, 3]) {
        controle?.enqueue(
          codificador.encode(`event: preco_atualizado\ndata: {"ativo_id":${id},"valor":"10"}\n\n`),
        );
      }
      controle?.enqueue(
        codificador.encode('event: fim_ciclo\ndata: {"fim":"2026-10-29T17:00:00Z","erros":2}\n\n'),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/Cotações atualizadas em/)).toHaveTextContent("· 2 falhas");
    });
    await waitFor(
      () => {
        expect(invalidar).toHaveBeenCalledTimes(1);
      },
      { timeout: JANELA_INVALIDACAO_MS * 4 },
    );
  });
});
