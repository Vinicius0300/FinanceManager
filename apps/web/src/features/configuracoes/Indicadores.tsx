import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Pencil, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { components } from "@/api/schema";
import { Secao } from "@/components/CabecalhoPagina";
import { Campo } from "@/components/Campo";
import { Carregando, EstadoErro, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import { hojeIso, paraIso } from "@/lib/datas";
import {
  aplicarErrosDaApi,
  dataObrigatoria,
  decimalObrigatorio,
  paraCampo,
} from "@/lib/formularios";
import { formatarData, formatarMoeda, formatarNumero } from "@/lib/formatacao";
import { INDICADORES, type DefinicaoIndicador } from "./definicoes";
import { subDays } from "date-fns";

type Indicador = components["schemas"]["IndicadorSaida"];

const FONTES: Record<string, string> = {
  bcb_sgs: "Banco Central (SGS)",
  yfinance: "Yahoo Finance",
  manual: "Manual",
};

/** Janela consultada para achar o último valor (o IPCA sai uma vez por mês, com atraso). */
const DIAS_JANELA = 120;

function useUltimoIndicador(def: DefinicaoIndicador, agora: Date) {
  const { cliente } = useClienteApi();
  const inicio = paraIso(subDays(agora, DIAS_JANELA));
  return useQuery({
    queryKey: ["indicadores", def.tipo, def.moeda, inicio],
    queryFn: async ({ signal }) => {
      const lista = exigir(
        await cliente.GET("/api/indicadores", {
          params: { query: { tipo: def.tipo, moeda: def.moeda, inicio } },
          signal,
        }),
      );
      return [...lista].sort((a, b) => a.data.localeCompare(b.data)).at(-1) ?? null;
    },
  });
}

function formatarIndicador(def: DefinicaoIndicador, valor: string): string {
  return def.tipo === "cambio"
    ? formatarMoeda(valor, "BRL", { casas: 4 })
    : `${formatarNumero(valor, { minimo: 2, maximo: 4 })}% ${def.unidade.replace("% ", "")}`;
}

/** Últimos valores de Selic, CDI, IPCA e câmbio, com data e fonte, e lançamento manual. */
export function SecaoIndicadores({ agora }: { agora: Date }) {
  return (
    <Secao titulo="Indicadores">
      <p className="mb-3 text-sm text-muted-foreground">
        Coletados automaticamente. Se a fonte falhar, lance o valor à mão: um valor manual nunca é
        sobrescrito pela coleta.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {INDICADORES.map((def) => (
          <CartaoIndicador key={def.tipo} def={def} agora={agora} />
        ))}
      </div>
    </Secao>
  );
}

function CartaoIndicador({ def, agora }: { def: DefinicaoIndicador; agora: Date }) {
  const ultimo = useUltimoIndicador(def, agora);
  const [dialogo, setDialogo] = useState<"novo" | "editar" | null>(null);
  return (
    <section aria-label={def.nome} className="flex flex-col gap-1 rounded-lg border p-3">
      <h3 className="text-xs font-semibold text-muted-foreground">{def.nome}</h3>
      {ultimo.isPending ? (
        <Carregando className="py-2" />
      ) : ultimo.isError ? (
        <EstadoErro erro={ultimo.error} className="py-2" />
      ) : ultimo.data ? (
        <>
          <p className="tabular text-lg font-semibold">
            {formatarIndicador(def, ultimo.data.valor)}
          </p>
          <p className="text-xs text-muted-foreground">
            {formatarData(ultimo.data.data)} ·{" "}
            {FONTES[ultimo.data.fonte ?? ""] ?? ultimo.data.fonte ?? "fonte desconhecida"}
          </p>
        </>
      ) : (
        <p className="text-sm text-aviso-texto">Sem valor nos últimos {DIAS_JANELA} dias.</p>
      )}
      <div className="mt-1 flex gap-1">
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setDialogo("novo");
          }}
        >
          <Plus aria-hidden />
          Lançar
        </Button>
        {ultimo.data && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setDialogo("editar");
            }}
          >
            <Pencil aria-hidden />
            Editar
          </Button>
        )}
      </div>
      {dialogo && (
        <DialogoIndicador
          def={def}
          hoje={hojeIso(agora)}
          indicador={dialogo === "editar" ? (ultimo.data ?? undefined) : undefined}
          aoFechar={() => {
            setDialogo(null);
          }}
        />
      )}
    </section>
  );
}

function DialogoIndicador({
  def,
  hoje,
  indicador,
  aoFechar,
}: {
  def: DefinicaoIndicador;
  hoje: string;
  indicador?: Indicador;
  aoFechar: () => void;
}) {
  const { cliente } = useClienteApi();
  const esquema = useMemo(
    () =>
      z.object({
        data: dataObrigatoria
          .refine((d) => d <= hoje, "A data não pode ser futura.")
          .refine((d) => def.tipo !== "ipca" || d.endsWith("-01"), "Use o dia 1º do mês."),
        valor: decimalObrigatorio({
          casas: def.casas,
          sinal:
            def.tipo === "cambio" ? "positivo" : def.tipo === "ipca" ? undefined : "naoNegativo",
        }),
      }),
    [def, hoje],
  );
  const salvar = useGravacao(async (dados: z.output<typeof esquema>) =>
    indicador
      ? exigir(
          await cliente.PUT("/api/indicadores/{indicador_id}", {
            params: { path: { indicador_id: indicador.id } },
            body: { valor: dados.valor },
          }),
        )
      : exigir(
          await cliente.POST("/api/indicadores", {
            body: { tipo: def.tipo, moeda: def.moeda, data: dados.data, valor: dados.valor },
          }),
        ),
  );
  const form = useForm<{ data: string; valor: string }, unknown, z.output<typeof esquema>>({
    resolver: zodResolver(esquema),
    defaultValues: {
      data: indicador?.data ?? (def.tipo === "ipca" ? `${hoje.slice(0, 7)}-01` : hoje),
      valor: paraCampo(indicador?.valor),
    },
  });
  const enviar = form.handleSubmit(async (dados) => {
    try {
      await salvar.mutateAsync(dados);
      aoFechar();
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, ["data", "valor"]);
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
          <DialogTitle>
            {indicador ? `Editar ${def.nome}` : `Lançar ${def.nome} manualmente`}
          </DialogTitle>
          <DialogDescription>{def.ajuda}</DialogDescription>
        </DialogHeader>
        <form
          noValidate
          className="grid gap-4"
          onSubmit={(e) => {
            void enviar(e);
          }}
        >
          <Campo
            rotulo="Data"
            erro={form.formState.errors.data?.message}
            ajuda={indicador ? "Na edição só o valor muda." : undefined}
          >
            <Input
              type="date"
              max={hoje}
              disabled={indicador !== undefined}
              {...form.register("data")}
            />
          </Campo>
          <Campo
            rotulo={`Valor (${def.unidade})`}
            obrigatorio
            erro={form.formState.errors.valor?.message}
          >
            <Input inputMode="decimal" {...form.register("valor")} />
          </Campo>
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
      </DialogContent>
    </Dialog>
  );
}
