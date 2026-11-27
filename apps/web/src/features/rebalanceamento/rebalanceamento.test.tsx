import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NAVEGACAO } from "@/app/navegacao";
import { ROTAS } from "@/app/rotas";
import { useValoresOcultosStore } from "@/lib/valores-ocultos";
import { ativo, renderizar, ROTAS_BASE, type Chamada, type Rotas } from "@/test/api-falsa";
import { erroDoAporte, formatarPp, lerAporte, lerModo, somarPercentuais } from "./apresentacao";
import { CartaoRebalanceamento } from "./CartaoRebalanceamento";
import type { AtivoPlano, ClassePlano, Metas, Plano } from "./consultas";
import { paraCorpo } from "./formularioMetas";
import { TelaRebalanceamento } from "./TelaRebalanceamento";

const limpo = (t: string | null) => (t ?? "").replace(/\u00a0/g, " ");

function ativoPlano(
  dados: Partial<AtivoPlano> & { ativo_id: number; simbolo: string },
): AtivoPlano {
  return {
    nome: dados.simbolo,
    valor_atual: "0.00",
    peso: null,
    sugestao: null,
    acao: "manter",
    quantidade_estimada: null,
    lucro_estimado: null,
    defasado: false,
    aviso: null,
    ...dados,
  };
}

function classe(dados: Partial<ClassePlano> & { tipo_ativo: string }): ClassePlano {
  return {
    valor_atual: "0.00",
    percentual_atual: "0.00",
    meta: null,
    desvio_pp: null,
    fora_da_banda: false,
    sugestao: null,
    acao: "manter",
    usa_pesos: false,
    ativos: [],
    ...dados,
  };
}

/** Mesmo cenário do teste da API: Ações BR 8.000 (80%), FII 2.000 (20%), caixa 11.000. */
function planoAportes(): Plano {
  return {
    tem_metas: true,
    patrimonio_considerado: "10000.00",
    caixa_disponivel: "11000.00",
    aporte: "11000.00",
    modo: "aportes",
    tolerancia_pp: 5,
    desvio_total_pp: "20.00",
    classes_fora_da_banda: 2,
    avisos: [],
    classes: [
      classe({
        tipo_ativo: "acao_br",
        valor_atual: "8000.00",
        percentual_atual: "80.00",
        meta: "60.00",
        desvio_pp: "20.00",
        fora_da_banda: true,
        sugestao: "4600.00",
        acao: "aportar",
        usa_pesos: true,
        ativos: [
          ativoPlano({
            ativo_id: 10,
            simbolo: "PETR4",
            valor_atual: "5000.00",
            peso: "50.00",
            sugestao: "1300.00",
            acao: "aportar",
          }),
          ativoPlano({
            ativo_id: 13,
            simbolo: "VALE3",
            valor_atual: "3000.00",
            peso: "50.00",
            sugestao: "3300.00",
            acao: "aportar",
          }),
        ],
      }),
      classe({
        tipo_ativo: "fundo_listado",
        valor_atual: "2000.00",
        percentual_atual: "20.00",
        meta: "40.00",
        desvio_pp: "-20.00",
        fora_da_banda: true,
        sugestao: "6400.00",
        acao: "aportar",
        ativos: [
          ativoPlano({
            ativo_id: 14,
            simbolo: "HGLG11",
            valor_atual: "2000.00",
            defasado: true,
            aviso: "Cotação de 9 dias atrás.",
          }),
        ],
      }),
    ],
  };
}

function planoCompleto(): Plano {
  const base = planoAportes();
  const [acoes, fii] = base.classes as [ClassePlano, ClassePlano];
  return {
    ...base,
    modo: "completo",
    aporte: "0.00",
    classes: [
      {
        ...acoes,
        sugestao: "-2000.00",
        acao: "vender",
        ativos: [
          ativoPlano({
            ativo_id: 10,
            simbolo: "PETR4",
            valor_atual: "5000.00",
            peso: "50.00",
            sugestao: "-2000.00",
            acao: "vender",
            quantidade_estimada: "40",
            lucro_estimado: "400.00",
          }),
          ativoPlano({ ativo_id: 13, simbolo: "VALE3", peso: "50.00", sugestao: "0.00" }),
        ],
      },
      { ...fii, sugestao: "2000.00", acao: "aportar" },
    ],
  };
}

const METAS: Metas = {
  classes: [
    { tipo_ativo: "acao_br", percentual: "60.00" },
    { tipo_ativo: "fundo_listado", percentual: "40.00" },
  ],
  ativos: [
    { tipo_ativo: "acao_br", ativo_id: 10, peso: "50.00" },
    { tipo_ativo: "acao_br", ativo_id: 13, peso: "50.00" },
  ],
  tolerancia_pp: 5,
};

const SEM_METAS: Plano = {
  ...planoAportes(),
  tem_metas: false,
  desvio_total_pp: null,
  classes_fora_da_banda: 0,
  classes: planoAportes().classes.map((c) => ({
    ...c,
    meta: null,
    desvio_pp: null,
    fora_da_banda: false,
    sugestao: null,
    acao: "manter",
    usa_pesos: false,
  })),
};

function rotas(extra: Rotas = {}): Rotas {
  return {
    "GET /api/ativos": [
      ...(ROTAS_BASE["GET /api/ativos"] as unknown[]),
      ativo({ id: 13, tipo: "acao_br", simbolo: "VALE3", nome: "Vale ON" }),
      ativo({ id: 14, tipo: "fundo_listado", simbolo: "HGLG11", nome: "CSHG Log" }),
    ],
    "GET /api/rebalanceamento/plano": (c: Chamada) =>
      c.query.get("modo") === "completo" ? planoCompleto() : planoAportes(),
    "GET /api/rebalanceamento/metas": METAS,
    "PUT /api/rebalanceamento/metas": (c: Chamada) => c.corpo,
    ...extra,
  };
}

const chamadasPlano = (chamadas: Chamada[]) =>
  chamadas.filter((c) => c.caminho === "/api/rebalanceamento/plano");

async function abrirTela(extra: Rotas = {}, url = "/rebalanceamento") {
  const tela = renderizar(<TelaRebalanceamento />, { rotas: rotas(extra), url });
  await screen.findByRole("table", { name: /desvio de cada classe/i });
  return tela;
}

// ---------------------------------------------------------------- regras de apresentação

describe("apresentação do rebalanceamento", () => {
  it("lê modo e aporte da URL com padrão para valor inválido", () => {
    expect(lerModo("completo")).toBe("completo");
    expect(lerModo("tudo")).toBe("aportes");
    expect(lerModo(null)).toBe("aportes");
    expect(lerAporte("5000")).toBe("5000");
    expect(lerAporte("1.234,5")).toBe("1234.5");
    expect(lerAporte("-1")).toBeNull();
    expect(lerAporte("10.001")).toBeNull();
    expect(lerAporte("abc")).toBeNull();
    expect(erroDoAporte("10,001")).toBe("Use no máximo 2 casas decimais.");
    expect(erroDoAporte("-5")).toBe("O aporte não pode ser negativo.");
    expect(erroDoAporte("")).toBeNull();
  });

  it("formata desvio em p.p. e soma percentuais sem number", () => {
    expect(limpo(formatarPp("7.00"))).toBe("+7,00 p.p.");
    expect(limpo(formatarPp("-6.00"))).toBe("−6,00 p.p.");
    expect(limpo(formatarPp("0.00"))).toBe("0,00 p.p.");
    expect(somarPercentuais(["60", "37,5"]).texto).toBe("Soma: 97,5% (faltam 2,5%)");
    expect(somarPercentuais(["60", "40"])).toMatchObject({ completa: true, texto: "Soma: 100%" });
    expect(somarPercentuais(["60", "41", ""]).texto).toBe("Soma: 101% (passou 1%)");
    // 0,1 + 0,2 exatos (em number daria 0,30000000000000004).
    expect(somarPercentuais(["0,1", "0,2", "99,7"]).completa).toBe(true);
  });

  it("monta o corpo do PUT só com o que foi preenchido", () => {
    const corpo = paraCorpo(
      {
        classes: [
          {
            tipo: "acao_br",
            nome: "Ação (Brasil)",
            temPosicao: true,
            percentual: "60,5",
            pesos: [
              { ativo_id: 10, rotulo: "PETR4", peso: "100" },
              { ativo_id: 13, rotulo: "VALE3", peso: "" },
            ],
          },
          { tipo: "cripto", nome: "Cripto", temPosicao: false, percentual: "", pesos: [] },
          { tipo: "renda_fixa", nome: "RF", temPosicao: false, percentual: "39,5", pesos: [] },
        ],
      },
      7,
    );
    expect(corpo).toEqual({
      classes: [
        { tipo_ativo: "acao_br", percentual: "60.5" },
        { tipo_ativo: "renda_fixa", percentual: "39.5" },
      ],
      ativos: [{ tipo_ativo: "acao_br", ativo_id: 10, peso: "100" }],
      tolerancia_pp: 7,
    });
  });
});

// ---------------------------------------------------------------- tela

describe("tela Rebalanceamento", () => {
  it("mostra o carregando e depois o plano", async () => {
    renderizar(<TelaRebalanceamento />, { rotas: rotas() });
    expect(screen.getByText("Calculando o plano…")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Desvio total" })).toHaveTextContent(
      "20,00 p.p.",
    );
  });

  it("sem metas abre a tabela já em edição, sem Cancelar nem Apagar", async () => {
    renderizar(<TelaRebalanceamento />, {
      rotas: rotas({
        "GET /api/rebalanceamento/plano": SEM_METAS,
        "GET /api/rebalanceamento/metas": { classes: [], ativos: [], tolerancia_pp: 5 },
      }),
    });
    expect(await screen.findByText("Defina suas metas de alocação")).toBeInTheDocument();
    const formulario = await screen.findByRole("form", { name: "Editar metas de alocação" });
    // Todos os tipos do registry viram linhas; as classes com posição vêm primeiro.
    const campos = within(formulario).getAllByLabelText(/^Meta de /);
    expect(campos).toHaveLength(10);
    expect(campos[0]).toHaveAccessibleName("Meta de Ação (Brasil) (%)");
    expect(campos[0]).toHaveValue("");
    expect(within(formulario).getByTestId("soma-metas")).toHaveTextContent(
      "Soma: 0% (faltam 100%)",
    );
    expect(within(formulario).queryByRole("button", { name: "Cancelar" })).toBeNull();
    expect(within(formulario).queryByRole("button", { name: /apagar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Editar metas" })).toBeNull();
  });

  it("erro da API mostra a mensagem e Tentar novamente", async () => {
    let tentativas = 0;
    const { usuario } = renderizar(<TelaRebalanceamento />, {
      rotas: rotas({
        "GET /api/rebalanceamento/plano": () => {
          tentativas += 1;
          return tentativas === 1
            ? { status: 500, corpo: { codigo: "erro", mensagem: "Falha ao montar o plano." } }
            : planoAportes();
        },
      }),
    });
    expect(await screen.findByText("Falha ao montar o plano.")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(
      await screen.findByRole("table", { name: /desvio de cada classe/i }),
    ).toBeInTheDocument();
  });

  it("renderiza cartões, desvios, banda e a divisão do aporte", async () => {
    await abrirTela();
    expect(
      limpo(screen.getByRole("region", { name: "Patrimônio considerado" }).textContent),
    ).toContain("R$ 10.000,00");
    expect(screen.getByRole("region", { name: "Classes fora da banda" })).toHaveTextContent(
      "2 de 2",
    );
    expect(screen.getByRole("region", { name: "Soma das metas" })).toHaveTextContent("100%");
    const tabela = screen.getByRole("table", { name: /desvio de cada classe/i });
    expect(within(tabela).getAllByText("fora da banda")).toHaveLength(2);
    expect(within(tabela).getAllByTestId("faixa-banda")).toHaveLength(2);
    expect(limpo(tabela.textContent)).toContain("+20,00 p.p.");
    expect(limpo(tabela.textContent)).toContain("−20,00 p.p.");
    const sugestoes = screen.getByRole("list", { name: "Sugestões por classe" });
    expect(limpo(sugestoes.textContent)).toContain("Aportar em Ação (Brasil)");
    expect(limpo(sugestoes.textContent)).toContain("R$ 4.600,00");
    expect(limpo(sugestoes.textContent)).toContain("PETR4");
    expect(limpo(sugestoes.textContent)).toContain("R$ 1.300,00");
    expect(
      screen.getByText("Sugestão informativa com base nas suas metas. O app nunca executa ordens."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /alocação atual e meta por classe/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /o que é rebalanceamento/i })).toHaveAttribute(
      "href",
      "/glossario/rebalanceamento",
    );
  });

  it("pré-preenche o aporte com o caixa e manda o aporte digitado (com espera)", async () => {
    const { usuario, chamadas } = await abrirTela();
    const campo = screen.getByLabelText("Aporte (R$)");
    expect(campo).toHaveValue("11000,00");
    expect(limpo(screen.getByText(/caixa disponível/i).textContent)).toBe(
      "Caixa disponível: R$ 11.000,00",
    );
    expect(chamadasPlano(chamadas)[0]?.query.has("aporte")).toBe(false);
    await usuario.clear(campo);
    await usuario.type(campo, "5000");
    await waitFor(() => {
      expect(chamadasPlano(chamadas).at(-1)?.query.get("aporte")).toBe("5000");
    });
    expect(screen.getByTestId("url-atual")).toHaveTextContent("aporte=5000");
    // Só uma consulta nova depois de parar de digitar (não uma por tecla).
    expect(chamadasPlano(chamadas).filter((c) => c.query.has("aporte"))).toHaveLength(1);
  });

  it("aporte inválido mostra o erro e não consulta", async () => {
    const { usuario, chamadas } = await abrirTela();
    const campo = screen.getByLabelText("Aporte (R$)");
    await usuario.clear(campo);
    await usuario.type(campo, "10,001");
    expect(await screen.findByText("Use no máximo 2 casas decimais.")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 500));
    expect(chamadasPlano(chamadas).some((c) => c.query.has("aporte"))).toBe(false);
  });

  it("valor inválido na URL cai no padrão (caixa e só com aportes)", async () => {
    const { chamadas } = await abrirTela({}, "/rebalanceamento?aporte=abc&modo=tudo");
    const primeira = chamadasPlano(chamadas)[0];
    expect(primeira?.query.has("aporte")).toBe(false);
    expect(primeira?.query.get("modo")).toBe("aportes");
  });

  it("trocar o modo manda modo=completo, grava na URL e mostra vendas com lucro e aviso de IR", async () => {
    const { usuario, chamadas } = await abrirTela();
    expect(screen.queryByText(/vendas podem gerar imposto de renda/i)).not.toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Completo (com vendas)" }));
    await waitFor(() => {
      expect(chamadasPlano(chamadas).at(-1)?.query.get("modo")).toBe("completo");
    });
    expect(screen.getByTestId("url-atual")).toHaveTextContent("modo=completo");
    expect(
      await screen.findByText("Vendas podem gerar imposto de renda. O app não calcula o IR."),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rebalanceamento completo" })).toBeInTheDocument();
    const sugestoes = screen.getByRole("list", { name: "Sugestões por classe" });
    expect(limpo(sugestoes.textContent)).toContain("Reduzir Ação (Brasil)");
    expect(limpo(sugestoes.textContent)).toContain("≈ 40 unidades");
    expect(limpo(sugestoes.textContent)).toContain("lucro estimado");
    expect(limpo(sugestoes.textContent)).toContain("+R$ 400,00");
  });

  it("a classe com pesos se expande para os ativos", async () => {
    const { usuario } = await abrirTela();
    const tabela = screen.getByRole("table", { name: /desvio de cada classe/i });
    const botao = within(tabela).getByRole("button", { name: "Ação (Brasil)" });
    expect(botao).toHaveAttribute("aria-expanded", "false");
    expect(within(tabela).queryByText("VALE3")).not.toBeInTheDocument();
    await usuario.click(botao);
    expect(botao).toHaveAttribute("aria-expanded", "true");
    expect(within(tabela).getByText("VALE3")).toBeInTheDocument();
    expect(limpo(tabela.textContent)).toContain("50,00% da classe");
    // FII sem pesos não é expansível.
    expect(within(tabela).queryByRole("button", { name: /fundo listado/i })).toBeNull();
  });

  it("modo privacidade oculta valores e mantém os percentuais", async () => {
    useValoresOcultosStore.getState().definir(true);
    await abrirTela();
    const patrimonio = screen.getByRole("region", { name: "Patrimônio considerado" });
    expect(patrimonio).toHaveTextContent("•••••");
    expect(patrimonio).not.toHaveTextContent("10.000");
    const tabela = screen.getByRole("table", { name: /desvio de cada classe/i });
    expect(limpo(tabela.textContent)).toContain("80,00%");
    expect(limpo(tabela.textContent)).not.toContain("8.000,00");
    expect(limpo(screen.getByText(/caixa disponível/i).textContent)).toContain("•••••");
  });

  it("mudar a tolerância grava as metas com a nova tolerância", async () => {
    const { usuario, chamadas } = await abrirTela();
    await waitFor(() => {
      expect(screen.getByLabelText("Tolerância da banda")).toBeEnabled();
    });
    await usuario.selectOptions(screen.getByLabelText("Tolerância da banda"), "8");
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "PUT")?.corpo).toEqual({
        ...METAS,
        tolerancia_pp: 8,
      });
    });
  });
});

// ---------------------------------------------------------------- editor de metas

describe("editor de metas", () => {
  async function abrirEditor(extra: Rotas = {}) {
    const tela = await abrirTela(extra);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Editar metas" })).toBeEnabled();
    });
    await tela.usuario.click(screen.getByRole("button", { name: "Editar metas" }));
    const dialogo = await screen.findByRole("form", { name: "Editar metas de alocação" });
    return { ...tela, dialogo };
  }

  it("o lápis fica no cabeçalho da coluna Meta e Cancelar volta à tabela de desvios", async () => {
    const { usuario, dialogo } = await abrirEditor();
    expect(screen.queryByRole("table", { name: /desvio de cada classe/i })).toBeNull();
    expect(screen.getByRole("heading", { name: "Editar metas" })).toBeInTheDocument();
    expect(within(dialogo).getByLabelText("Meta de Ação (Brasil) (%)")).toHaveValue("60,00");
    await usuario.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    const tabela = await screen.findByRole("table", { name: /desvio de cada classe/i });
    const cabecalho = within(tabela).getByRole("columnheader", { name: /^Meta/ });
    expect(within(cabecalho).getByRole("button", { name: "Editar metas" })).toBeInTheDocument();
  });

  it("classes com posição vêm primeiro e a soma ≠ 100 bloqueia o salvar", async () => {
    const { usuario, dialogo } = await abrirEditor();
    const campos = within(dialogo).getAllByLabelText(/^Meta de /);
    expect(campos[0]).toHaveAccessibleName("Meta de Ação (Brasil) (%)");
    expect(within(dialogo).getByTestId("soma-metas")).toHaveTextContent("Soma: 100%");
    const fii = within(dialogo).getByLabelText(/^Meta de Fundo listado/);
    await usuario.clear(fii);
    await usuario.type(fii, "37");
    expect(within(dialogo).getByTestId("soma-metas")).toHaveTextContent("Soma: 97% (faltam 3%)");
    expect(within(dialogo).getByRole("button", { name: "Salvar metas" })).toBeDisabled();
    await usuario.type(fii, ",5");
    expect(within(dialogo).getByTestId("soma-metas")).toHaveTextContent(
      "Soma: 97,5% (faltam 2,5%)",
    );
    await usuario.clear(fii);
    await usuario.type(fii, "40");
    expect(within(dialogo).getByRole("button", { name: "Salvar metas" })).toBeEnabled();
  });

  it("pesos que não somam 100 bloqueiam o salvar", async () => {
    const { usuario, dialogo } = await abrirEditor();
    // Ações BR já tem pesos: as linhas dos ativos abrem sozinhas.
    expect(
      within(dialogo).getByRole("button", { name: "Pesos dos ativos de Ação (Brasil)" }),
    ).toHaveAttribute("aria-expanded", "true");
    const petr = within(dialogo).getByLabelText("Peso de PETR4 (% da classe)");
    await usuario.clear(petr);
    await usuario.type(petr, "30");
    expect(within(dialogo).getByText("Pesos — Soma: 80% (faltam 20%)")).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: "Salvar metas" })).toBeDisabled();
  });

  it("salva as metas (PUT) e volta à tabela de desvios", async () => {
    const { usuario, dialogo, chamadas } = await abrirEditor();
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar metas" }));
    await waitFor(() => {
      expect(screen.queryByRole("form")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("table", { name: /desvio de cada classe/i })).toBeInTheDocument();
    expect(chamadas.find((c) => c.metodo === "PUT")?.corpo).toEqual({
      classes: [
        { tipo_ativo: "acao_br", percentual: "60.00" },
        { tipo_ativo: "fundo_listado", percentual: "40.00" },
      ],
      ativos: [
        { tipo_ativo: "acao_br", ativo_id: 10, peso: "50.00" },
        { tipo_ativo: "acao_br", ativo_id: 13, peso: "50.00" },
      ],
      tolerancia_pp: 5,
    });
  });

  it("erro 422 da API vai para o campo", async () => {
    const { usuario, dialogo } = await abrirEditor({
      "PUT /api/rebalanceamento/metas": {
        status: 422,
        corpo: {
          codigo: "validacao",
          mensagem: "Metas inválidas. Confira os campos destacados.",
          detalhes: [
            { campo: "classes.acao_br", mensagem: "A meta deve estar entre 0 e 100%." },
            { campo: "ativos.13", mensagem: "Ativo não encontrado." },
          ],
        },
      },
    });
    await usuario.click(within(dialogo).getByRole("button", { name: "Salvar metas" }));
    const campo = await within(dialogo).findByLabelText("Meta de Ação (Brasil) (%)");
    await waitFor(() => {
      expect(campo).toHaveAttribute("aria-invalid", "true");
    });
    expect(within(dialogo).getByText("A meta deve estar entre 0 e 100%.")).toBeInTheDocument();
    expect(within(dialogo).getByLabelText("Peso de VALE3 (% da classe)")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByRole("form", { name: "Editar metas de alocação" })).toBeInTheDocument();
  });

  it("apagar todas as metas pede confirmação", async () => {
    const { usuario, dialogo, chamadas } = await abrirEditor();
    await usuario.click(within(dialogo).getByRole("button", { name: "Apagar todas as metas" }));
    const confirmacao = await screen.findByRole("alertdialog", { name: "Apagar todas as metas?" });
    expect(chamadas.some((c) => c.metodo === "PUT")).toBe(false);
    await usuario.click(within(confirmacao).getByRole("button", { name: "Apagar metas" }));
    await waitFor(() => {
      expect(chamadas.find((c) => c.metodo === "PUT")?.corpo).toEqual({
        classes: [],
        ativos: [],
        tolerancia_pp: 5,
      });
    });
  });
});

// ---------------------------------------------------------------- Dashboard e menu

describe("cartão do Dashboard", () => {
  it("mostra quantas classes estão fora da banda (plano com aporte 0)", async () => {
    const { chamadas } = renderizar(<CartaoRebalanceamento />, { rotas: rotas() });
    const cartao = await screen.findByRole("region", { name: "Rebalanceamento" });
    expect(cartao).toHaveTextContent("2 classes fora da banda");
    expect(within(cartao).getByRole("link", { name: "Ver Rebalanceamento" })).toHaveAttribute(
      "href",
      "/rebalanceamento",
    );
    expect(chamadasPlano(chamadas)[0]?.query.get("aporte")).toBe("0");
  });

  it("dentro das metas e oculto sem metas", async () => {
    const dentro = { ...planoAportes(), classes_fora_da_banda: 0 };
    const { unmount } = renderizar(<CartaoRebalanceamento />, {
      rotas: rotas({ "GET /api/rebalanceamento/plano": dentro }),
    });
    expect(await screen.findByText("Carteira dentro das metas")).toBeInTheDocument();
    unmount();
    const { chamadas } = renderizar(<CartaoRebalanceamento />, {
      rotas: rotas({ "GET /api/rebalanceamento/plano": SEM_METAS }),
    });
    await waitFor(() => {
      expect(chamadasPlano(chamadas)).toHaveLength(1);
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("region", { name: "Rebalanceamento" })).not.toBeInTheDocument();
  });
});

describe("menu e rota", () => {
  it("o item Rebalanceamento vem logo depois de Carteira e tem rota própria", () => {
    const rotulos = NAVEGACAO.map((i) => i.rotulo);
    expect(rotulos.indexOf("Rebalanceamento")).toBe(rotulos.indexOf("Carteira") + 1);
    expect(NAVEGACAO.find((i) => i.rotulo === "Rebalanceamento")?.para).toBe("/rebalanceamento");
    const filhos = ROTAS[0]?.children ?? [];
    expect(filhos.some((r) => r.path === "rebalanceamento")).toBe(true);
  });

  it("a rota abre a tela", async () => {
    const filho = (ROTAS[0]?.children ?? []).find((r) => r.path === "rebalanceamento");
    renderizar(<>{filho?.element}</>, { rotas: rotas(), url: "/rebalanceamento" });
    expect(await screen.findByRole("heading", { name: "Rebalanceamento" })).toBeInTheDocument();
  });
});
