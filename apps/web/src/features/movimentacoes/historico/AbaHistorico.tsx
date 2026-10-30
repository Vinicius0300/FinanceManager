import { useCallback, useState } from "react";
import {} from "react-router-dom";
import { Secao } from "@/components/CabecalhoPagina";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useHistorico, useResumoHistorico, type Operacao } from "./consultas";
import { DetalheOperacao } from "./DetalheOperacao";
import { useEstadoHistorico } from "./estado";
import { FILTROS_PADRAO, type FiltrosHistorico } from "./filtros";
import { PainelFiltros } from "./PainelFiltros";
import { CartoesResumo, GraficoMensal } from "./ResumoHistorico";
import { TabelaHistorico } from "./TabelaHistorico";
import { VisaoPorAtivo } from "./VisaoPorAtivo";

export function AbaHistorico({ agora }: { agora: Date }) {
  const { estado, consulta, atualizar } = useEstadoHistorico(agora);
  const lista = useHistorico(consulta, estado.ordem, estado.direcao, estado.pagina);
  const resumo = useResumoHistorico(consulta);
  const [aberta, setAberta] = useState<Operacao | null>(null);

  // Mudar filtros volta para a primeira página.
  const mudarFiltros = useCallback(
    (filtros: FiltrosHistorico) => {
      atualizar({ filtros, pagina: 1 });
    },
    [atualizar],
  );
  const limpar = () => {
    atualizar({ filtros: FILTROS_PADRAO, pagina: 1 });
  };

  const semOperacoes = consulta === null;
  const contagem = semOperacoes
    ? { filtradas: 0, total: resumo.data?.total_sem_filtros ?? 0 }
    : resumo.data
      ? { filtradas: resumo.data.totais.operacoes, total: resumo.data.total_sem_filtros }
      : null;
  const vazio = semOperacoes || (lista.data?.total === 0 && !lista.isFetching);

  return (
    <div className="flex flex-col gap-4">
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
            <VisaoPorAtivo grupos={resumo.data.por_ativo} />
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
              total={lista.data.total}
              pagina={estado.pagina}
              ordem={estado.ordem}
              direcao={estado.direcao}
              aoOrdenar={(ordem, direcao) => {
                atualizar({ ordem, direcao, pagina: 1 });
              }}
              aoPaginar={(pagina) => {
                atualizar({ pagina });
              }}
              aoAbrir={setAberta}
            />
          </div>
        )}
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
