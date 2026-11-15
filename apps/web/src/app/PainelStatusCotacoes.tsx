import { Loader2, RefreshCw, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PopoverClose } from "@/components/ui/popover";
import {
  useAtualizacao,
  useForcarAtualizacaoAtivos,
  type StatusAtivo,
} from "@/features/carteira/consultas";
import { nomeDoTipo, useTiposAtivo } from "@/lib/consultas-comuns";
import { tempoDecorrido } from "@/lib/datas";
import { formatarDataHora, formatarPreco } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import {
  agruparPorSituacao,
  COR_SITUACAO,
  idsDaSituacao,
  ORDEM_SITUACOES,
  quantidade,
  rotuloStatus,
  TITULO_SITUACAO,
  type ContagemStatus,
  type Situacao,
} from "./status-cotacoes";

/** Nomes legíveis das fontes de cotação (o backend manda o nome do registry). */
const FONTES: Record<string, string> = {
  yfinance: "Yahoo Finance",
  coingecko: "CoinGecko",
  tesouro: "Tesouro Transparente",
  cvm: "CVM",
};

type Filtro = "todos" | Situacao;

function fonte(item: StatusAtivo): string {
  if (item.situacao === "manual") return "sem fonte automática";
  if (item.origem === "calculado") return "calculado";
  return item.provider ? (FONTES[item.provider] ?? item.provider) : "sem fonte automática";
}

/** Texto do meio da linha: o porquê da situação. */
function descricao(item: StatusAtivo): string {
  switch (item.situacao) {
    case "com_erro":
      return item.ultimo_erro ?? "Falha na última atualização.";
    case "defasado":
      return item.aviso ?? "Usando o último preço salvo.";
    case "manual":
      return "Preço informado à mão.";
    case "em_dia":
      if (item.origem === "calculado") return "Calculado pelo indicador.";
      if (item.origem === "manual") return "Preço do dia informado à mão.";
      return "Automático.";
  }
}

/** Dica com as datas exatas (o painel mostra o tempo passado). */
function dica(item: StatusAtivo): string | undefined {
  const partes: string[] = [];
  if (item.data_hora) partes.push(`Preço de ${formatarDataHora(item.data_hora)}`);
  if (item.ultima_tentativa)
    partes.push(`Última tentativa: ${formatarDataHora(item.ultima_tentativa)}`);
  if (item.ultimo_sucesso) partes.push(`Último sucesso: ${formatarDataHora(item.ultimo_sucesso)}`);
  return partes.length > 0 ? partes.join("\n") : undefined;
}

function quando(item: StatusAtivo, agora: Date): string {
  if (item.data_hora) return tempoDecorrido(item.data_hora, agora);
  if (item.origem === "calculado") return "hoje";
  return "sem cotação";
}

function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("pt-BR");
}

interface Props {
  itens: StatusAtivo[];
  contagem: ContagemStatus;
}

/**
 * Painel aberto pelo chip da barra superior: situação de cada ativo com posição aberta,
 * filtros por situação, busca e atualização só dos defasados ou só dos com erro.
 */
export function PainelStatusCotacoes({ itens, contagem }: Props) {
  const [filtroEscolhido, setFiltro] = useState<Filtro>("todos");
  const [busca, setBusca] = useState("");
  // A situação escolhida pode esvaziar com o painel aberto (ex.: depois de atualizar os
  // defasados): aí o filtro volta a "Todos" em vez de mostrar uma lista vazia.
  const filtro =
    filtroEscolhido !== "todos" && quantidade(contagem, filtroEscolhido) === 0
      ? "todos"
      : filtroEscolhido;
  const tipos = useTiposAtivo();
  // O conteúdo do popover monta a cada abertura: o "há X" vale para o momento em que abriu.
  const [agora] = useState(() => new Date());

  const grupos = useMemo(() => {
    const termo = normalizar(busca.trim());
    const visiveis = itens.filter(
      (i) =>
        (filtro === "todos" || i.situacao === filtro) &&
        (!termo || normalizar(`${i.simbolo ?? ""} ${i.nome}`).includes(termo)),
    );
    return agruparPorSituacao(visiveis, rotuloStatus);
  }, [itens, filtro, busca]);

  const filtros: Filtro[] = [
    "todos",
    ...ORDEM_SITUACOES.filter((s) => quantidade(contagem, s) > 0),
  ];

  return (
    <div className="flex max-h-[min(80vh,620px)] w-[min(30rem,calc(100vw-2rem))] flex-col">
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <h2 className="text-sm font-semibold">Status das cotações</h2>
        <PopoverClose
          aria-label="Fechar"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <X aria-hidden className="size-4" />
        </PopoverClose>
      </div>

      <div
        className="flex flex-wrap gap-1.5 px-4 pb-2"
        role="group"
        aria-label="Filtrar por situação"
      >
        {filtros.map((f) => {
          const total = f === "todos" ? itens.length : quantidade(contagem, f);
          return (
            <button
              key={f}
              type="button"
              aria-pressed={filtro === f}
              onClick={() => {
                setFiltro(f);
              }}
              className={cn(
                "tabular inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
                filtro === f
                  ? "border-primary bg-primary/15 text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {f !== "todos" && (
                <span aria-hidden className={cn("size-2 rounded-full", COR_SITUACAO[f])} />
              )}
              {f === "todos" ? "Todos" : TITULO_SITUACAO[f]} {total}
            </button>
          );
        })}
      </div>

      <div className="relative mx-4 mb-2">
        <Search
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          type="search"
          aria-label="Buscar ativo"
          placeholder="Buscar ticker ou nome"
          value={busca}
          onChange={(e) => {
            setBusca(e.target.value);
          }}
          className="h-8 pl-8 text-sm"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto border-t">
        {itens.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            Nenhum ativo com posição aberta.
          </p>
        ) : grupos.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            Nenhum ativo encontrado.
          </p>
        ) : (
          grupos.map((grupo) => (
            <section key={grupo.situacao} aria-label={TITULO_SITUACAO[grupo.situacao]}>
              <h3 className="px-4 pt-2.5 pb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                {TITULO_SITUACAO[grupo.situacao]}
              </h3>
              <ul>
                {grupo.itens.map((item) => (
                  <li
                    key={item.ativo_id}
                    title={dica(item)}
                    className="grid grid-cols-[0.5rem_minmax(0,1.1fr)_minmax(0,1fr)_auto] items-center gap-x-3 border-t px-4 py-2 text-sm"
                  >
                    <span
                      aria-hidden
                      className={cn("size-2 rounded-full", COR_SITUACAO[item.situacao])}
                    />
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{rotuloStatus(item)}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {nomeDoTipo(tipos.data, item.tipo)} · {fonte(item)}
                      </p>
                    </div>
                    <p
                      className={cn(
                        "line-clamp-2 text-xs",
                        item.situacao === "com_erro" ? "text-negativo" : "text-muted-foreground",
                      )}
                    >
                      {descricao(item)}
                    </p>
                    <div className="tabular text-right text-xs">
                      {item.valor && <p>{formatarPreco(item.valor, item.moeda)}</p>}
                      <p className="text-muted-foreground">{quando(item, agora)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      <RodapeAtualizar itens={itens} contagem={contagem} />
    </div>
  );
}

function RodapeAtualizar({ itens, contagem }: Props) {
  const atualizacao = useAtualizacao();
  const forcar = useForcarAtualizacaoAtivos();
  const [pedido, setPedido] = useState<Situacao | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const emAndamento = (atualizacao.data?.em_andamento ?? false) || forcar.isPending;

  function atualizar(situacao: "defasado" | "com_erro") {
    const ids = idsDaSituacao(itens, situacao);
    forcar.reset();
    if (ids.length === 0) {
      setAviso(situacao === "defasado" ? "Nenhum ativo defasado." : "Nenhum ativo com erro.");
      return;
    }
    setAviso(null);
    setPedido(situacao);
    forcar.mutate(ids);
  }

  const botoes = [
    { situacao: "defasado", rotulo: "Atualizar valores defasados" },
    { situacao: "com_erro", rotulo: "Atualizar valores com erro" },
  ] as const;

  return (
    <div className="border-t px-4 py-2.5">
      <p className="mb-2 text-xs text-muted-foreground">Só ativos com posição aberta</p>
      <div className="flex flex-wrap justify-end gap-2">
        {botoes.map(({ situacao, rotulo }) => {
          const girando = emAndamento && pedido === situacao;
          return (
            <Button
              key={situacao}
              variant="outline"
              size="sm"
              disabled={emAndamento}
              onClick={() => {
                atualizar(situacao);
              }}
              aria-label={`${rotulo} (${quantidade(contagem, situacao)})`}
            >
              {girando ? (
                <Loader2 aria-hidden className="animate-spin" />
              ) : (
                <RefreshCw aria-hidden />
              )}
              <span aria-hidden className={cn("size-2 rounded-full", COR_SITUACAO[situacao])} />
              {rotulo} ({quantidade(contagem, situacao)})
            </Button>
          );
        })}
      </div>
      {(aviso || forcar.isError) && (
        <p
          role={forcar.isError ? "alert" : "status"}
          className={cn(
            "mt-2 text-right text-xs",
            forcar.isError ? "text-negativo" : "text-muted-foreground",
          )}
        >
          {forcar.isError ? forcar.error.message : aviso}
        </p>
      )}
    </div>
  );
}
