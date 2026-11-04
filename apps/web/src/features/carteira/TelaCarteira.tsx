import { createColumnHelper } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { Carregando, EstadoErro, EstadoVazio, MensagemErro } from "@/components/Estados";
import { IndicadorDefasado } from "@/components/IndicadorDefasado";
import { Segmentos } from "@/components/Segmentos";
import { SeletorAnalise } from "@/components/SeletorAnalise";
import { useInstituicaoAnalise } from "@/lib/consultas-comuns";
import { TabelaDados } from "@/components/TabelaDados";
import { ordenarDecimal } from "@/lib/ordenacao";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { useAlocacao, usePosicoes, type Posicao } from "@/features/dashboard/consultas";
import { GraficoAlocacao } from "@/features/dashboard/graficos";
import { nomeDoTipo, useAtivos, useTiposAtivo, type Ativo } from "@/lib/consultas-comuns";
import {
  formatarData,
  formatarDataHora,
  formatarMoeda,
  formatarNumero,
  formatarPreco,
} from "@/lib/formatacao";
import { useStatusCotacoes, type StatusAtivo } from "./consultas";
import { DetalheAtivo } from "./DetalheAtivo";
import { CarteiraPorInstituicao } from "./PorInstituicao";
import { NOMES_ORIGEM } from "./rotulos";
import { DialogoTransacao } from "@/features/movimentacoes/transacao/DialogoTransacao";

/**
 * Posições com filtros e status da cotação de cada ativo. O ativo é cadastrado na própria
 * movimentação ("Nova movimentação"); aqui ele pode ser editado pelo detalhe.
 */
export function TelaCarteira() {
  const instituicaoId = useInstituicaoAnalise();
  const [novo, setNovo] = useState(false);
  const [detalhe, setDetalhe] = useState<number | null>(null);
  const ativos = useAtivos();
  const status = useStatusCotacoes();
  const statusPorAtivo = useMemo(
    () => new Map((status.data ?? []).map((s) => [s.ativo_id, s])),
    [status.data],
  );
  const ativoDetalhe = ativos.data?.find((a) => a.id === detalhe);

  return (
    <div className="flex flex-col gap-3.5">
      <CabecalhoPagina
        titulo="Carteira"
        acoes={
          <>
            <SeletorAnalise />
            <Button
              onClick={() => {
                setNovo(true);
              }}
            >
              <Plus aria-hidden />
              Nova movimentação
            </Button>
          </>
        }
      />
      <Posicoes
        instituicaoId={instituicaoId}
        statusPorAtivo={statusPorAtivo}
        aoAbrir={setDetalhe}
      />
      <div className="grid gap-3.5 xl:grid-cols-5">
        <Secao titulo="Alocação" className="xl:col-span-2">
          <AlocacaoCarteira instituicaoId={instituicaoId} />
        </Secao>
        <Secao titulo="Ativos cadastrados" className="xl:col-span-3">
          <AtivosCadastrados statusPorAtivo={statusPorAtivo} aoAbrir={setDetalhe} />
        </Secao>
      </div>
      {novo && <DialogoTransacao aberto={novo} aoMudar={setNovo} />}
      {ativoDetalhe && (
        <DetalheAtivo
          ativo={ativoDetalhe}
          status={statusPorAtivo.get(ativoDetalhe.id)}
          aoFechar={() => {
            setDetalhe(null);
          }}
        />
      )}
    </div>
  );
}

function Atualizacao({ status }: { status: StatusAtivo | undefined }) {
  if (!status) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="flex flex-col text-xs">
      <span>
        {status.data_hora ? formatarDataHora(status.data_hora) : formatarData(status.data)}
      </span>
      <span className="text-muted-foreground">
        {status.origem ? (NOMES_ORIGEM[status.origem] ?? status.origem) : "sem preço"}
        {status.provider_preco && ` · ${status.provider_preco}`}
      </span>
      {status.ultimo_erro && (
        <span className="text-negativo" title={status.ultimo_erro}>
          Erro: {status.ultimo_erro}
        </span>
      )}
    </span>
  );
}

const coluna = createColumnHelper<Posicao>();

type VisaoPosicoes = "lista" | "instituicao";
const VISOES = [
  { valor: "lista", rotulo: "Lista" },
  { valor: "instituicao", rotulo: "Por instituição" },
] as const;

function Posicoes({
  instituicaoId,
  statusPorAtivo,
  aoAbrir,
}: {
  instituicaoId: number | null;
  statusPorAtivo: Map<number, StatusAtivo>;
  aoAbrir: (ativoId: number) => void;
}) {
  const posicoes = usePosicoes(instituicaoId);
  const tipos = useTiposAtivo();
  const [visao, setVisao] = useState<VisaoPosicoes>("lista");
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState("");

  const colunas = useMemo(
    () => [
      coluna.accessor((p) => p.simbolo ?? p.nome, {
        id: "ativo",
        header: "Ativo",
        cell: ({ row }) => (
          <span className="flex flex-col">
            <span className="flex flex-wrap items-center gap-1 font-medium">
              {row.original.simbolo ?? row.original.nome}
              <IndicadorDefasado
                defasado={row.original.defasado}
                aviso={row.original.aviso}
                erro={row.original.erro}
              />
            </span>
            {row.original.simbolo && (
              <span className="text-xs text-muted-foreground">{row.original.nome}</span>
            )}
          </span>
        ),
      }),
      coluna.accessor("tipo", {
        header: "Tipo",
        cell: ({ getValue }) => nomeDoTipo(tipos.data, getValue()),
      }),
      coluna.accessor("quantidade", {
        header: "Qtd.",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue }) => formatarNumero(getValue()),
      }),
      coluna.accessor("preco_medio", {
        header: "Preço médio",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue, row }) => formatarPreco(getValue(), row.original.moeda),
      }),
      coluna.accessor("preco_atual", {
        header: "Preço atual",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue, row }) => formatarPreco(getValue(), row.original.moeda),
      }),
      coluna.accessor("valor_brl", {
        header: "Valor (BRL)",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue }) => formatarMoeda(getValue()),
      }),
      coluna.accessor((p) => p.variacao_dia?.variacao ?? null, {
        id: "variacao",
        header: "Dia",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue }) => <ValorFinanceiro valor={getValue()} percentual />,
      }),
      coluna.accessor((p) => p.metricas_brl?.rentabilidade_total ?? null, {
        id: "rentabilidade",
        header: "Rentabilidade",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue }) => <ValorFinanceiro valor={getValue()} percentual />,
      }),
      coluna.display({
        id: "atualizacao",
        header: "Atualização",
        cell: ({ row }) => <Atualizacao status={statusPorAtivo.get(row.original.ativo_id)} />,
      }),
    ],
    [tipos.data, statusPorAtivo],
  );

  const filtradas = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase("pt-BR");
    return (posicoes.data ?? []).filter(
      (p) =>
        (!tipo || p.tipo === tipo) &&
        (!termo ||
          p.nome.toLocaleLowerCase("pt-BR").includes(termo) ||
          (p.simbolo ?? "").toLocaleLowerCase("pt-BR").includes(termo)),
    );
  }, [posicoes.data, busca, tipo]);

  return (
    <Secao
      titulo="Posições"
      acoes={
        <div className="flex flex-wrap items-center gap-2">
          <Segmentos rotulo="Visão das posições" opcoes={VISOES} valor={visao} aoMudar={setVisao} />
          {visao === "lista" && (
            <>
              <Input
                type="search"
                aria-label="Buscar ativo"
                placeholder="Ticker ou nome…"
                className="w-48"
                value={busca}
                onChange={(e) => {
                  setBusca(e.target.value);
                }}
              />
              <Select
                aria-label="Filtrar por tipo"
                className="w-48"
                value={tipo}
                onChange={(e) => {
                  setTipo(e.target.value);
                }}
              >
                <option value="">Todos os tipos</option>
                {tipos.data?.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.nome}
                  </option>
                ))}
              </Select>
            </>
          )}
        </div>
      }
    >
      {visao === "instituicao" ? (
        <CarteiraPorInstituicao instituicaoId={instituicaoId} aoAbrir={aoAbrir} />
      ) : posicoes.isPending ? (
        <Carregando />
      ) : posicoes.isError ? (
        <EstadoErro
          erro={posicoes.error}
          aoTentarNovamente={() => {
            void posicoes.refetch();
          }}
        />
      ) : posicoes.data.length === 0 ? (
        <EstadoVazio
          titulo="Nenhuma posição aberta"
          descricao='Registre uma compra ou aporte em "Nova movimentação": o ativo é cadastrado junto.'
        />
      ) : filtradas.length === 0 ? (
        <EstadoVazio titulo="Nenhuma posição com esses filtros" />
      ) : (
        <TabelaDados
          rotulo="Posições"
          dados={filtradas}
          colunas={colunas}
          ordenacaoInicial={[{ id: "valor_brl", desc: true }]}
          idDaLinha={(p) => `${p.ativo_id}-${p.instituicao_id ?? "geral"}`}
          aoClicarLinha={(p) => {
            aoAbrir(p.ativo_id);
          }}
        />
      )}
    </Secao>
  );
}

function AlocacaoCarteira({ instituicaoId }: { instituicaoId: number | null }) {
  const alocacao = useAlocacao(instituicaoId);
  if (alocacao.isPending) return <Carregando />;
  if (alocacao.isError) return <EstadoErro erro={alocacao.error} />;
  if (alocacao.data.length === 0) return <EstadoVazio titulo="Nada investido ainda" />;
  return <GraficoAlocacao fatias={alocacao.data} />;
}

const colunaAtivo = createColumnHelper<Ativo>();

function AtivosCadastrados({
  statusPorAtivo,
  aoAbrir,
}: {
  statusPorAtivo: Map<number, StatusAtivo>;
  aoAbrir: (ativoId: number) => void;
}) {
  const ativos = useAtivos();
  const tipos = useTiposAtivo();
  const colunas = useMemo(
    () => [
      colunaAtivo.accessor((a) => a.simbolo ?? a.nome, {
        id: "ativo",
        header: "Ativo",
        cell: ({ row }) => (
          <span className="flex flex-col">
            <span className="font-medium">{row.original.simbolo ?? row.original.nome}</span>
            {row.original.simbolo && (
              <span className="text-xs text-muted-foreground">{row.original.nome}</span>
            )}
          </span>
        ),
      }),
      colunaAtivo.accessor("tipo", {
        header: "Tipo",
        cell: ({ getValue }) => nomeDoTipo(tipos.data, getValue()),
      }),
      colunaAtivo.accessor("moeda", { header: "Moeda" }),
      colunaAtivo.display({
        id: "preco",
        header: "Último preço",
        meta: { numerica: true },
        cell: ({ row }) => {
          const s = statusPorAtivo.get(row.original.id);
          return (
            <span className="inline-flex items-center gap-1">
              {formatarPreco(s?.valor, row.original.moeda)}
              {s && <IndicadorDefasado defasado={s.defasado} aviso={s.aviso} />}
            </span>
          );
        },
      }),
      colunaAtivo.display({
        id: "atualizacao",
        header: "Atualização",
        cell: ({ row }) => <Atualizacao status={statusPorAtivo.get(row.original.id)} />,
      }),
    ],
    [tipos.data, statusPorAtivo],
  );
  if (ativos.isPending) return <Carregando />;
  if (ativos.isError) return <MensagemErro erro={ativos.error} />;
  if (ativos.data.length === 0) {
    return (
      <EstadoVazio
        titulo="Nenhum ativo cadastrado"
        descricao='Use "Nova movimentação": o ativo é cadastrado junto com a primeira compra.'
      />
    );
  }
  return (
    <TabelaDados
      rotulo="Ativos cadastrados"
      dados={ativos.data}
      colunas={colunas}
      ordenacaoInicial={[{ id: "ativo", desc: false }]}
      idDaLinha={(a) => String(a.id)}
      aoClicarLinha={(a) => {
        aoAbrir(a.id);
      }}
    />
  );
}
