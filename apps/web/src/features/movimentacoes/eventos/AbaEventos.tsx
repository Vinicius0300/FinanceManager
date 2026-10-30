import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import type { components } from "@/api/schema";
import { Secao } from "@/components/CabecalhoPagina";
import { Campo } from "@/components/Campo";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Carregando, EstadoErro, EstadoVazio, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import {
  indexarPorId,
  rotuloAtivo,
  useAtivos,
  useGravacao,
  useTiposAtivo,
} from "@/lib/consultas-comuns";
import { ehZero } from "@/lib/decimal";
import { hojeIso } from "@/lib/datas";
import {
  aplicarErrosDaApi,
  CASAS,
  dataObrigatoria,
  lerDecimal,
  paraCampo,
} from "@/lib/formularios";
import { formatarData, formatarMoeda } from "@/lib/formatacao";
import { NOMES_EVENTO } from "./rotulos";

type Evento = components["schemas"]["EventoSaida"];
type EventoEntrada = components["schemas"]["EventoEntrada"];
type TipoEvento = Evento["tipo"];

function useEventos() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["eventos-corporativos"],
    queryFn: async ({ signal }) =>
      exigir(await cliente.GET("/api/eventos-corporativos", { signal })),
  });
}

/** Desdobramentos, grupamentos e bonificações (aplicados na data "ex", em todas as instituições). */
export function AbaEventos({ agora }: { agora: Date }) {
  const eventos = useEventos();
  const ativos = indexarPorId(useAtivos().data);
  const [editando, setEditando] = useState<Evento | "novo" | null>(null);
  const [excluindo, setExcluindo] = useState<Evento | null>(null);
  const { cliente } = useClienteApi();
  const excluir = useGravacao(async (id: number) => {
    exigir(
      await cliente.DELETE("/api/eventos-corporativos/{evento_id}", {
        params: { path: { evento_id: id } },
      }),
    );
  });

  return (
    <Secao
      titulo="Eventos corporativos"
      acoes={
        <Button
          size="sm"
          onClick={() => {
            setEditando("novo");
          }}
        >
          <Plus aria-hidden />
          Novo evento
        </Button>
      }
    >
      {eventos.isPending ? (
        <Carregando />
      ) : eventos.isError ? (
        <EstadoErro
          erro={eventos.error}
          aoTentarNovamente={() => {
            void eventos.refetch();
          }}
        />
      ) : eventos.data.length === 0 ? (
        <EstadoVazio
          titulo="Nenhum evento corporativo"
          descricao="Registre desdobramentos, grupamentos e bonificações para ajustar a quantidade das posições."
        />
      ) : (
        <Table aria-label="Eventos corporativos">
          <TableHeader>
            <TableRow>
              <TableHead>Data "ex"</TableHead>
              <TableHead>Evento</TableHead>
              <TableHead>Ativo</TableHead>
              <TableHead>Proporção</TableHead>
              <TableHead className="text-right">Custo unitário</TableHead>
              <TableHead className="text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {eventos.data.map((e) => {
              const ativo = ativos.get(e.ativo_id);
              return (
                <TableRow key={e.id}>
                  <TableCell className="tabular">{formatarData(e.data)}</TableCell>
                  <TableCell>{NOMES_EVENTO[e.tipo]}</TableCell>
                  <TableCell>{rotuloAtivo(ativo)}</TableCell>
                  <TableCell className="tabular">
                    {e.proporcao_de}:{e.proporcao_para}
                  </TableCell>
                  <TableCell className="tabular text-right">
                    {ehZero(e.custo_unitario) ? "—" : formatarMoeda(e.custo_unitario, ativo?.moeda)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Editar ${NOMES_EVENTO[e.tipo]} de ${formatarData(e.data)}`}
                      onClick={() => {
                        setEditando(e);
                      }}
                    >
                      <Pencil aria-hidden />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Excluir ${NOMES_EVENTO[e.tipo]} de ${formatarData(e.data)}`}
                      onClick={() => {
                        excluir.reset();
                        setExcluindo(e);
                      }}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
      {editando && (
        <DialogoEvento
          evento={editando === "novo" ? undefined : editando}
          hoje={hojeIso(agora)}
          aoFechar={() => {
            setEditando(null);
          }}
        />
      )}
      <DialogoConfirmacao
        aberto={excluindo !== null}
        aoMudar={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo="Excluir este evento?"
        descricao="As posições do ativo são recalculadas. A exclusão é recusada se deixar alguma venda posterior inválida."
        ocupado={excluir.isPending}
        erro={excluir.error}
        aoConfirmar={() => {
          if (!excluindo) return;
          excluir.mutate(excluindo.id, {
            onSuccess: () => {
              setExcluindo(null);
            },
          });
        }}
      />
    </Secao>
  );
}

interface ValoresEvento {
  ativo_id: string;
  tipo: TipoEvento;
  data: string;
  proporcao_de: string;
  proporcao_para: string;
  custo_unitario: string;
  cambio: string;
  observacao: string;
}

const proporcao = z
  .string()
  .trim()
  .regex(/^\d+$/, "Use um número inteiro.")
  .refine((v) => Number(v) > 0, "Use um número maior que zero.");

function criarEsquemaEvento(moedaDe: (ativoId: number) => string | undefined) {
  return z
    .object({
      ativo_id: z.string().min(1, "Escolha o ativo."),
      tipo: z.enum(["desdobramento", "grupamento", "bonificacao"]),
      data: dataObrigatoria,
      proporcao_de: proporcao,
      proporcao_para: proporcao,
      custo_unitario: z.string(),
      cambio: z.string(),
      observacao: z.string().max(500, "Use no máximo 500 caracteres."),
    })
    .transform((v, ctx): EventoEntrada => {
      const de = Number(v.proporcao_de);
      const para = Number(v.proporcao_para);
      if (v.tipo === "grupamento" ? para >= de : para <= de) {
        ctx.addIssue({
          code: "custom",
          path: ["proporcao_para"],
          message:
            v.tipo === "grupamento"
              ? "No grupamento a quantidade final é menor (ex.: 10:1)."
              : "A quantidade final deve ser maior (ex.: 1:2 ou 10:11).",
        });
      }
      const moeda = moedaDe(Number(v.ativo_id));
      return {
        ativo_id: Number(v.ativo_id),
        tipo: v.tipo,
        data: v.data,
        proporcao_de: de,
        proporcao_para: para,
        custo_unitario:
          v.tipo === "bonificacao"
            ? (lerDecimal(ctx, "custo_unitario", v.custo_unitario, {
                casas: CASAS.preco,
                sinal: "naoNegativo",
              }) ?? "0")
            : "0",
        cambio:
          moeda && moeda !== "BRL"
            ? lerDecimal(ctx, "cambio", v.cambio, { casas: CASAS.cambio, sinal: "positivo" })
            : null,
        observacao: v.observacao.trim() || null,
      };
    });
}

function DialogoEvento({
  evento,
  hoje,
  aoFechar,
}: {
  evento?: Evento;
  hoje: string;
  aoFechar: () => void;
}) {
  const { cliente } = useClienteApi();
  const ativos = useAtivos();
  const tipos = useTiposAtivo();
  // Eventos só fazem sentido para posições em cotas (ações, fundos, cripto...).
  const elegiveis = (ativos.data ?? []).filter(
    (a) => tipos.data?.find((t) => t.slug === a.tipo)?.modo === "cotas",
  );
  const esquema = useMemo(
    () => criarEsquemaEvento((id) => ativos.data?.find((a) => a.id === id)?.moeda),
    [ativos.data],
  );
  const salvar = useGravacao(async (corpo: EventoEntrada) =>
    evento
      ? exigir(
          await cliente.PUT("/api/eventos-corporativos/{evento_id}", {
            params: { path: { evento_id: evento.id } },
            body: corpo,
          }),
        )
      : exigir(await cliente.POST("/api/eventos-corporativos", { body: corpo })),
  );
  const form = useForm<ValoresEvento, unknown, z.output<typeof esquema>>({
    resolver: zodResolver(esquema),
    defaultValues: {
      ativo_id: evento ? String(evento.ativo_id) : "",
      tipo: evento?.tipo ?? "desdobramento",
      data: evento?.data ?? hoje,
      proporcao_de: evento ? String(evento.proporcao_de) : "1",
      proporcao_para: evento ? String(evento.proporcao_para) : "2",
      custo_unitario:
        evento && !ehZero(evento.custo_unitario) ? paraCampo(evento.custo_unitario) : "",
      cambio: evento ? paraCampo(evento.cambio) : "",
      observacao: evento?.observacao ?? "",
    },
  });
  const erros = form.formState.errors;
  const tipo = useWatch({ control: form.control, name: "tipo" });
  const ativoId = useWatch({ control: form.control, name: "ativo_id" });
  const moeda = ativos.data?.find((a) => a.id === Number(ativoId))?.moeda ?? "BRL";
  const enviar = form.handleSubmit(async (corpo) => {
    try {
      await salvar.mutateAsync(corpo);
      aoFechar();
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, Object.keys(form.getValues()), {
        proporcao: "proporcao_para",
      });
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
          <DialogTitle>{evento ? "Editar evento" : "Novo evento corporativo"}</DialogTitle>
          <DialogDescription>
            Proporção "de:para": desdobramento 1:2 dobra a quantidade; grupamento 10:1 divide por
            10; bonificação 10:11 dá 1 ação a cada 10.
          </DialogDescription>
        </DialogHeader>
        {ativos.isPending || tipos.isPending ? (
          <Carregando />
        ) : (
          <form
            noValidate
            onSubmit={(e) => {
              void enviar(e);
            }}
            className="grid gap-4"
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo rotulo="Ativo" obrigatorio erro={erros.ativo_id?.message}>
                <Select {...form.register("ativo_id")} disabled={evento !== undefined}>
                  <option value="">Escolha…</option>
                  {elegiveis.map((a) => (
                    <option key={a.id} value={a.id}>
                      {rotuloAtivo(a)}
                    </option>
                  ))}
                </Select>
              </Campo>
              <Campo rotulo="Evento" obrigatorio erro={erros.tipo?.message}>
                <Select {...form.register("tipo")}>
                  {Object.entries(NOMES_EVENTO).map(([valor, rotulo]) => (
                    <option key={valor} value={valor}>
                      {rotulo}
                    </option>
                  ))}
                </Select>
              </Campo>
              <Campo rotulo='Data "ex"' obrigatorio erro={erros.data?.message}>
                <Input type="date" {...form.register("data")} />
              </Campo>
              <div className="grid grid-cols-2 gap-2">
                <Campo rotulo="De" obrigatorio erro={erros.proporcao_de?.message}>
                  <Input inputMode="numeric" {...form.register("proporcao_de")} />
                </Campo>
                <Campo rotulo="Para" obrigatorio erro={erros.proporcao_para?.message}>
                  <Input inputMode="numeric" {...form.register("proporcao_para")} />
                </Campo>
              </div>
              {tipo === "bonificacao" && (
                <Campo
                  rotulo={`Custo unitário atribuído (${moeda})`}
                  erro={erros.custo_unitario?.message}
                  ajuda="Informado pela empresa; vazio = zero."
                >
                  <Input inputMode="decimal" {...form.register("custo_unitario")} />
                </Campo>
              )}
              {moeda !== "BRL" && (
                <Campo
                  rotulo={`Câmbio (R$ por ${moeda})`}
                  erro={erros.cambio?.message}
                  ajuda="Opcional. Se vazio, usa a PTAX da data."
                >
                  <Input inputMode="decimal" {...form.register("cambio")} />
                </Campo>
              )}
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
