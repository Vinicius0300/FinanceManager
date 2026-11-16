import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import type { z } from "zod";
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
import { Input, Select } from "@/components/ui/input";
import { useCategorias } from "@/features/receitas-despesas/consultas";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao, useInstituicoes } from "@/lib/consultas-comuns";
import { aplicarErrosDaApi, paraCampo } from "@/lib/formularios";
import {
  DICA_TARIFA_USD,
  esquemaTransferencia,
  MOEDAS_TRANSFERENCIA,
  useTransferencia,
  type Transferencia,
  type TransferenciaEntrada,
} from "./transferencias";

type Valores = z.input<typeof esquemaTransferencia>;

/**
 * Nova transferência ou edição (`transferenciaId`). A origem precisa ter saldo para valor +
 * tarifa: sem saldo a API recusa (422) e a mensagem aparece aqui, sem ajuste.
 */
export function DialogoTransferencia({
  transferenciaId,
  origemPadrao,
  moedaPadrao,
  hoje,
  aoFechar,
}: {
  transferenciaId?: number;
  origemPadrao?: number;
  moedaPadrao?: string;
  hoje: string;
  aoFechar: () => void;
}) {
  const existente = useTransferencia(transferenciaId ?? null);
  const carregandoExistente = transferenciaId !== undefined && existente.isPending;
  return (
    <Dialog
      open
      onOpenChange={(aberto) => {
        if (!aberto) aoFechar();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {transferenciaId ? "Editar transferência" : "Nova transferência"}
          </DialogTitle>
          <DialogDescription>
            Dinheiro passado de uma instituição para outra, na mesma moeda. Não é receita nem
            despesa: só a tarifa entra como despesa da origem.
          </DialogDescription>
        </DialogHeader>
        {carregandoExistente ? (
          <Carregando />
        ) : existente.isError ? (
          <MensagemErro erro={existente.error} />
        ) : (
          <FormularioTransferencia
            transferencia={existente.data}
            origemPadrao={origemPadrao}
            moedaPadrao={moedaPadrao}
            hoje={hoje}
            aoFechar={aoFechar}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function FormularioTransferencia({
  transferencia,
  origemPadrao,
  moedaPadrao,
  hoje,
  aoFechar,
}: {
  transferencia?: Transferencia;
  origemPadrao?: number;
  moedaPadrao?: string;
  hoje: string;
  aoFechar: () => void;
}) {
  const instituicoes = useInstituicoes();
  const categorias = useCategorias();
  const { cliente } = useClienteApi();
  const salvar = useGravacao(async (corpo: TransferenciaEntrada) =>
    transferencia
      ? exigir(
          await cliente.PUT("/api/transferencias/{transferencia_id}", {
            params: { path: { transferencia_id: transferencia.id } },
            body: corpo,
          }),
        )
      : exigir(await cliente.POST("/api/transferencias", { body: corpo })),
  );
  const moedaInicial = transferencia?.moeda ?? moedaPadrao ?? "BRL";
  const origemInicial = transferencia?.origem_id ?? origemPadrao;
  const form = useForm<Valores, unknown, TransferenciaEntrada>({
    resolver: zodResolver(esquemaTransferencia),
    defaultValues: {
      data: transferencia?.data ?? hoje,
      origem_id: origemInicial === undefined ? "" : String(origemInicial),
      destino_id: transferencia ? String(transferencia.destino_id) : "",
      moeda: moedaInicial === "USD" ? "USD" : "BRL",
      valor: paraCampo(transferencia?.valor),
      tarifa: transferencia && transferencia.tarifa !== "0" ? paraCampo(transferencia.tarifa) : "",
      categoria_tarifa_id: transferencia?.categoria_tarifa_id
        ? String(transferencia.categoria_tarifa_id)
        : "",
      descricao: transferencia?.descricao ?? "",
    },
  });
  const erros = form.formState.errors;
  const moeda = useWatch({ control: form.control, name: "moeda" });
  const emDolar = moeda !== "BRL";
  useEffect(() => {
    if (emDolar) {
      form.setValue("tarifa", "");
      form.setValue("categoria_tarifa_id", "");
    }
  }, [emDolar, form]);
  const despesas = (categorias.data ?? []).filter((c) => c.tipo === "despesa");

  const enviar = form.handleSubmit(async (corpo) => {
    try {
      await salvar.mutateAsync(corpo);
      aoFechar();
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, [
        "data",
        "origem_id",
        "destino_id",
        "moeda",
        "valor",
        "tarifa",
        "categoria_tarifa_id",
        "descricao",
      ]);
    }
  });

  if (instituicoes.isPending) return <Carregando />;
  if (instituicoes.isError) return <MensagemErro erro={instituicoes.error} />;
  const opcoes = instituicoes.data.map((i) => (
    <option key={i.id} value={i.id}>
      {i.nome}
    </option>
  ));

  return (
    <form
      noValidate
      className="grid gap-4"
      onSubmit={(e) => {
        void enviar(e);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo rotulo="Origem" obrigatorio erro={erros.origem_id?.message}>
          <Select {...form.register("origem_id")}>
            <option value="">Escolha…</option>
            {opcoes}
          </Select>
        </Campo>
        <Campo rotulo="Destino" obrigatorio erro={erros.destino_id?.message}>
          <Select {...form.register("destino_id")}>
            <option value="">Escolha…</option>
            {opcoes}
          </Select>
        </Campo>
        <Campo rotulo="Data" obrigatorio erro={erros.data?.message}>
          <Input type="date" {...form.register("data")} />
        </Campo>
        <Campo rotulo="Moeda" erro={erros.moeda?.message}>
          <Select {...form.register("moeda")}>
            {MOEDAS_TRANSFERENCIA.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Campo>
        <Campo rotulo={`Valor (${moeda})`} obrigatorio erro={erros.valor?.message}>
          <Input inputMode="decimal" placeholder="0,00" {...form.register("valor")} />
        </Campo>
        <Campo
          rotulo="Tarifa (R$)"
          erro={erros.tarifa?.message}
          ajuda={emDolar ? DICA_TARIFA_USD : "Opcional. Entra como despesa da origem."}
        >
          <Input
            inputMode="decimal"
            placeholder="0,00"
            disabled={emDolar}
            {...form.register("tarifa")}
          />
        </Campo>
        <Campo rotulo="Categoria da tarifa" erro={erros.categoria_tarifa_id?.message}>
          <Select disabled={emDolar} {...form.register("categoria_tarifa_id")}>
            <option value="">Sem categoria</option>
            {despesas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </Select>
        </Campo>
        <Campo rotulo="Descrição" erro={erros.descricao?.message}>
          <Input maxLength={300} {...form.register("descricao")} />
        </Campo>
      </div>
      <MensagemErro erro={salvar.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={aoFechar} disabled={salvar.isPending}>
          Cancelar
        </Button>
        <Button type="submit" disabled={salvar.isPending}>
          {salvar.isPending && <Loader2 aria-hidden className="animate-spin" />}
          Salvar
        </Button>
      </div>
    </form>
  );
}
