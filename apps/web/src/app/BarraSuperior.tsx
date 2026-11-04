import { Loader2, RefreshCw } from "lucide-react";
import { useMemo } from "react";
import { SeletorTema } from "@/components/SeletorTema";
import { Button } from "@/components/ui/button";
import {
  useAtualizacao,
  useForcarAtualizacao,
  useStatusCotacoes,
} from "@/features/carteira/consultas";
import { usePosicoes } from "@/features/dashboard/consultas";
import { useEstadoAtualizacao } from "@/features/tempo-real/atualizacao";
import { formatarDataHora } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import { contarStatus, textoStatus } from "./status-cotacoes";

/**
 * Topo global (Parte 5A): chip de status das cotações, hora da última atualização,
 * "Atualizar cotações" (vale para todas as telas) e o switch de tema.
 */
export function BarraSuperior() {
  return (
    <header className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 border-b px-5 py-2">
      <ChipStatusCotacoes />
      <StatusAtualizacao />
      <BotaoAtualizar />
      <SeletorTema />
    </header>
  );
}

/** "N em dia · N defasadas · N com erro" dos ativos com posição aberta (Análise Geral). */
export function ChipStatusCotacoes() {
  const status = useStatusCotacoes();
  const posicoes = usePosicoes(null);
  const contagem = useMemo(() => {
    if (!status.data || !posicoes.data) return null;
    return contarStatus(status.data, new Set(posicoes.data.map((p) => p.ativo_id)));
  }, [status.data, posicoes.data]);
  if (!contagem) return null;
  const texto = textoStatus(contagem);
  return (
    <p
      role="status"
      aria-label={`Cotações: ${texto}`}
      className="tabular inline-flex items-center gap-2.5 rounded-full border bg-muted px-2.5 py-0.5 text-xs font-semibold"
    >
      {texto.split(" · ").map((parte) => (
        <span key={parte} aria-hidden className="inline-flex items-center gap-1.5">
          <span className={cn("size-2 shrink-0 rounded-full", corDaParte(parte))} />
          {parte}
        </span>
      ))}
    </p>
  );
}

function corDaParte(parte: string): string {
  if (parte.includes("erro")) return "bg-perigo";
  if (parte.includes("defasad")) return "bg-aviso";
  return "bg-sucesso";
}

/** Última atualização automática concluída (vem do stream SSE). */
function StatusAtualizacao() {
  const ultimoFim = useEstadoAtualizacao((s) => s.ultimoFim);
  const erros = useEstadoAtualizacao((s) => s.ultimosErros);
  const mensagem = useEstadoAtualizacao((s) => s.ultimaMensagemErro);
  if (!ultimoFim) return null;
  return (
    <p className="text-xs text-muted-foreground" aria-live="polite">
      Cotações atualizadas em {formatarDataHora(ultimoFim)}
      {erros > 0 && (
        <span className="text-aviso-texto" title={mensagem ?? undefined}>
          {" "}
          · {erros} {erros === 1 ? "falha" : "falhas"}
        </span>
      )}
    </p>
  );
}

/** Atualização forçada: dispara e libera a tela; o progresso vem pelo SSE. */
export function BotaoAtualizar() {
  const atualizacao = useAtualizacao();
  const forcar = useForcarAtualizacao();
  const emAndamento = atualizacao.data?.em_andamento ?? false;
  return (
    <div className="flex flex-col items-end">
      <Button
        size="sm"
        disabled={forcar.isPending || emAndamento}
        onClick={() => {
          forcar.mutate();
        }}
      >
        {emAndamento || forcar.isPending ? (
          <Loader2 aria-hidden className="animate-spin" />
        ) : (
          <RefreshCw aria-hidden />
        )}
        {emAndamento ? "Atualizando…" : "Atualizar cotações"}
      </Button>
      {forcar.isError && (
        <span role="alert" className="mt-1 max-w-xs text-right text-xs text-negativo">
          {forcar.error.message}
        </span>
      )}
    </div>
  );
}
