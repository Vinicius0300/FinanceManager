import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Campo } from "@/components/Campo";
import { Carregando, EstadoVazio, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { DialogoSaldoInsuficiente } from "@/features/movimentacoes/transacao/DialogoSaldoInsuficiente";
import {
  lerSaldoInsuficiente,
  type SaldoInsuficiente,
} from "@/features/movimentacoes/transacao/saldo";
import { useInstituicoes } from "@/lib/consultas-comuns";
import { aplicarErrosDaApi, paraCampo } from "@/lib/formularios";
import {
  useCategorias,
  useSalvarLancamento,
  type Lancamento,
  type LancamentoEntrada,
} from "./consultas";
import { esquemaLancamento } from "./esquemas";

type Valores = z.input<typeof esquemaLancamento>;

/**
 * Cadastro e edição de um lançamento (receita ou despesa) de uma instituição, com categoria
 * do mesmo tipo. Despesa que deixaria o caixa negativo abre o aviso de saldo insuficiente
 * (409); "Continuar assim mesmo" reenvia com `aceitar_ajuste`. Recusas (422) aparecem como
 * mensagem.
 */
export function DialogoLancamento({
  lancamento,
  dataPadrao,
  instituicaoPadrao,
  aoFechar,
}: {
  lancamento?: Lancamento;
  dataPadrao: string;
  instituicaoPadrao?: number | null;
  aoFechar: () => void;
}) {
  const categorias = useCategorias();
  const instituicoes = useInstituicoes();
  const salvar = useSalvarLancamento();
  const [pendente, setPendente] = useState<{
    corpo: LancamentoEntrada;
    saldo: SaldoInsuficiente;
  } | null>(null);
  const instituicaoInicial = lancamento?.instituicao_id ?? instituicaoPadrao ?? null;
  const form = useForm<Valores, unknown, z.output<typeof esquemaLancamento>>({
    resolver: zodResolver(esquemaLancamento),
    defaultValues: {
      tipo: lancamento?.tipo ?? "despesa",
      data: lancamento?.data ?? dataPadrao,
      valor: paraCampo(lancamento?.valor),
      instituicao_id: instituicaoInicial === null ? "" : String(instituicaoInicial),
      categoria_id: lancamento?.categoria_id ? String(lancamento.categoria_id) : "",
      descricao: lancamento?.descricao ?? "",
      observacao: lancamento?.observacao ?? "",
    },
  });
  const erros = form.formState.errors;
  const tipo = useWatch({ control: form.control, name: "tipo" });
  const doTipo = (categorias.data ?? []).filter((c) => c.tipo === tipo);
  const id = lancamento?.lancamento_id ?? undefined;

  const gravar = async (corpo: LancamentoEntrada) => {
    try {
      await salvar.mutateAsync({ id, corpo });
      setPendente(null);
      aoFechar();
    } catch (falha) {
      const saldo = lerSaldoInsuficiente(falha);
      if (saldo && !corpo.aceitar_ajuste) {
        salvar.reset();
        setPendente({ corpo, saldo });
        return;
      }
      if (!corpo.aceitar_ajuste) {
        aplicarErrosDaApi(falha, form.setError, [
          "tipo",
          "data",
          "valor",
          "instituicao_id",
          "categoria_id",
          "descricao",
          "observacao",
        ]);
      }
    }
  };

  const enviar = form.handleSubmit((dados) => gravar({ ...dados, aceitar_ajuste: false }));
  const carregando = categorias.isPending || instituicoes.isPending;
  const semInstituicao = instituicoes.isSuccess && instituicoes.data.length === 0;

  return (
    <Dialog
      open
      onOpenChange={(aberto) => {
        if (!aberto) aoFechar();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{lancamento ? "Editar lançamento" : "Novo lançamento"}</DialogTitle>
          <DialogDescription>
            Receitas e despesas do mês (sempre em reais), no caixa da instituição. Salário é
            receita; dinheiro passado entre bancos é transferência (Movimentações → Caixa).
          </DialogDescription>
        </DialogHeader>
        {carregando ? (
          <Carregando />
        ) : instituicoes.isError ? (
          <MensagemErro erro={instituicoes.error} />
        ) : semInstituicao ? (
          <EstadoVazio
            titulo="Nenhuma instituição cadastrada"
            descricao="Todo lançamento pertence a uma instituição. Cadastre o banco em Movimentações › Caixa (Nova instituição)."
          />
        ) : (
          <form
            noValidate
            className="grid gap-4"
            onSubmit={(e) => {
              void enviar(e);
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo rotulo="Tipo" erro={erros.tipo?.message}>
                <Select
                  {...form.register("tipo", {
                    onChange: () => {
                      form.setValue("categoria_id", "");
                    },
                  })}
                >
                  <option value="despesa">Despesa</option>
                  <option value="receita">Receita</option>
                </Select>
              </Campo>
              <Campo rotulo="Data" obrigatorio erro={erros.data?.message}>
                <Input type="date" {...form.register("data")} />
              </Campo>
              <Campo rotulo="Valor (R$)" obrigatorio erro={erros.valor?.message}>
                <Input inputMode="decimal" placeholder="0,00" {...form.register("valor")} />
              </Campo>
              <Campo rotulo="Instituição" obrigatorio erro={erros.instituicao_id?.message}>
                <Select {...form.register("instituicao_id")}>
                  <option value="">Escolha…</option>
                  {instituicoes.data.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.nome}
                    </option>
                  ))}
                </Select>
              </Campo>
              <Campo rotulo="Categoria" erro={erros.categoria_id?.message}>
                <Select {...form.register("categoria_id")}>
                  <option value="">Sem categoria</option>
                  {doTipo.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nome}
                    </option>
                  ))}
                </Select>
              </Campo>
              <Campo rotulo="Descrição" obrigatorio erro={erros.descricao?.message}>
                <Input maxLength={200} {...form.register("descricao")} />
              </Campo>
              <Campo rotulo="Observação" erro={erros.observacao?.message} className="sm:col-span-2">
                <Textarea rows={2} maxLength={500} {...form.register("observacao")} />
              </Campo>
            </div>
            {!pendente && <MensagemErro erro={salvar.error} />}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={aoFechar}
                disabled={salvar.isPending}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={salvar.isPending}>
                {salvar.isPending && <Loader2 aria-hidden className="animate-spin" />}
                Salvar
              </Button>
            </div>
          </form>
        )}
        <DialogoSaldoInsuficiente
          saldo={pendente?.saldo ?? null}
          ocupado={salvar.isPending}
          erro={salvar.error}
          aoCancelar={() => {
            setPendente(null);
            salvar.reset();
          }}
          aoContinuar={() => {
            if (!pendente) return;
            void gravar({ ...pendente.corpo, aceitar_ajuste: true });
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
