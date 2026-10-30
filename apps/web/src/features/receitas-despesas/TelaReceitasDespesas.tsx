import { ChevronLeft, ChevronRight, Pencil, Plus, Tags, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { CartaoMetrica } from "@/components/CartaoMetrica";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { GraficoECharts } from "@/components/graficos/GraficoECharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { useResumoMensal, type ResumoMensal } from "@/features/dashboard/consultas";
import { paraGrafico } from "@/lib/decimal";
import { prepararFatias } from "@/lib/fatias";
import { formatarData, formatarMesAno, formatarMoeda, formatarRazao } from "@/lib/formatacao";
import { useCoresTema } from "@/theme/cores";
import {
  limitesDoMes,
  somarMes,
  useCategorias,
  useExcluirLancamento,
  useLancamentos,
  type Lancamento,
  type Mes,
} from "./consultas";
import { DialogoCategorias } from "./DialogoCategorias";
import { DialogoLancamento } from "./DialogoLancamento";

/** Receitas e despesas do mês: resumo, gráfico por categoria, lançamentos e categorias. */
export function TelaReceitasDespesas({ agora = new Date() }: { agora?: Date }) {
  const [mes, setMes] = useState<Mes>({ ano: agora.getFullYear(), mes: agora.getMonth() + 1 });
  const resumo = useResumoMensal(mes.ano, mes.mes);
  const [editando, setEditando] = useState<Lancamento | "novo" | null>(null);
  const [categorias, setCategorias] = useState(false);
  const iso = `${mes.ano}-${String(mes.mes).padStart(2, "0")}`;
  const { inicio, fim } = limitesDoMes(mes);
  const hoje = `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}`;
  // Novo lançamento: hoje no mês atual; senão, o 1º dia do mês escolhido.
  const dataPadrao = iso === hoje ? `${iso}-${String(agora.getDate()).padStart(2, "0")}` : inicio;

  return (
    <div className="flex flex-col gap-4">
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
                className="w-40"
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
      {resumo.isError ? (
        <EstadoErro
          erro={resumo.error}
          aoTentarNovamente={() => {
            void resumo.refetch();
          }}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
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
      <div className="grid gap-4 xl:grid-cols-5">
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
          <ListaLancamentos mes={mes} aoEditar={setEditando} />
        </Secao>
      </div>
      {editando && (
        <DialogoLancamento
          lancamento={editando === "novo" ? undefined : editando}
          dataPadrao={dataPadrao}
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

/** Pizza das despesas do mês; cores fixas pela ordem de criação das categorias. */
function GraficoCategorias({ resumo }: { resumo: ResumoMensal }) {
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
    const textos = new Map(
      prontas.map((f) => [f.rotulo, `${formatarMoeda(f.valor)} (${formatarRazao(f.percentual)})`]),
    );
    return {
      tooltip: {
        trigger: "item",
        backgroundColor: cores.cartao,
        borderColor: cores.borda,
        textStyle: { color: cores.texto },
        formatter: (p: { name: string }) => `${p.name}: ${textos.get(p.name) ?? ""}`,
      },
      legend: {
        orient: "vertical",
        right: 0,
        top: "middle",
        textStyle: { color: cores.texto },
        formatter: (nome: string) => `${nome}  ${textos.get(nome) ?? ""}`,
      },
      series: [
        {
          type: "pie",
          radius: ["45%", "72%"],
          center: ["28%", "50%"],
          label: { show: false },
          itemStyle: { borderColor: cores.fundo, borderWidth: 2 },
          data: prontas.map((f) => ({
            name: f.rotulo,
            value: paraGrafico(f.valor),
            itemStyle: { color: f.cor },
          })),
        },
      ],
    };
  }, [resumo, categorias.data, cores]);
  if (!resumo.por_categoria.some((c) => c.tipo === "despesa")) {
    return <EstadoVazio titulo="Nenhuma despesa neste mês" />;
  }
  return <GraficoECharts opcoes={opcoes} rotulo="Despesas do mês por categoria" />;
}

function ListaLancamentos({
  mes,
  aoEditar,
}: {
  mes: Mes;
  aoEditar: (lancamento: Lancamento) => void;
}) {
  const lancamentos = useLancamentos(mes);
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
            <TableHead>Categoria</TableHead>
            <TableHead className="text-right">Valor</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {lancamentos.data.itens.map((l) => (
            <TableRow key={l.id}>
              <TableCell className="tabular">{formatarData(l.data)}</TableCell>
              <TableCell>
                {l.descricao}
                {l.observacao && (
                  <span className="block text-xs text-muted-foreground">{l.observacao}</span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant="secondary">{l.categoria_nome ?? "Sem categoria"}</Badge>
              </TableCell>
              <TableCell className="text-right">
                <ValorFinanceiro
                  valor={l.tipo === "despesa" ? `-${l.valor}` : l.valor}
                  seta={false}
                />
              </TableCell>
              <TableCell className="text-right whitespace-nowrap">
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
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <DialogoConfirmacao
        aberto={excluindo !== null}
        aoMudar={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo={`Excluir "${excluindo?.descricao ?? ""}"?`}
        descricao="O lançamento sai do mês e do resumo."
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
    </>
  );
}
