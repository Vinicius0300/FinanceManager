import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";
import { Secao } from "@/components/CabecalhoPagina";
import { Carregando, EstadoErro, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { formatarData, formatarDataHora } from "@/lib/formatacao";

const INTERVALO_DURANTE_ATUALIZACAO_MS = 2_000;

const NOMES_BOLSA: Record<string, string> = {
  B3: "B3 (ações, units, BDRs, ETFs e fundos listados)",
  EUA: "EUA (NASDAQ, NYSE e AMEX)",
};

/**
 * Listas oficiais de tickers usadas na busca do cadastro de movimentações (só ticker,
 * nome e tipo oficial; nenhuma cotação). Baixadas sozinhas na primeira abertura; o botão
 * baixa de novo em segundo plano (o fim chega pelo stream de eventos).
 */
export function SecaoListasTickers() {
  const { cliente } = useClienteApi();
  const queryClient = useQueryClient();
  const listas = useQuery({
    queryKey: ["simbolos", "listas"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/simbolos/listas", { signal })),
    refetchInterval: (consulta) =>
      consulta.state.data?.em_andamento ? INTERVALO_DURANTE_ATUALIZACAO_MS : false,
  });
  const atualizar = useMutation({
    mutationFn: async () => exigir(await cliente.POST("/api/simbolos/atualizar")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["simbolos"] }),
  });
  const emAndamento = listas.data?.em_andamento === true;

  return (
    <Secao titulo="Lista de tickers">
      <div className="grid gap-3">
        <p className="text-xs text-muted-foreground">
          Listas oficiais das bolsas usadas para encontrar o ativo e identificar o tipo dele (ação,
          ETF, fundo listado) ao registrar uma movimentação. Guardam só ticker e nome.
        </p>
        {listas.isPending ? (
          <Carregando />
        ) : listas.isError ? (
          <EstadoErro
            erro={listas.error}
            aoTentarNovamente={() => {
              void listas.refetch();
            }}
          />
        ) : (
          <ul className="grid gap-2">
            {listas.data.listas.map((lista) => (
              <li key={lista.bolsa} className="rounded-md border p-3 text-sm">
                <p className="font-medium">{NOMES_BOLSA[lista.bolsa] ?? lista.bolsa}</p>
                {lista.atualizado_em ? (
                  <p className="text-xs text-muted-foreground">
                    {lista.quantidade.toLocaleString("pt-BR")} papéis · atualizada em{" "}
                    {formatarDataHora(lista.atualizado_em)}
                    {lista.data_arquivo ? ` · arquivo de ${formatarData(lista.data_arquivo)}` : ""}
                    {lista.status_arquivo ? ` (${lista.status_arquivo.toLowerCase()})` : ""}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">Ainda não baixada.</p>
                )}
                {lista.ultimo_erro && (
                  <p role="alert" className="mt-1 text-xs text-negativo">
                    Última tentativa falhou: {lista.ultimo_erro}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            disabled={emAndamento || atualizar.isPending}
            onClick={() => {
              atualizar.mutate();
            }}
          >
            {emAndamento || atualizar.isPending ? (
              <Loader2 aria-hidden className="animate-spin" />
            ) : (
              <RefreshCw aria-hidden />
            )}
            {emAndamento ? "Atualizando…" : "Atualizar lista"}
          </Button>
          {atualizar.isSuccess && !emAndamento && (
            <p role="status" className="text-xs text-muted-foreground">
              {atualizar.data.mensagem}
            </p>
          )}
        </div>
        <MensagemErro erro={atualizar.error} />
      </div>
    </Secao>
  );
}
