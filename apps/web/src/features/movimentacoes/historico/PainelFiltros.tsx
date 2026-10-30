import { X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, Select } from "@/components/ui/input";
import { nomeDoTipo, useInstituicoes, useTiposAtivo } from "@/lib/consultas-comuns";
import { PERIODOS, type Periodo } from "@/lib/datas";
import { plural } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import {
  CLASSES_OPERACAO,
  etiquetasDosFiltros,
  NOMES_OPERACAO,
  OPERACOES,
  type FiltrosHistorico,
  type Situacao,
} from "./filtros";

const ESPERA_BUSCA_MS = 300;

/** Filtros do histórico, etiquetas removíveis, contador "N de M" e "Limpar filtros". */
export function PainelFiltros({
  filtros,
  aoMudar,
  aoLimpar,
  contagem,
}: {
  filtros: FiltrosHistorico;
  aoMudar: (filtros: FiltrosHistorico) => void;
  aoLimpar: () => void;
  contagem: { filtradas: number; total: number } | null;
}) {
  const tipos = useTiposAtivo();
  const instituicoes = useInstituicoes();
  const id = useId();
  const [busca, setBusca] = useState(filtros.busca);
  const [buscaDaUrl, setBuscaDaUrl] = useState(filtros.busca);

  // Busca alterada de fora (etiqueta "×", Limpar filtros, voltar à tela): acompanha a URL.
  if (buscaDaUrl !== filtros.busca) {
    setBuscaDaUrl(filtros.busca);
    setBusca(filtros.busca);
  }
  // A busca grava na URL só depois de uma pausa na digitação.
  useEffect(() => {
    if (busca === filtros.busca) return;
    const espera = setTimeout(() => {
      aoMudar({ ...filtros, busca });
    }, ESPERA_BUSCA_MS);
    return () => {
      clearTimeout(espera);
    };
  }, [busca, filtros, aoMudar]);

  const etiquetas = etiquetasDosFiltros(filtros, {
    tipoAtivo: (slug) => nomeDoTipo(tipos.data, slug),
    instituicao: (i) => instituicoes.data?.find((x) => x.id === i)?.nome ?? `#${i}`,
  });
  const mudar = <K extends keyof FiltrosHistorico>(campo: K, valor: FiltrosHistorico[K]) => {
    aoMudar({ ...filtros, [campo]: valor });
  };

  return (
    <section aria-label="Filtros" className="rounded-xl border bg-card p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <CampoFiltro id={`${id}-busca`} rotulo="Ativo">
          <Input
            id={`${id}-busca`}
            type="search"
            placeholder="Ticker ou nome…"
            value={busca}
            onChange={(e) => {
              setBusca(e.target.value);
            }}
          />
        </CampoFiltro>
        <CampoFiltro id={`${id}-tipo`} rotulo="Tipo de ativo">
          <Select
            id={`${id}-tipo`}
            value={filtros.tipoAtivo}
            onChange={(e) => {
              mudar("tipoAtivo", e.target.value);
            }}
          >
            <option value="">Todos</option>
            {tipos.data?.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.nome}
              </option>
            ))}
          </Select>
        </CampoFiltro>
        <CampoFiltro id={`${id}-inst`} rotulo="Instituição">
          <Select
            id={`${id}-inst`}
            value={filtros.instituicaoId ?? ""}
            onChange={(e) => {
              mudar("instituicaoId", e.target.value ? Number(e.target.value) : null);
            }}
          >
            <option value="">Todas</option>
            {instituicoes.data?.map((i) => (
              <option key={i.id} value={i.id}>
                {i.nome}
              </option>
            ))}
          </Select>
        </CampoFiltro>
        <CampoFiltro id={`${id}-periodo`} rotulo="Período">
          <Select
            id={`${id}-periodo`}
            value={filtros.periodo}
            onChange={(e) => {
              aoMudar({ ...filtros, periodo: e.target.value as Periodo, inicio: null, fim: null });
            }}
          >
            {PERIODOS.map((p) => (
              <option key={p.valor} value={p.valor}>
                {p.rotulo}
              </option>
            ))}
          </Select>
        </CampoFiltro>
        <CampoFiltro id={`${id}-moeda`} rotulo="Moeda">
          <Select
            id={`${id}-moeda`}
            value={filtros.moeda}
            onChange={(e) => {
              mudar("moeda", e.target.value);
            }}
          >
            <option value="">Todas</option>
            <option value="BRL">BRL</option>
            <option value="USD">USD</option>
          </Select>
        </CampoFiltro>
        <CampoFiltro id={`${id}-situacao`} rotulo="Situação do ativo">
          <Select
            id={`${id}-situacao`}
            value={filtros.situacao}
            onChange={(e) => {
              mudar("situacao", e.target.value as Situacao);
            }}
          >
            <option value="">Todas</option>
            <option value="aberta">Ainda na carteira</option>
            <option value="encerrada">Posição encerrada</option>
          </Select>
        </CampoFiltro>
      </div>

      {filtros.periodo === "personalizado" && (
        <div className="mt-3 flex flex-wrap gap-3">
          <CampoFiltro id={`${id}-inicio`} rotulo="Data inicial">
            <Input
              id={`${id}-inicio`}
              type="date"
              value={filtros.inicio ?? ""}
              max={filtros.fim ?? undefined}
              onChange={(e) => {
                mudar("inicio", e.target.value || null);
              }}
            />
          </CampoFiltro>
          <CampoFiltro id={`${id}-fim`} rotulo="Data final">
            <Input
              id={`${id}-fim`}
              type="date"
              value={filtros.fim ?? ""}
              min={filtros.inicio ?? undefined}
              onChange={(e) => {
                mudar("fim", e.target.value || null);
              }}
            />
          </CampoFiltro>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-muted-foreground" id={`${id}-ops`}>
          Operação:
        </span>
        <div role="group" aria-labelledby={`${id}-ops`} className="flex flex-wrap gap-2">
          {OPERACOES.map((op) => {
            const ligado = filtros.operacoes.includes(op);
            return (
              <button
                key={op}
                type="button"
                aria-pressed={ligado}
                onClick={() => {
                  mudar(
                    "operacoes",
                    ligado
                      ? filtros.operacoes.filter((o) => o !== op)
                      : OPERACOES.filter((o) => o === op || filtros.operacoes.includes(o)),
                  );
                }}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border border-input px-3 py-1 text-xs text-muted-foreground",
                  ligado && cn(CLASSES_OPERACAO[op].selo, "font-semibold text-foreground"),
                )}
              >
                <span
                  aria-hidden
                  className={cn("size-2 rounded-full", CLASSES_OPERACAO[op].ponto)}
                />
                {NOMES_OPERACAO[op]}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Checkbox
            checked={filtros.apenasPrejuizo}
            onChange={(e) => {
              mudar("apenasPrejuizo", e.target.checked);
            }}
          />
          Só vendas com prejuízo
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Checkbox
            checked={filtros.apenasComCustos}
            onChange={(e) => {
              mudar("apenasComCustos", e.target.checked);
            }}
          />
          Só com taxas ou imposto
        </label>
        <span className="flex-1" />
        {contagem && (
          <span className="text-sm text-muted-foreground" aria-live="polite">
            {contagem.filtradas.toLocaleString("pt-BR")} de{" "}
            {plural(contagem.total, "operação", "operações")}
          </span>
        )}
        <Button variant="ghost" size="sm" onClick={aoLimpar} disabled={etiquetas.length === 0}>
          Limpar filtros
        </Button>
      </div>

      {etiquetas.length > 0 && (
        <ul aria-label="Filtros ativos" className="mt-3 flex flex-wrap gap-1.5">
          {etiquetas.map((e) => (
            <li
              key={e.chave}
              className="flex items-center gap-1 rounded-full bg-accent py-0.5 pr-1 pl-2.5 text-xs text-accent-foreground"
            >
              {e.texto}
              <button
                type="button"
                aria-label={`Remover filtro ${e.texto}`}
                className="rounded-full p-0.5 hover:bg-accent-foreground/15"
                onClick={() => {
                  aoMudar(e.remover(filtros));
                }}
              >
                <X aria-hidden className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CampoFiltro({
  id,
  rotulo,
  children,
}: {
  id: string;
  rotulo: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-semibold text-muted-foreground">
        {rotulo}
      </label>
      {children}
    </div>
  );
}
