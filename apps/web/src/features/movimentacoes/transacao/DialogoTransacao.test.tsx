import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderizar, type Chamada } from "@/test/api-falsa";
import { DialogoTransacao } from "./DialogoTransacao";

const AGORA = new Date(2026, 9, 29, 12);

const SALDO_INSUFICIENTE = {
  status: 409,
  corpo: {
    codigo: "saldo_insuficiente",
    mensagem: "Saldo insuficiente em XP (BRL) em 29/10/2026: faltam 1.234,50 BRL.",
    detalhes: [
      { campo: "instituicao_id", mensagem: "1" },
      { campo: "instituicao", mensagem: "XP" },
      { campo: "moeda", mensagem: "BRL" },
      { campo: "data", mensagem: "2026-10-29" },
      { campo: "valor_faltante", mensagem: "1234.50" },
    ],
  },
};

function transacaoGravada(corpo: Record<string, unknown>) {
  return {
    status: 201,
    corpo: {
      id: 99,
      moeda: "BRL",
      cambio: "1",
      criado_em: "2026-10-29T12:00:00Z",
      movimentos: [],
      valor_total: "0",
      valor_total_brl: "0",
      taxas_brl: "0",
      imposto_retido_brl: "0",
      resultado: null,
      resultado_brl: null,
      situacao: "aberta" as const,
      valor: null,
      subtipo_provento: null,
      imposto_retido: "0",
      observacao: null,
      ...corpo,
    },
  };
}

/** POST /api/transacoes: 409 sem `aceitar_ajuste`, grava com ele. */
function postComSaldoInsuficiente(chamada: Chamada) {
  const corpo = chamada.corpo as Record<string, unknown>;
  return corpo.aceitar_ajuste ? transacaoGravada(corpo) : SALDO_INSUFICIENTE;
}

async function preencherCompra(usuario: ReturnType<typeof renderizar>["usuario"]) {
  await screen.findByRole("option", { name: /PETR4/ });
  await usuario.selectOptions(screen.getByLabelText(/^Ativo/), "10");
  await usuario.selectOptions(screen.getByLabelText(/^Instituição/), "1");
  await usuario.type(screen.getByLabelText(/^Quantidade/), "200");
  await usuario.type(screen.getByLabelText(/^Preço unitário/), "38,12");
  await usuario.type(screen.getByLabelText(/^Taxas/), "2");
}

const posts = (chamadas: Chamada[]) =>
  chamadas.filter((c) => c.metodo === "POST" && c.caminho === "/api/transacoes");

describe("DialogoTransacao", () => {
  it("valida em pt-BR e não chama a API com campos faltando", async () => {
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />,
    );
    await usuario.click(await screen.findByRole("button", { name: "Registrar" }));
    expect(await screen.findByText("Escolha o ativo.")).toBeInTheDocument();
    expect(screen.getByText("Escolha a instituição.")).toBeInTheDocument();
    expect(screen.getAllByText("Campo obrigatório.")).toHaveLength(2);
    expect(posts(chamadas)).toHaveLength(0);
  });

  it("409 de saldo insuficiente: mostra instituição, data e valor; continuar reenvia com aceitar_ajuste", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={aoMudar} agora={AGORA} />,
      { rotas: { "POST /api/transacoes": postComSaldoInsuficiente } },
    );
    await preencherCompra(usuario);
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));

    const alerta = await screen.findByRole("alertdialog", { name: "Saldo insuficiente" });
    expect(within(alerta).getByText("XP (BRL)")).toBeInTheDocument();
    expect(within(alerta).getByText("29/10/2026")).toBeInTheDocument();
    expect(within(alerta).getByText(/R\$\s1\.234,50/)).toBeInTheDocument();
    expect(posts(chamadas)).toHaveLength(1);
    expect(posts(chamadas)[0]?.corpo).toMatchObject({
      ativo_id: 10,
      instituicao_id: 1,
      quantidade: "200",
      preco_unitario: "38.12",
      taxas: "2",
      aceitar_ajuste: false,
    });

    await usuario.click(within(alerta).getByRole("button", { name: "Continuar assim mesmo" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    expect(posts(chamadas)).toHaveLength(2);
    expect(posts(chamadas)[1]?.corpo).toMatchObject({ aceitar_ajuste: true, quantidade: "200" });
  });

  it("cancelar no aviso não grava e volta ao formulário (para registrar o depósito antes)", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao aberto aoMudar={aoMudar} agora={AGORA} />,
      { rotas: { "POST /api/transacoes": postComSaldoInsuficiente } },
    );
    await preencherCompra(usuario);
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));
    const alerta = await screen.findByRole("alertdialog");
    await usuario.click(within(alerta).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    expect(posts(chamadas)).toHaveLength(1);
    expect(aoMudar).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Registrar" })).toBeInTheDocument();
  });

  it("outros erros da API aparecem no campo certo (detalhes por campo)", async () => {
    const { usuario } = renderizar(<DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />, {
      rotas: {
        "POST /api/transacoes": {
          status: 422,
          corpo: {
            codigo: "operacao_nao_permitida",
            mensagem: "Venda maior que a posição.",
            detalhes: [{ campo: "quantidade", mensagem: "Venda maior que a posição disponível." }],
          },
        },
      },
    });
    await preencherCompra(usuario);
    await usuario.click(screen.getByRole("button", { name: "Registrar" }));
    expect(await screen.findByText("Venda maior que a posição disponível.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Quantidade/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Venda maior que a posição.")).toBeInTheDocument();
  });

  it("campos mudam com a operação e o ativo (provento, câmbio de ativo em USD)", async () => {
    const { usuario } = renderizar(<DialogoTransacao aberto aoMudar={vi.fn()} agora={AGORA} />);
    await usuario.selectOptions(await screen.findByLabelText(/^Operação/), "provento");
    expect(screen.getByLabelText(/^Valor líquido recebido/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Imposto retido/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^Quantidade/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Câmbio pago/)).not.toBeInTheDocument();

    await usuario.selectOptions(screen.getByLabelText(/^Ativo/), "11"); // AAPL (USD)
    expect(screen.getByLabelText(/^Câmbio pago \(R\$ por USD\)/)).toBeInTheDocument();
    expect(screen.getByText("Opcional. Se vazio, usa a PTAX da data.")).toBeInTheDocument();
  });

  it("edição: ativo bloqueado e PUT no mesmo id", async () => {
    const aoMudar = vi.fn();
    const { usuario, chamadas } = renderizar(
      <DialogoTransacao
        aberto
        aoMudar={aoMudar}
        agora={AGORA}
        transacao={{
          ...transacaoGravada({}).corpo,
          id: 7,
          ativo_id: 10,
          instituicao_id: 1,
          tipo: "venda",
          data: "2026-10-08",
          quantidade: "150",
          preco_unitario: "52.4",
          taxas: "3.5",
        }}
      />,
      {
        rotas: {
          "PUT /api/transacoes/{id}": (c: Chamada) =>
            transacaoGravada(c.corpo as Record<string, unknown>).corpo,
        },
      },
    );
    expect(await screen.findByLabelText(/^Ativo/)).toBeDisabled();
    expect(screen.getByLabelText(/^Preço unitário/)).toHaveValue("52,4");
    const preco = screen.getByLabelText(/^Preço unitário/);
    await usuario.clear(preco);
    await usuario.type(preco, "53");
    await usuario.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => {
      expect(aoMudar).toHaveBeenCalledWith(false);
    });
    const put = chamadas.find((c) => c.metodo === "PUT");
    expect(put?.caminho).toBe("/api/transacoes/7");
    expect(put?.corpo).toMatchObject({ tipo: "venda", preco_unitario: "53", taxas: "3.5" });
  });
});
