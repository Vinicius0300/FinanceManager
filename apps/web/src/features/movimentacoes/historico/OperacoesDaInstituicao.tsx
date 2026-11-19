import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatarData, formatarMoeda, formatarPreco, formatarQuantidade } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import {
  ITENS_PAINEL,
  useOperacoesDaInstituicao,
  usePosicoesDaInstituicao,
  useUltimaOperacao,
  type Operacao,
} from "./consultas";
import { totalDePaginas, type ConsultaHistorico } from "./filtros";
import { SeloOperacao } from "./SeloOperacao";
import { CelulasValores } from "./TabelaHistorico";

const COLUNAS = [
  { titulo: "Data" },
  { titulo: "Operação" },
  { titulo: "Qtd.", numerica: true },
  { titulo: "Preço unit.", numerica: true },
  { titulo: "Taxas", numerica: true },
  { titulo: "Imposto", numerica: true },
  { titulo: "Valor total", numerica: true },
  { titulo: "Resultado", numerica: true },
] as const;

/**
 * Painel aberto na linha de uma instituição da visão Por ativo (Parte 9): posição de hoje
 * naquela instituição, primeira e última operação e a lista das operações do ativo ali,
 * com os filtros do topo, da mais antiga para a mais recente. Só consulta quando aberto.
 */
export function OperacoesDaInstituicao({
  ativoId,
  instituicaoId,
  rotulo,
  consulta,
  aoAbrir,
  aoVerEmOperacoes,
}: {
  ativoId: number;
  instituicaoId: number;
  rotulo: string; // "PETR4 em XP"
  consulta: ConsultaHistorico;
  aoAbrir: (operacao: Operacao) => void;
  aoVerEmOperacoes: () => void;
}) {
  const [pagina, setPagina] = useState(1);
  // A 1ª página traz a 1ª operação; quando a página aberta é a 1ª, é a mesma consulta.
  const primeiraPagina = useOperacoesDaInstituicao(consulta, ativoId, instituicaoId, 1);
  const lista = useOperacoesDaInstituicao(consulta, ativoId, instituicaoId, pagina);
  const total = primeiraPagina.data?.total ?? 0;
  const varias = total > ITENS_PAINEL;
  const ultimaConsulta = useUltimaOperacao(consulta, ativoId, instituicaoId, varias);

  const primeira = primeiraPagina.data?.itens[0]?.data;
  const ultima = varias
    ? ultimaConsulta.data?.itens[0]?.data
    : primeiraPagina.data?.itens.at(-1)?.data;
  const paginas = totalDePaginas(total, ITENS_PAINEL);

  return (
    <section
      aria-label={`Operações de ${rotulo}`}
      className="flex flex-col gap-3 border-l-2 border-primary py-3 pr-3 pl-6 sm:pl-10"
    >
      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        <PosicaoDeHoje ativoId={ativoId} instituicaoId={instituicaoId} />
        <Metrica titulo="Primeira operação">{primeira ? formatarData(primeira) : "—"}</Metrica>
        <Metrica titulo="Última operação">{ultima ? formatarData(ultima) : "—"}</Metrica>
      </dl>

      {lista.isPending ? (
        <Carregando texto="Carregando operações…" className="py-4" />
      ) : lista.isError ? (
        <EstadoErro
          erro={lista.error}
          aoTentarNovamente={() => {
            void lista.refetch();
          }}
        />
      ) : lista.data.total === 0 ? (
        <EstadoVazio titulo="Nenhuma operação com esses filtros" className="py-4" />
      ) : (
        <div
          className={cn(
            "overflow-x-auto rounded-lg border bg-card",
            lista.isPlaceholderData && "opacity-60 transition-opacity",
          )}
        >
          <Table aria-label={`Operações de ${rotulo}`}>
            <TableHeader>
              <TableRow>
                {COLUNAS.map((c) => (
                  <TableHead key={c.titulo} className={cn("numerica" in c && "text-right")}>
                    {c.titulo}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {lista.data.itens.map((op) => (
                <TableRow
                  key={op.id}
                  data-clicavel
                  tabIndex={0}
                  onClick={() => {
                    aoAbrir(op);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") aoAbrir(op);
                  }}
                >
                  <TableCell className="tabular whitespace-nowrap">
                    {formatarData(op.data)}
                  </TableCell>
                  <TableCell>
                    <SeloOperacao tipo={op.tipo} />
                  </TableCell>
                  <CelulasValores operacao={op} />
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        {paginas > 1 ? (
          <nav
            aria-label={`Páginas das operações de ${rotulo}`}
            className="flex items-center gap-2 text-muted-foreground"
          >
            <Button
              variant="outline"
              size="sm"
              disabled={pagina <= 1}
              onClick={() => {
                setPagina(pagina - 1);
              }}
            >
              <ChevronLeft aria-hidden />
              Anterior
            </Button>
            <span className="tabular">
              Página {pagina} de {paginas}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={pagina >= paginas}
              onClick={() => {
                setPagina(pagina + 1);
              }}
            >
              Próxima
              <ChevronRight aria-hidden />
            </Button>
          </nav>
        ) : (
          <span />
        )}
        <Button variant="link" size="sm" className="px-0" onClick={aoVerEmOperacoes}>
          Ver em Operações com este filtro
          <ArrowRight aria-hidden />
        </Button>
      </div>
    </section>
  );
}

/**
 * Posição de hoje do ativo na instituição, sem os filtros do topo. Ativo que não está na
 * lista de posições abertas = posição encerrada. Renda fixa por aporte não tem quantidade
 * nem preço médio: mostra só o custo.
 */
function PosicaoDeHoje({ ativoId, instituicaoId }: { ativoId: number; instituicaoId: number }) {
  const posicoes = usePosicoesDaInstituicao(instituicaoId);
  if (posicoes.isPending) {
    return <Metrica titulo="Posição de hoje">Carregando…</Metrica>;
  }
  if (posicoes.isError) {
    return <Metrica titulo="Posição de hoje">Não foi possível carregar a posição.</Metrica>;
  }
  const posicao = posicoes.data.find((p) => p.ativo_id === ativoId);
  if (!posicao) {
    return <Metrica titulo="Posição de hoje">Posição encerrada</Metrica>;
  }
  return (
    <>
      {posicao.quantidade !== null && (
        <>
          <Metrica titulo="Quantidade atual">{formatarQuantidade(posicao.quantidade)}</Metrica>
          <Metrica titulo="Preço médio">
            {formatarPreco(posicao.preco_medio, posicao.moeda)}
          </Metrica>
        </>
      )}
      <Metrica titulo="Custo da posição">
        {posicao.metricas ? formatarMoeda(posicao.metricas.custo, posicao.moeda) : "—"}
      </Metrica>
    </>
  );
}

function Metrica({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {titulo}
      </dt>
      <dd className="tabular font-semibold">{children}</dd>
    </div>
  );
}
