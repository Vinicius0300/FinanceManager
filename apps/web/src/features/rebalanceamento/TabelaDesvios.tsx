import { ChevronDown, ChevronRight, Pencil } from "lucide-react";
import { Fragment, useState } from "react";
import { IndicadorDefasado } from "@/components/IndicadorDefasado";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { nomeDoTipo, type TipoAtivo } from "@/lib/consultas-comuns";
import { comparar, paraGrafico } from "@/lib/decimal";
import { formatarMoeda, formatarPercentual } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import { corDaClasse, formatarPp } from "./apresentacao";
import type { ClassePlano } from "./consultas";

/**
 * Tabela de desvios: % atual × meta por classe, com uma barra que mostra a faixa da banda
 * (meta ± tolerância), o traço da meta e a posição atual. A classe com pesos se expande
 * para os ativos dela (`aria-expanded`). O lápis no cabeçalho da coluna Meta abre a edição
 * das metas (`aoEditar`).
 */
export function TabelaDesvios({
  classes,
  tolerancia,
  tipos,
  aoEditar,
}: {
  classes: readonly ClassePlano[];
  tolerancia: number;
  tipos: readonly TipoAtivo[] | undefined;
  aoEditar?: () => void;
}) {
  const [abertas, setAbertas] = useState<ReadonlySet<string>>(new Set());
  const alternar = (tipo: string) => {
    setAbertas((atuais) => {
      const novas = new Set(atuais);
      if (novas.has(tipo)) novas.delete(tipo);
      else novas.add(tipo);
      return novas;
    });
  };
  // Escala comum das barras: o maior entre % atual e meta + tolerância (mínimo 10%).
  const escala = Math.max(
    10,
    ...classes.map((c) =>
      Math.max(paraGrafico(c.percentual_atual), paraGrafico(c.meta) + tolerancia),
    ),
  );
  return (
    <Table aria-label="Desvio de cada classe em relação à meta">
      <TableHeader>
        <TableRow>
          <TableHead>Classe</TableHead>
          <TableHead className="text-right">Valor atual</TableHead>
          <TableHead className="text-right">Atual</TableHead>
          <TableHead className="text-right">
            <span className="inline-flex items-center justify-end gap-1">
              Meta
              {aoEditar && (
                <button
                  type="button"
                  aria-label="Editar metas"
                  title="Editar metas"
                  onClick={aoEditar}
                  className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <Pencil aria-hidden className="size-3.5" />
                </button>
              )}
            </span>
          </TableHead>
          <TableHead className="text-right">Desvio</TableHead>
          <TableHead className="w-[32%] min-w-40">Atual × meta</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {classes.map((classe) => {
          const nome = nomeDoTipo(tipos, classe.tipo_ativo);
          const aberta = abertas.has(classe.tipo_ativo);
          return (
            <Fragment key={classe.tipo_ativo}>
              <TableRow>
                <TableCell>
                  {classe.usa_pesos ? (
                    <button
                      type="button"
                      aria-expanded={aberta}
                      onClick={() => {
                        alternar(classe.tipo_ativo);
                      }}
                      className="inline-flex items-center gap-1 rounded-sm font-semibold hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      {aberta ? (
                        <ChevronDown aria-hidden className="size-3.5" />
                      ) : (
                        <ChevronRight aria-hidden className="size-3.5" />
                      )}
                      {nome}
                    </button>
                  ) : (
                    <span className="font-semibold">{nome}</span>
                  )}
                </TableCell>
                <TableCell className="tabular text-right">
                  {formatarMoeda(classe.valor_atual)}
                </TableCell>
                <TableCell className="tabular text-right">
                  {formatarPercentual(classe.percentual_atual)}
                </TableCell>
                <TableCell className="tabular text-right">
                  {formatarPercentual(classe.meta)}
                </TableCell>
                <TableCell className="text-right">
                  <span
                    className={cn(
                      "tabular whitespace-nowrap",
                      classe.fora_da_banda
                        ? "font-semibold text-aviso-texto"
                        : "text-muted-foreground",
                    )}
                  >
                    {formatarPp(classe.desvio_pp)}
                  </span>
                  {classe.fora_da_banda && (
                    <Badge variant="aviso" className="ml-1.5">
                      fora da banda
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  <BarraDesvio
                    classe={classe}
                    tolerancia={tolerancia}
                    escala={escala}
                    nome={nome}
                  />
                </TableCell>
              </TableRow>
              {aberta &&
                classe.ativos.map((ativo) => (
                  <TableRow key={`${classe.tipo_ativo}-${ativo.ativo_id}`} className="bg-muted/40">
                    <TableCell className="pl-8">
                      <span className="font-medium">{ativo.simbolo ?? ativo.nome}</span>{" "}
                      <IndicadorDefasado defasado={ativo.defasado} aviso={ativo.aviso} />
                    </TableCell>
                    <TableCell className="tabular text-right">
                      {formatarMoeda(ativo.valor_atual)}
                    </TableCell>
                    <TableCell />
                    <TableCell className="tabular text-right text-muted-foreground">
                      {ativo.peso === null ? "—" : `${formatarPercentual(ativo.peso)} da classe`}
                    </TableCell>
                    <TableCell />
                    <TableCell />
                  </TableRow>
                ))}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}

/** Barra horizontal: faixa da banda, traço da meta e a posição atual (cor da classe). */
function BarraDesvio({
  classe,
  tolerancia,
  escala,
  nome,
}: {
  classe: ClassePlano;
  tolerancia: number;
  escala: number;
  nome: string;
}) {
  // `paraGrafico` só para posicionar o desenho; os textos usam os decimais da API.
  const pos = (valor: number) => `${Math.min(100, Math.max(0, (valor / escala) * 100))}%`;
  const atual = paraGrafico(classe.percentual_atual);
  const meta = classe.meta === null ? null : paraGrafico(classe.meta);
  const acima = classe.meta !== null && comparar(classe.percentual_atual, classe.meta) > 0;
  return (
    <div
      role="img"
      aria-label={
        meta === null
          ? `${nome}: ${formatarPercentual(classe.percentual_atual)} da carteira`
          : `${nome}: ${formatarPercentual(classe.percentual_atual)} atual, meta ${formatarPercentual(classe.meta)}, banda de ${tolerancia} p.p.`
      }
      className="relative h-3 w-full rounded-full bg-muted"
    >
      {meta !== null && (
        <div
          data-testid="faixa-banda"
          className="absolute inset-y-0 rounded-full bg-foreground/10"
          style={{ left: pos(meta - tolerancia), right: `calc(100% - ${pos(meta + tolerancia)})` }}
        />
      )}
      <div
        className={cn("absolute inset-y-0.5 left-0 rounded-full", acima && "opacity-90")}
        style={{ width: pos(atual), background: corDaClasse(classe.tipo_ativo) }}
      />
      {meta !== null && (
        <div
          className="absolute -inset-y-0.5 w-0.5 rounded-full bg-foreground"
          style={{ left: pos(meta) }}
        />
      )}
    </div>
  );
}
