import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Pencil, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Campo } from "@/components/Campo";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Carregando, EstadoErro, EstadoVazio, MensagemErro } from "@/components/Estados";
import { GraficoPreco } from "@/components/graficos/GraficoPreco";
import { IndicadorDefasado } from "@/components/IndicadorDefasado";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { nomeDoTipo, useTiposAtivo, type Ativo } from "@/lib/consultas-comuns";
import { hojeIso, inicioDaJanela } from "@/lib/datas";
import { aplicarErrosDaApi, CASAS, dataObrigatoria, decimalObrigatorio } from "@/lib/formularios";
import { formatarData, formatarDataHora, formatarPreco } from "@/lib/formatacao";
import {
  useExcluirAtivo,
  useExcluirPreco,
  usePrecos,
  useRegistrarPrecoManual,
  type StatusAtivo,
} from "./consultas";
import { DialogoAtivo } from "./DialogoAtivo";
import { NOMES_ORIGEM } from "./rotulos";

/**
 * Detalhe de um ativo: cotação e status da coleta, gráfico de preço de 1 ano (Lightweight
 * Charts), preço manual (só para ativos cotados) e as ações de editar e excluir.
 */
export function DetalheAtivo({
  ativo,
  status,
  aoFechar,
  agora = new Date(),
}: {
  ativo: Ativo;
  status: StatusAtivo | undefined;
  aoFechar: () => void;
  agora?: Date;
}) {
  const tipos = useTiposAtivo();
  const tipo = tipos.data?.find((t) => t.slug === ativo.tipo);
  const cotado = tipo?.modo === "cotas";
  const [editando, setEditando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const excluir = useExcluirAtivo();

  return (
    <>
      <Dialog
        open={!editando}
        onOpenChange={(aberto) => {
          if (!aberto) aoFechar();
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {ativo.simbolo ? `${ativo.simbolo} · ${ativo.nome}` : ativo.nome}
            </DialogTitle>
            <DialogDescription>
              {nomeDoTipo(tipos.data, ativo.tipo)} · {ativo.moeda}
              {ativo.provider && ` · fonte ${ativo.provider}`}
              {ativo.simbolo_externo && ` (${ativo.simbolo_externo})`}
            </DialogDescription>
          </DialogHeader>
          <StatusCotacao status={status} moeda={ativo.moeda} />
          {cotado ? (
            <>
              <HistoricoPreco ativo={ativo} agora={agora} />
              <PrecoManual ativo={ativo} hoje={hojeIso(agora)} />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              {tipo?.nome ?? "Este tipo"} tem valor calculado pelos indicadores (sem cotação de
              mercado), por isso não aceita valor manual.
            </p>
          )}
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button
              variant="outline"
              onClick={() => {
                setEditando(true);
              }}
            >
              <Pencil aria-hidden />
              Editar
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                excluir.reset();
                setExcluindo(true);
              }}
            >
              <Trash2 aria-hidden />
              Excluir
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <DialogoAtivo
        aberto={editando}
        ativo={ativo}
        aoMudar={(aberto) => {
          setEditando(aberto);
        }}
      />
      <DialogoConfirmacao
        aberto={excluindo}
        aoMudar={setExcluindo}
        titulo={`Excluir ${ativo.simbolo ?? ativo.nome}?`}
        descricao="O ativo só pode ser excluído se não tiver transações. Os preços salvos saem junto."
        ocupado={excluir.isPending}
        erro={excluir.error}
        aoConfirmar={() => {
          excluir.mutate(ativo.id, {
            onSuccess: () => {
              setExcluindo(false);
              aoFechar();
            },
          });
        }}
      />
    </>
  );
}

function StatusCotacao({ status, moeda }: { status: StatusAtivo | undefined; moeda: string }) {
  if (!status) return null;
  return (
    <dl className="grid gap-x-6 gap-y-2 rounded-lg border p-3 text-sm sm:grid-cols-3">
      <div>
        <dt className="text-xs text-muted-foreground">Último preço</dt>
        <dd className="tabular font-medium">
          {formatarPreco(status.valor, moeda)}{" "}
          <IndicadorDefasado defasado={status.defasado} aviso={status.aviso} />
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">Data e origem</dt>
        <dd>
          {status.data_hora ? formatarDataHora(status.data_hora) : formatarData(status.data)}
          {status.origem && ` · ${NOMES_ORIGEM[status.origem] ?? status.origem}`}
          {status.provider_preco && ` (${status.provider_preco})`}
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">Última tentativa de coleta</dt>
        <dd>
          {status.ultima_tentativa ? formatarDataHora(status.ultima_tentativa) : "—"}
          {status.provider && ` · ${status.provider}`}
        </dd>
      </div>
      {status.ultimo_erro && (
        <div className="sm:col-span-3">
          <dt className="text-xs text-muted-foreground">Último erro do provider</dt>
          <dd className="text-negativo">{status.ultimo_erro}</dd>
        </div>
      )}
      {status.aviso && (
        <div className="sm:col-span-3">
          <dt className="text-xs text-muted-foreground">Aviso</dt>
          <dd className="text-aviso-texto">{status.aviso}</dd>
        </div>
      )}
    </dl>
  );
}

function HistoricoPreco({ ativo, agora }: { ativo: Ativo; agora: Date }) {
  const precos = usePrecos(ativo.id, inicioDaJanela("1a", agora));
  const excluir = useExcluirPreco();
  const pontos = useMemo(
    () => [...(precos.data?.itens ?? [])].sort((a, b) => a.data.localeCompare(b.data)),
    [precos.data],
  );
  const manuais = pontos.filter((p) => p.origem === "manual").reverse();
  if (precos.isPending) return <Carregando texto="Carregando preços…" />;
  if (precos.isError) {
    return (
      <EstadoErro
        erro={precos.error}
        aoTentarNovamente={() => {
          void precos.refetch();
        }}
      />
    );
  }
  return (
    <section className="grid gap-2">
      <h3 className="text-sm font-semibold">Preço em 1 ano</h3>
      {pontos.length === 0 ? (
        <EstadoVazio
          titulo="Nenhum preço salvo ainda"
          descricao="A coleta automática busca o histórico de 1 ano. Use o valor manual se a fonte falhar."
        />
      ) : (
        <GraficoPreco
          rotulo={`Preço de ${ativo.simbolo ?? ativo.nome} em 1 ano`}
          pontos={pontos.map((p) => ({ data: p.data, valor: p.valor }))}
        />
      )}
      {manuais.length > 0 && (
        <div className="text-sm">
          <h4 className="mb-1 text-xs font-semibold text-muted-foreground">Valores manuais</h4>
          <ul className="grid gap-1">
            {manuais.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2">
                <span className="tabular">
                  {formatarData(p.data)} · {formatarPreco(p.valor, p.moeda)}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={excluir.isPending}
                  onClick={() => {
                    excluir.mutate(p.id);
                  }}
                  aria-label={`Excluir o valor manual de ${formatarData(p.data)}`}
                >
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
          <MensagemErro erro={excluir.error} />
        </div>
      )}
    </section>
  );
}

function criarEsquemaPreco(hoje: string) {
  return z.object({
    data: dataObrigatoria.refine((d) => d <= hoje, "A data não pode ser futura."),
    valor: decimalObrigatorio({ casas: CASAS.preco, sinal: "positivo" }),
  });
}

/** Valor manual (só ativos cotados): vale para o dia e não é sobrescrito pela coleta. */
export function PrecoManual({ ativo, hoje }: { ativo: Ativo; hoje: string }) {
  const registrar = useRegistrarPrecoManual();
  const esquema = useMemo(() => criarEsquemaPreco(hoje), [hoje]);
  const form = useForm<{ data: string; valor: string }, unknown, z.output<typeof esquema>>({
    resolver: zodResolver(esquema),
    defaultValues: { data: hoje, valor: "" },
  });
  const erros = form.formState.errors;
  const enviar = form.handleSubmit(async (dados) => {
    try {
      await registrar.mutateAsync({ ativoId: ativo.id, ...dados });
      form.reset({ data: hoje, valor: "" });
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, ["data", "valor"]);
    }
  });
  return (
    <form
      noValidate
      aria-label="Valor manual"
      onSubmit={(e) => {
        void enviar(e);
      }}
      className="grid gap-3 rounded-lg border p-3"
    >
      <div>
        <h3 className="text-sm font-semibold">Valor manual</h3>
        <p className="text-xs text-muted-foreground">
          Substitui a cotação automática daquele dia (use quando a fonte falhar).
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Campo rotulo="Data" erro={erros.data?.message}>
          <Input type="date" max={hoje} {...form.register("data")} />
        </Campo>
        <Campo rotulo={`Preço (${ativo.moeda})`} erro={erros.valor?.message}>
          <Input inputMode="decimal" placeholder="0,00" {...form.register("valor")} />
        </Campo>
        <Button type="submit" disabled={registrar.isPending}>
          {registrar.isPending && <Loader2 aria-hidden className="animate-spin" />}
          Salvar valor
        </Button>
      </div>
      <MensagemErro erro={registrar.error} />
    </form>
  );
}
