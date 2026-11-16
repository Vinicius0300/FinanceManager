import { ChevronLeft, ChevronRight, Pencil, Plus, Tags, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { CartaoMetrica } from "@/components/CartaoMetrica";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { opcoesRosca } from "@/components/graficos/estiloGrafico";
import { GraficoECharts } from "@/components/graficos/GraficoECharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { paraGrafico } from "@/lib/decimal";
import { prepararFatias } from "@/lib/fatias";
import { formatarData, formatarMesAno, formatarMoeda, formatarRazao } from "@/lib/formatacao";
import { useInstituicoes } from "@/lib/consultas-comuns";
import { useCoresTema } from "@/theme/cores";
import {
  limitesDoMes,
  somarMes,
  useCategorias,
  useExcluirLancamento,
  useLancamentos,
  useResumoDoMes,
  useResumoPorInstituicao,
  type Lancamento,
  type Mes,
  type ResumoMensalFiltrado,
  type TagLancamento,
} from "./consultas";
import { DialogoCategorias } from "./DialogoCategorias";
import { DialogoLancamento } from "./DialogoLancamento";
import { useValoresOcultos } from "@/lib/valores-ocultos";

/**
 * Receitas e despesas do mês: resumo, gráfico por categoria, resumo por instituição,
 * lançamentos (com as transferências em BRL, só leitura) e categorias. O filtro por
 * instituição muda os cartões, a rosca e a tabela.
 */
export function TelaReceitasDespesas({ agora = new Date() }: { agora?: Date }) {
  // Redesenha ao alternar o modo privacidade (os formatadores leem o store).
  useValoresOcultos();
  const [mes, setMes] = useState<Mes>({ ano: agora.getFullYear(), mes: agora.getMonth() + 1 });
  const instituicoes = useInstituicoes();
  const [filtro, setFiltro] = useState<number | null>(null);
  // Ignora uma instituição que tenha sido excluída.
  const instituicaoId =
    filtro !== null && instituicoes.data?.some((i) => i.id === filtro) ? filtro : null;
  const resumo = useResumoDoMes(mes, instituicaoId);
  const [editando, setEditando] = useState<Lancamento | "novo" | null>(null);
  const [categorias, setCategorias] = useState(false);
  const iso = `${mes.ano}-${String(mes.mes).padStart(2, "0")}`;
  const { inicio, fim } = limitesDoMes(mes);
  const hoje = `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}`;
  // Novo lançamento: hoje no mês atual; senão, o 1º dia do mês escolhido.
  const dataPadrao = iso === hoje ? `${iso}-${String(agora.getDate()).padStart(2, "0")}` : inicio;

  return (
    <div className="flex flex-col gap-3.5">
      <CabecalhoPagina
        titulo="Receitas e Despesas"
        acoes={
          <>
            <div className="flex items-center gap-1" role="group" aria-label="Mês">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Mês anterior"
                onClick={() => {
                  setMes(somarMes(mes, -1));
                }}
              >
                <ChevronLeft aria-hidden />
              </Button>
              <Input
                type="month"
                aria-label="Mês exibido"
                className="w-44"
                value={iso}
                onChange={(e) => {
                  const [a, m] = e.target.value.split("-").map(Number);
                  if (a && m) setMes({ ano: a, mes: m });
                }}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Próximo mês"
                onClick={() => {
                  setMes(somarMes(mes, 1));
                }}
              >
                <ChevronRight aria-hidden />
              </Button>
            </div>
            <Select
              aria-label="Instituição"
              className="w-52"
              value={instituicaoId === null ? "" : String(instituicaoId)}
              onChange={(e) => {
                setFiltro(e.target.value ? Number(e.target.value) : null);
              }}
            >
              <option value="">Todas as instituições</option>
              {(instituicoes.data ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.nome}
                </option>
              ))}
            </Select>
            <Button
              variant="outline"
              onClick={() => {
                setCategorias(true);
              }}
            >
              <Tags aria-hidden />
              Categorias
            </Button>
            <Button
              onClick={() => {
                setEditando("novo");
              }}
            >
              <Plus aria-hidden />
              Novo lançamento
            </Button>
          </>
        }
      />
      <p className="text-sm text-muted-foreground">
        Lance primeiro as receitas do mês e depois as despesas: o caixa da instituição nunca fica
        negativo, e uma despesa sem saldo pede um ajuste. Transferências entre bancos aparecem na
        tabela, mas não entram nos totais.
      </p>
      {resumo.isError ? (
        <EstadoErro
          erro={resumo.error}
          aoTentarNovamente={() => {
            void resumo.refetch();
          }}
        />
      ) : (
        <div className="grid gap-3.5 sm:grid-cols-3">
          <CartaoMetrica
            titulo="Recebido"
            carregando={resumo.isPending}
            valor={formatarMoeda(resumo.data?.total_receitas)}
            apoio={formatarMesAno(`${iso}-01`)}
          />
          <CartaoMetrica
            titulo="Gasto"
            carregando={resumo.isPending}
            valor={formatarMoeda(resumo.data?.total_despesas)}
          />
          <CartaoMetrica
            titulo="Saldo do mês"
            carregando={resumo.isPending}
            valor={<ValorFinanceiro valor={resumo.data?.saldo} />}
          />
        </div>
      )}
      <div className="grid gap-3.5 xl:grid-cols-5">
        <Secao titulo="Despesas por categoria" className="xl:col-span-2">
          {resumo.isPending ? (
            <Carregando />
          ) : resumo.data ? (
            <GraficoCategorias resumo={resumo.data} />
          ) : null}
        </Secao>
        <Secao
          titulo={`Lançamentos de ${formatarData(inicio)} a ${formatarData(fim)}`}
          className="xl:col-span-3"
        >
          <ListaLancamentos mes={mes} instituicaoId={instituicaoId} aoEditar={setEditando} />
        </Secao>
      </div>
      <Secao titulo="Resumo por instituição">
        <ResumoPorInstituicao mes={mes} />
      </Secao>
      {editando && (
        <DialogoLancamento
          lancamento={editando === "novo" ? undefined : editando}
          dataPadrao={dataPadrao}
          instituicaoPadrao={instituicaoId}
          aoFechar={() => {
            setEditando(null);
          }}
        />
      )}
      {categorias && (
        <DialogoCategorias
          aoFechar={() => {
            setCategorias(false);
          }}
        />
      )}
    </div>
  );
}

/** Rosca das despesas do mês; cores pela regra das 6 cores (ordem de criação das categorias). */
function GraficoCategorias({ resumo }: { resumo: ResumoMensalFiltrado }) {
  const ocultos = useValoresOcultos();
  const cores = useCoresTema();
  const categorias = useCategorias();
  const opcoes = useMemo(() => {
    const despesas = resumo.por_categoria.filter((c) => c.tipo === "despesa");
    const ordem = (categorias.data ?? [])
      .filter((c) => c.tipo === "despesa")
      .sort((a, b) => a.id - b.id)
      .map((c) => String(c.id));
    const prontas = prepararFatias(
      despesas.map((c) => ({
        categoria: c.categoria_id === null ? "sem-categoria" : String(c.categoria_id),
        rotulo: c.categoria_nome,
        valor: c.total,
        percentual: c.percentual,
      })),
      ordem,
      cores,
    );
    return opcoesRosca(
      prontas.map((f) => ({
        rotulo: f.rotulo,
        valor: paraGrafico(f.valor),
        cor: f.cor,
        texto: `${formatarMoeda(f.valor, "BRL", { ocultar: ocultos })} (${formatarRazao(f.percentual ?? null)})`,
      })),
      cores,
    );
  }, [resumo, categorias.data, cores, ocultos]);
  if (!resumo.por_categoria.some((c) => c.tipo === "despesa")) {
    return <EstadoVazio titulo="Nenhuma despesa neste mês" />;
  }
  return <GraficoECharts opcoes={opcoes} rotulo="Despesas do mês por categoria" />;
}

const ROTULO_TAG: Partial<Record<TagLancamento, string>> = {
  transferencia_saida: "Transferência",
  transferencia_entrada: "Transferência",
  tarifa: "Tarifa",
};

function ListaLancamentos({
  mes,
  instituicaoId,
  aoEditar,
}: {
  mes: Mes;
  instituicaoId: number | null;
  aoEditar: (lancamento: Lancamento) => void;
}) {
  const lancamentos = useLancamentos(mes, instituicaoId);
  const excluir = useExcluirLancamento();
  const [excluindo, setExcluindo] = useState<Lancamento | null>(null);
  if (lancamentos.isPending) return <Carregando />;
  if (lancamentos.isError) {
    return (
      <EstadoErro
        erro={lancamentos.error}
        aoTentarNovamente={() => {
          void lancamentos.refetch();
        }}
      />
    );
  }
  if (lancamentos.data.itens.length === 0) {
    return <EstadoVazio titulo="Nenhum lançamento neste mês" descricao='Use "Novo lançamento".' />;
  }
  return (
    <>
      <Table aria-label="Lançamentos do mês">
        <TableHeader>
          <TableRow>
            <TableHead>Data</TableHead>
            <TableHead>Descrição</TableHead>
            <TableHead>Instituição</TableHead>
            <TableHead>Categoria</TableHead>
            <TableHead className="text-right">Valor</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {lancamentos.data.itens.map((l) => {
            const tag = ROTULO_TAG[l.tag];
            const transferencia = l.tag !== "lancamento" && l.tag !== "tarifa";
            return (
              <TableRow key={l.chave}>
                <TableCell className="tabular">{formatarData(l.data)}</TableCell>
                <TableCell>
                  {l.descricao}
                  {tag && (
                    <Badge variant="outline" className="ml-2">
                      {tag}
                    </Badge>
                  )}
                  {l.observacao && (
                    <span className="block text-xs text-muted-foreground">{l.observacao}</span>
                  )}
                </TableCell>
                <TableCell>{l.instituicao_nome}</TableCell>
                <TableCell>
                  {!transferencia && (
                    <Badge variant="secondary">{l.categoria_nome ?? "Sem categoria"}</Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <ValorFinanceiro
                    valor={l.tipo === "despesa" ? `-${l.valor}` : l.valor}
                    seta={false}
                  />
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {l.editavel && l.lancamento_id !== null ? (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Editar ${l.descricao}`}
                        onClick={() => {
                          aoEditar(l);
                        }}
                      >
                        <Pencil aria-hidden />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Excluir ${l.descricao}`}
                        onClick={() => {
                          excluir.reset();
                          setExcluindo(l);
                        }}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      Edite em Movimentações → Caixa
                    </span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <DialogoConfirmacao
        aberto={excluindo !== null}
        aoMudar={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo={`Excluir "${excluindo?.descricao ?? ""}"?`}
        descricao="O lançamento sai do mês, do resumo e do caixa da instituição (com o ajuste de saldo ligado a ele, se houver). A exclusão é recusada se o caixa ficar negativo."
        ocupado={excluir.isPending}
        erro={excluir.error}
        aoConfirmar={() => {
          const id = excluindo?.lancamento_id;
          if (id === undefined || id === null) return;
          excluir.mutate(id, {
            onSuccess: () => {
              setExcluindo(null);
            },
          });
        }}
      />
    </>
  );
}

/** Receitas, despesas, transferências que entraram e saíram e saldo do mês (só BRL). */
function ResumoPorInstituicao({ mes }: { mes: Mes }) {
  const resumo = useResumoPorInstituicao(mes);
  if (resumo.isPending) return <Carregando />;
  if (resumo.isError) {
    return (
      <EstadoErro
        erro={resumo.error}
        aoTentarNovamente={() => {
          void resumo.refetch();
        }}
      />
    );
  }
  if (resumo.data.length === 0) {
    return <EstadoVazio titulo="Nenhuma receita, despesa ou transferência neste mês" />;
  }
  return (
    <Table aria-label="Resumo por instituição">
      <TableHeader>
        <TableRow>
          <TableHead>Instituição</TableHead>
          <TableHead className="text-right">Receitas</TableHead>
          <TableHead className="text-right">Despesas</TableHead>
          <TableHead className="text-right">Entrou</TableHead>
          <TableHead className="text-right">Saiu</TableHead>
          <TableHead className="text-right">Saldo do mês</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {resumo.data.map((r) => (
          <TableRow key={r.instituicao_id}>
            <TableCell>{r.instituicao_nome}</TableCell>
            <TableCell className="tabular text-right">{formatarMoeda(r.receitas)}</TableCell>
            <TableCell className="tabular text-right">{formatarMoeda(r.despesas)}</TableCell>
            <TableCell className="tabular text-right">{formatarMoeda(r.entrou)}</TableCell>
            <TableCell className="tabular text-right">{formatarMoeda(r.saiu)}</TableCell>
            <TableCell className="text-right">
              <ValorFinanceiro valor={r.saldo} seta={false} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
