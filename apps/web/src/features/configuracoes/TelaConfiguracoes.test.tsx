import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { escolherArquivo } from "@/lib/dialogos-nativos";
import { useTemaStore } from "@/theme/tema";
import { renderizar, type Chamada } from "@/test/api-falsa";
import { esquemaIntervalo } from "./definicoes";
import { TelaConfiguracoes } from "./TelaConfiguracoes";

vi.mock("@/lib/dialogos-nativos", () => ({
  escolherOndeSalvar: vi.fn(),
  escolherArquivo: vi.fn(),
}));

const AGORA = new Date(2026, 9, 29, 12);

const INDICADORES: Record<string, object[]> = {
  selic: [
    { id: 1, tipo: "selic", moeda: "BRL", data: "2026-10-27", valor: "15", fonte: "bcb_sgs" },
    { id: 2, tipo: "selic", moeda: "BRL", data: "2026-10-28", valor: "14.75", fonte: "bcb_sgs" },
  ],
  cdi: [{ id: 3, tipo: "cdi", moeda: "BRL", data: "2026-10-28", valor: "14.65", fonte: "manual" }],
  ipca: [],
  cambio: [
    { id: 5, tipo: "cambio", moeda: "USD", data: "2026-10-29", valor: "5.4321", fonte: "yfinance" },
  ],
};

const ROTAS = {
  "GET /api/configuracoes": { intervalo_atualizacao_min: 5 },
  "PUT /api/configuracoes": (c: Chamada) => c.corpo,
  "GET /api/indicadores": (c: Chamada) => INDICADORES[c.query.get("tipo") ?? ""] ?? [],
  "GET /api/backups": [
    {
      nome: "financas-20261029-120000-manual.db",
      tamanho_bytes: 2_500_000,
      criado_em: "2026-10-29T15:00:00Z",
    },
  ],
  "POST /api/backups/restaurar": (c: Chamada) => ({
    restaurado: (c.corpo as { nome?: string; caminho?: string }).nome ?? "arquivo",
    backup_seguranca: {
      nome: "financas-20261029-130000-pre-restauracao.db",
      tamanho_bytes: 1,
      criado_em: "",
    },
  }),
  "GET /health": { status: "ok", versao: "0.1.0" },
  "GET /api/ping": { mensagem: "pong", horario: "2026-10-29T15:00:00Z", versao: "0.1.0" },
};

describe("esquema do intervalo", () => {
  it.each([
    ["5", true],
    ["1", true],
    ["15", true],
    ["0", false],
    ["16", false],
    ["2,5", false],
  ])("%s → %s", (valor, valido) => {
    expect(esquemaIntervalo.safeParse({ intervalo_atualizacao_min: valor }).success).toBe(valido);
  });
});

describe("Configurações", () => {
  beforeEach(() => {
    vi.mocked(escolherArquivo).mockReset();
  });

  it("intervalo: carrega, valida (1 a 15) e salva", async () => {
    const { usuario, chamadas } = renderizar(<TelaConfiguracoes agora={AGORA} />, { rotas: ROTAS });
    const campo = await screen.findByLabelText(/^Intervalo de ações e cripto/);
    await waitFor(() => {
      expect(campo).toHaveValue(5);
    });
    await usuario.clear(campo);
    await usuario.type(campo, "20");
    await usuario.click(screen.getAllByRole("button", { name: "Salvar" })[0] as HTMLElement);
    expect(await screen.findByText("Escolha entre 1 e 15 minutos.")).toBeInTheDocument();
    await usuario.clear(campo);
    await usuario.type(campo, "10");
    await usuario.click(screen.getAllByRole("button", { name: "Salvar" })[0] as HTMLElement);
    expect(await screen.findByText("Intervalo salvo.")).toBeInTheDocument();
    expect(chamadas.find((c) => c.metodo === "PUT")?.corpo).toEqual({
      intervalo_atualizacao_min: 10,
    });
  });

  it("tema claro/escuro pelo switch", async () => {
    useTemaStore.setState({ tema: "escuro" });
    const { usuario } = renderizar(<TelaConfiguracoes agora={AGORA} />, { rotas: ROTAS });
    await usuario.click(screen.getByRole("switch", { name: "Modo escuro" }));
    expect(useTemaStore.getState().tema).toBe("claro");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    useTemaStore.setState({ tema: "escuro" });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("indicadores: último valor com data e fonte; aviso quando não há valor", async () => {
    renderizar(<TelaConfiguracoes agora={AGORA} />, { rotas: ROTAS });
    const selic = await screen.findByRole("region", { name: "Selic" });
    await waitFor(() => {
      expect(selic).toHaveTextContent("14,75% a.a.");
    });
    expect(selic).toHaveTextContent("28/10/2026 · Banco Central (SGS)");
    const cdi = screen.getByRole("region", { name: "CDI" });
    await waitFor(() => {
      expect(cdi).toHaveTextContent("Manual");
    });
    const cambio = screen.getByRole("region", { name: "Dólar (PTAX)" });
    await waitFor(() => {
      expect(cambio.textContent.replace(/\u00a0/g, " ")).toContain("R$ 5,4321");
    });
    expect(
      await within(screen.getByRole("region", { name: "IPCA" })).findByText(/Sem valor/),
    ).toBeInTheDocument();
  });

  it("lançamento manual de indicador (IPCA no dia 1º) e edição do último valor", async () => {
    const { usuario, chamadas } = renderizar(<TelaConfiguracoes agora={AGORA} />, {
      rotas: {
        ...ROTAS,
        "POST /api/indicadores": (c: Chamada) => ({
          id: 9,
          fonte: "manual",
          ...(c.corpo as object),
        }),
        "PUT /api/indicadores/{id}": (c: Chamada) => ({ id: 2, ...(c.corpo as object) }),
      },
    });
    const ipca = await screen.findByRole("region", { name: "IPCA" });
    await usuario.click(within(ipca).getByRole("button", { name: "Lançar" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByLabelText(/^Data/)).toHaveValue("2026-10-01");
    await usuario.type(within(dialogo).getByLabelText(/^Valor/), "0,56");
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "POST")?.corpo).toEqual({
        tipo: "ipca",
        moeda: "BRL",
        data: "2026-10-01",
        valor: "0.56",
      });
    });

    const selic = screen.getByRole("region", { name: "Selic" });
    await usuario.click(await within(selic).findByRole("button", { name: "Editar" }));
    const edicao = await screen.findByRole("dialog");
    expect(within(edicao).getByLabelText(/^Valor/)).toHaveValue("14,75");
    await usuario.clear(within(edicao).getByLabelText(/^Valor/));
    await usuario.type(within(edicao).getByLabelText(/^Valor/), "15");
    await usuario.click(within(edicao).getByRole("button", { name: "Salvar" }));
    await waitFor(() => {
      expect(
        chamadas.find((c) => c.metodo === "PUT" && c.caminho === "/api/indicadores/2")?.corpo,
      ).toEqual({
        valor: "15",
      });
    });
  });

  it("restauração pede confirmação (da lista e de arquivo escolhido no diálogo nativo)", async () => {
    vi.mocked(escolherArquivo).mockResolvedValue("D:\\backup\\financas.db");
    const { usuario, chamadas } = renderizar(<TelaConfiguracoes agora={AGORA} />, { rotas: ROTAS });
    const tabela = await screen.findByRole("table", { name: "Backups" });
    await usuario.click(within(tabela).getByRole("button", { name: "Restaurar" }));
    let confirmacao = await screen.findByRole("alertdialog", { name: "Restaurar este backup?" });
    expect(confirmacao).toHaveTextContent("backup de segurança");
    expect(chamadas.filter((c) => c.caminho === "/api/backups/restaurar")).toHaveLength(0);
    await usuario.click(within(confirmacao).getByRole("button", { name: "Restaurar" }));
    expect(
      await screen.findByText(/Dados restaurados de financas-20261029-120000-manual\.db/),
    ).toBeInTheDocument();
    expect(chamadas.find((c) => c.caminho === "/api/backups/restaurar")?.corpo).toEqual({
      nome: "financas-20261029-120000-manual.db",
    });

    await usuario.click(screen.getByRole("button", { name: "Restaurar de um arquivo…" }));
    confirmacao = await screen.findByRole("alertdialog");
    expect(confirmacao).toHaveTextContent("D:\\backup\\financas.db");
    await usuario.click(within(confirmacao).getByRole("button", { name: "Cancelar" }));
    expect(chamadas.filter((c) => c.caminho === "/api/backups/restaurar")).toHaveLength(1);
    expect(escolherArquivo).toHaveBeenCalledWith({ nome: "Banco do Finanças", extensoes: ["db"] });
  });
});
