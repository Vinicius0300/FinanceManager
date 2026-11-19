import { useCallback, useEffect, useState } from "react";
import { Secao } from "@/components/CabecalhoPagina";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useHistorico, useResumoHistorico, type Operacao } from "./consultas";
import { DetalheOperacao } from "./DetalheOperacao";
import { useEstadoHistorico } from "./estado";
import { FILTROS_PADRAO, totalDePaginas, type FiltrosHistorico } from "./filtros";
import { Paginacao } from "./Paginacao";
import { PainelFiltros } from "./PainelFiltros";
import { CartoesResumo, GraficoMensal } from "./ResumoHistorico";
import { TabelaHistorico } from "./TabelaHistorico";
import { VisaoPorAtivo } from "./VisaoPorAtivo";

export function AbaHistorico({ agora }: { agora: Date }) {
  const { estado, consulta, atualizar } = useEstadoHistorico(agora);
  const lista = useHistorico(consulta, estado.ordem, estado.direcao, estado.pagina, estado.tamanho);
  const resumo = useResumoHistorico(consulta);
  const [aberta, setAberta] = useState<Operacao | null>(null);

  // Mudar filtros volta as duas visões para a primeira página.
  const mudarFiltros = useCallback(
    (filtros: FiltrosHistorico) => {
      atualizar({ filtros, pagina: 1, paginaAtivos: 1 });
    },
    [atualizar],
  );
  const limpar = () => {
    atualizar({ filtros: FILTROS_PADRAO, pagina: 1, paginaAtivos: 1 });
  };
  // "Ver em Operações com este filtro": ativo e instituição exatos, mantendo o resto.
  const verEmOperacoes = (ativoId: number, instituicaoId: number) => {
    atualizar({
      filtros: { ...estado.filtros, ativoId, instituicaoId },
      visao: "operacoes",
      pagina: 1,
      paginaAtivos: 1,
    });
  };

  // Página além da última (dados mudaram ou URL antiga): vai para a última que existe.
  const totalOperacoes = lista.data?.total;
  useEffect(() => {
    if (totalOperacoes === undefined || totalOperacoes === 0) return;
    const ultima = totalDePaginas(totalOperacoes, estado.tamanho);
    if (estado.pagina > ultima) atualizar({ pagina: ultima });
  }, [totalOperacoes, estado.tamanho, estado.pagina, atualizar]);

  const grupos = resumo.data?.por_ativo ?? [];
  const paginaAtivos = Math.min(
    estado.paginaAtivos,
    totalDePaginas(grupos.length, estado.tamanhoAtivos),
  );
  const gruposDaPagina = grupos.slice(
    (paginaAtivos - 1) * estado.tamanhoAtivos,
    paginaAtivos * estado.tamanhoAtivos,
  );

  const semOperacoes = consulta === null;
  const contagem = semOperacoes
    ? { filtradas: 0, total: resumo.data?.total_sem_filtros ?? 0 }
    : resumo.data
      ? { filtradas: resumo.data.totais.operacoes, total: resumo.data.total_sem_filtros }
      : null;
  const vazio = semOperacoes || (lista.data?.total === 0 && !lista.isFetching);

  return (
    <div className="flex flex-col gap-3.5">
      <PainelFiltros
        filtros={estado.filtros}
        aoMudar={mudarFiltros}
        aoLimpar={limpar}
        contagem={contagem}
      />
      {resumo.isError ? (
        <EstadoErro
          erro={resumo.error}
          aoTentarNovamente={() => {
            void resumo.refetch();
          }}
        />
      ) : (
        <CartoesResumo
          resumo={semOperacoes ? undefined : resumo.data}
          carregando={resumo.isPending && !semOperacoes}
        />
      )}
      {!semOperacoes && resumo.data && resumo.data.serie.length > 0 && (
        <Secao titulo="Compras × vendas por mês">
          <GraficoMensal resumo={resumo.data} />
        </Secao>
      )}
      <Secao
        titulo="Histórico de operações"
        acoes={
          <div role="group" aria-label="Visão da tabela" className="flex gap-1">
            {(
              [
                ["operacoes", "Operações"],
                ["ativos", "Por ativo"],
              ] as const
            ).map(([valor, rotulo]) => (
              <Button
                key={valor}
                size="sm"
                variant="ghost"
                aria-pressed={estado.visao === valor}
                className={cn(estado.visao === valor && "bg-secondary text-secondary-foreground")}
                onClick={() => {
                  atualizar({ visao: valor });
                }}
              >
                {rotulo}
              </Button>
            ))}
          </div>
        }
      >
        {vazio ? (
          <EstadoVazio
            titulo="Nenhuma operação com esses filtros"
            acao={
              <Button variant="outline" size="sm" onClick={limpar}>
                Limpar filtros
              </Button>
            }
          />
        ) : estado.visao === "ativos" ? (
          resumo.isPending ? (
            <Carregando />
          ) : resumo.data ? (
            <VisaoPorAtivo
              grupos={gruposDaPagina}
              consulta={consulta}
              aoAbrir={setAberta}
              aoVerEmOperacoes={verEmOperacoes}
            />
          ) : null
        ) : lista.isPending ? (
          <Carregando />
        ) : lista.isError ? (
          <EstadoErro
            erro={lista.error}
            aoTentarNovamente={() => {
              void lista.refetch();
            }}
          />
        ) : (
          <div className={cn(lista.isPlaceholderData && "opacity-60 transition-opacity")}>
            <TabelaHistorico
              operacoes={lista.data.itens}
              ordem={estado.ordem}
              direcao={estado.direcao}
              aoOrdenar={(ordem, direcao) => {
                atualizar({ ordem, direcao, pagina: 1 });
              }}
              aoAbrir={setAberta}
            />
          </div>
        )}
        {!vazio &&
          (estado.visao === "ativos"
            ? resumo.data && (
                <Paginacao
                  total={grupos.length}
                  pagina={paginaAtivos}
                  tamanho={estado.tamanhoAtivos}
                  unidade={{ singular: "ativo", plural: "ativos" }}
                  aoPaginar={(paginaNova) => {
                    atualizar({ paginaAtivos: paginaNova });
                  }}
                  aoMudarTamanho={(tamanho) => {
                    atualizar({ tamanhoAtivos: tamanho, paginaAtivos: 1 });
                  }}
                />
              )
            : lista.data && (
                <Paginacao
                  total={lista.data.total}
                  pagina={estado.pagina}
                  tamanho={estado.tamanho}
                  unidade={{ singular: "operação", plural: "operações" }}
                  aoPaginar={(paginaNova) => {
                    atualizar({ pagina: paginaNova });
                  }}
                  aoMudarTamanho={(tamanho) => {
                    atualizar({ tamanho, pagina: 1 });
                  }}
                />
              ))}
      </Secao>
      {aberta && (
        <DetalheOperacao
          operacao={aberta}
          aoFechar={() => {
            setAberta(null);
          }}
        />
      )}
    </div>
  );
}
