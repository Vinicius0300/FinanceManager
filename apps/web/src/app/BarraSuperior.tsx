import { ChevronDown, Eye, EyeOff, Loader2, RefreshCw } from "lucide-react";
import { useMemo } from "react";
import { SeletorTema } from "@/components/SeletorTema";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  useAtualizacao,
  useForcarAtualizacao,
  useStatusCotacoes,
} from "@/features/carteira/consultas";
import { usePosicoes } from "@/features/dashboard/consultas";
import { useEstadoAtualizacao } from "@/features/tempo-real/atualizacao";
import { formatarDataHora } from "@/lib/formatacao";
import { useValoresOcultosStore } from "@/lib/valores-ocultos";
import { cn } from "@/lib/utils";
import { PainelStatusCotacoes } from "./PainelStatusCotacoes";
import {
  COR_SITUACAO,
  contarStatus,
  partesStatus,
  soAbertos,
  textoStatus,
} from "./status-cotacoes";

/**
 * Topo global (Parte 5A): chip de status das cotações, hora da última atualização,
 * "Atualizar cotações" (vale para todas as telas), o olho do modo privacidade e o switch de tema.
 */
export function BarraSuperior() {
  return (
    <header className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 border-b px-5 py-2">
      <ChipStatusCotacoes />
      <StatusAtualizacao />
      <BotaoAtualizar />
      <BotaoOcultarValores />
      <SeletorTema />
    </header>
  );
}

/**
 * Chip "N em dia · N defasadas · N com erro · N manuais" dos ativos com posição aberta
 * (Análise Geral). Clicar abre o painel com a situação de cada ativo.
 */
export function ChipStatusCotacoes() {
  const status = useStatusCotacoes();
  const posicoes = usePosicoes(null);
  const dados = useMemo(() => {
    if (!status.data || !posicoes.data) return null;
    const abertos = new Set(posicoes.data.map((p) => p.ativo_id));
    return { itens: soAbertos(status.data, abertos), contagem: contarStatus(status.data, abertos) };
  }, [status.data, posicoes.data]);
  if (!dados) return null;
  const partes = partesStatus(dados.contagem);
  const texto = textoStatus(dados.contagem);
  return (
    <Popover>
      <PopoverTrigger
        aria-label={`Cotações: ${texto}. Ver a situação de cada ativo`}
        title="Ver a situação de cada ativo"
        className="tabular inline-flex items-center gap-2.5 rounded-full border bg-muted px-2.5 py-0.5 text-xs font-semibold transition-colors hover:border-primary focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none data-[state=open]:border-primary"
      >
        {partes.map((parte) => (
          <span key={parte.situacao} aria-hidden className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 shrink-0 rounded-full", COR_SITUACAO[parte.situacao])} />
            {parte.texto}
          </span>
        ))}
        <ChevronDown aria-hidden className="size-3.5 text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent align="start" className="p-0">
        <PainelStatusCotacoes itens={dados.itens} contagem={dados.contagem} />
      </PopoverContent>
    </Popover>
  );
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

/** Olho do modo privacidade: oculta/mostra os valores do usuário em todas as telas. */
export function BotaoOcultarValores() {
  const ocultos = useValoresOcultosStore((s) => s.ocultos);
  const alternar = useValoresOcultosStore((s) => s.alternar);
  const rotulo = ocultos ? "Mostrar valores" : "Ocultar valores";
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={rotulo}
      aria-pressed={ocultos}
      title={rotulo}
      onClick={alternar}
      className="text-muted-foreground hover:text-foreground"
    >
      {ocultos ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
    </Button>
  );
}
