import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Campo } from "@/components/Campo";
import { Carregando, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { aplicarErrosDaApi, paraCampo } from "@/lib/formularios";
import {
  useCategorias,
  useSalvarLancamento,
  type Lancamento,
  type LancamentoEntrada,
} from "./consultas";
import { esquemaLancamento } from "./esquemas";

type Valores = z.input<typeof esquemaLancamento>;

/** Cadastro e edição de um lançamento (receita ou despesa) com categoria do mesmo tipo. */
export function DialogoLancamento({
  lancamento,
  dataPadrao,
  aoFechar,
}: {
  lancamento?: Lancamento;
  dataPadrao: string;
  aoFechar: () => void;
}) {
  const categorias = useCategorias();
  const salvar = useSalvarLancamento();
  const form = useForm<Valores, unknown, z.output<typeof esquemaLancamento>>({
    resolver: zodResolver(esquemaLancamento),
    defaultValues: {
      tipo: lancamento?.tipo ?? "despesa",
      data: lancamento?.data ?? dataPadrao,
      valor: paraCampo(lancamento?.valor),
      categoria_id: lancamento?.categoria_id ? String(lancamento.categoria_id) : "",
      descricao: lancamento?.descricao ?? "",
      observacao: lancamento?.observacao ?? "",
    },
  });
  const erros = form.formState.errors;
  const tipo = useWatch({ control: form.control, name: "tipo" });
  const doTipo = (categorias.data ?? []).filter((c) => c.tipo === tipo);

  const enviar = form.handleSubmit(async (dados) => {
    const corpo: LancamentoEntrada = { ...dados };
    try {
      await salvar.mutateAsync({ id: lancamento?.id, corpo });
      aoFechar();
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, [
        "tipo",
        "data",
        "valor",
        "categoria_id",
        "descricao",
        "observacao",
      ]);
    }
  });

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
          <DialogDescription>Receitas e despesas do mês (sempre em reais).</DialogDescription>
        </DialogHeader>
        {categorias.isPending ? (
          <Carregando />
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
              <Campo
                rotulo="Descrição"
                obrigatorio
                erro={erros.descricao?.message}
                className="sm:col-span-2"
              >
                <Input maxLength={200} {...form.register("descricao")} />
              </Campo>
              <Campo rotulo="Observação" erro={erros.observacao?.message} className="sm:col-span-2">
                <Textarea rows={2} maxLength={500} {...form.register("observacao")} />
              </Campo>
            </div>
            <MensagemErro erro={salvar.error} />
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
      </DialogContent>
    </Dialog>
  );
}
