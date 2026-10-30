import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import {
  indexarPorId,
  nomeDoTipo,
  useAtivos,
  useInstituicoes,
  useTiposAtivo,
} from "@/lib/consultas-comuns";
import { formatarMoeda } from "@/lib/formatacao";
import type { GrupoAtivo, Totais } from "./consultas";

const NOMES_SITUACAO = { aberta: "Na carteira", encerrada: "Encerrada" } as const;

function Situacao({ situacao }: { situacao: "aberta" | "encerrada" }) {
  return (
    <Badge variant={situacao === "aberta" ? "secondary" : "outline"}>
      {NOMES_SITUACAO[situacao]}
    </Badge>
  );
}

function CelulasTotais({ totais }: { totais: Totais }) {
  return (
    <>
      <TableCell className="tabular text-right">{formatarMoeda(totais.total_comprado)}</TableCell>
      <TableCell className="tabular text-right">{formatarMoeda(totais.total_vendido)}</TableCell>
      <TableCell className="text-right">
        <ValorFinanceiro valor={totais.lucro_realizado} seta={false} />
      </TableCell>
      <TableCell className="tabular text-right">
        {formatarMoeda(totais.proventos_liquidos)}
      </TableCell>
      <TableCell className="tabular text-right">{formatarMoeda(totais.impostos_retidos)}</TableCell>
      <TableCell className="tabular text-right">{formatarMoeda(totais.taxas)}</TableCell>
      <TableCell className="tabular text-right">{totais.operacoes}</TableCell>
    </>
  );
}

/**
 * Visão "Por ativo" (decisão do dono): uma linha por ativo com os totais do filtro somando
 * todas as instituições, que se abre nas linhas de cada instituição. Com filtro de
 * instituição, a linha do ativo tem só aquela instituição (e a situação daquela posição).
 */
export function VisaoPorAtivo({ grupos }: { grupos: GrupoAtivo[] }) {
  const ativos = indexarPorId(useAtivos().data);
  const instituicoes = indexarPorId(useInstituicoes().data);
  const tipos = useTiposAtivo().data;
  const [abertos, setAbertos] = useState<ReadonlySet<number>>(new Set());

  const alternar = (id: number) => {
    setAbertos((atual) => {
      const novo = new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  };

  return (
    <Table aria-label="Histórico por ativo">
      <TableHeader>
        <TableRow>
          <TableHead>Ativo</TableHead>
          <TableHead>Situação</TableHead>
          <TableHead className="text-right">Comprado</TableHead>
          <TableHead className="text-right">Vendido</TableHead>
          <TableHead className="text-right">Lucro realizado</TableHead>
          <TableHead className="text-right">Proventos</TableHead>
          <TableHead className="text-right">IR retido</TableHead>
          <TableHead className="text-right">Taxas</TableHead>
          <TableHead className="text-right">Operações</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {grupos.map((grupo) => {
          const ativo = ativos.get(grupo.ativo_id);
          const aberto = abertos.has(grupo.ativo_id);
          const rotulo = ativo?.simbolo ?? ativo?.nome ?? `Ativo ${grupo.ativo_id}`;
          return (
            <Fragment key={grupo.ativo_id}>
              <TableRow>
                <TableCell>
                  <button
                    type="button"
                    aria-expanded={aberto}
                    aria-label={`${aberto ? "Recolher" : "Ver por instituição"}: ${rotulo}`}
                    className="inline-flex items-center gap-1 text-left"
                    onClick={() => {
                      alternar(grupo.ativo_id);
                    }}
                  >
                    {aberto ? (
                      <ChevronDown aria-hidden className="size-4" />
                    ) : (
                      <ChevronRight aria-hidden className="size-4" />
                    )}
                    <span>
                      <span className="font-semibold">{rotulo}</span>
                      {ativo && (
                        <span className="block text-xs text-muted-foreground">
                          {nomeDoTipo(tipos, ativo.tipo)} · {grupo.instituicoes.length}{" "}
                          {grupo.instituicoes.length === 1 ? "instituição" : "instituições"}
                        </span>
                      )}
                    </span>
                  </button>
                </TableCell>
                <TableCell>
                  <Situacao situacao={grupo.situacao} />
                </TableCell>
                <CelulasTotais totais={grupo.totais} />
              </TableRow>
              {aberto &&
                grupo.instituicoes.map((inst) => (
                  <TableRow key={inst.instituicao_id} className="bg-muted/40">
                    <TableCell className="pl-10 text-sm">
                      {instituicoes.get(inst.instituicao_id)?.nome ?? `#${inst.instituicao_id}`}
                    </TableCell>
                    <TableCell>
                      <Situacao situacao={inst.situacao} />
                    </TableCell>
                    <CelulasTotais totais={inst.totais} />
                  </TableRow>
                ))}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}
