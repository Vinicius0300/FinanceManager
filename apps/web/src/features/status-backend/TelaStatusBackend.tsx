import { Loader2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { mensagemDeErro } from "@/lib/backend";
import { useClienteApi } from "@/lib/cliente-api";
import { formatarDataHora } from "@/lib/formatacao";
import { useHealth, usePing } from "./consultas";

/** Tela única da Parte 1: estado do backend e chamada à rota protegida. */
export function TelaStatusBackend() {
  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 md:grid-cols-2">
      <CartaoServico />
      <CartaoPing />
    </div>
  );
}

function CartaoServico() {
  const { conexao } = useClienteApi();
  const health = useHealth();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Serviço interno</CardTitle>
        <CardDescription>Backend local verificado a cada 10 segundos.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Estado</span>
          {health.isPending ? (
            <Badge variant="secondary">Verificando…</Badge>
          ) : health.isError ? (
            <Badge variant="perigo">Indisponível</Badge>
          ) : (
            <Badge variant="sucesso">Conectado</Badge>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Versão</span>
          <span>{health.data?.versao ?? "—"}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Endereço</span>
          <code className="text-xs">{conexao.urlBase}</code>
        </div>
        {health.isError && (
          <p role="alert" className="text-perigo">
            {mensagemDeErro(health.error)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function CartaoPing() {
  const ping = usePing();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Rota protegida</CardTitle>
        <CardDescription>
          <code>GET /api/ping</code> com o token de sessão.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {ping.isPending ? (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <Loader2 aria-hidden className="size-4 animate-spin" /> Chamando…
          </p>
        ) : ping.isError ? (
          <p role="alert" className="text-perigo">
            {mensagemDeErro(ping.error)}
          </p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Resposta</span>
              <Badge variant="sucesso">{ping.data.mensagem}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Horário do servidor</span>
              <span>{formatarDataHora(ping.data.horario)}</span>
            </div>
          </>
        )}
        <Button
          variant="outline"
          className="mt-2 justify-self-start"
          disabled={ping.isFetching}
          onClick={() => {
            void ping.refetch();
          }}
        >
          <RefreshCw aria-hidden className={ping.isFetching ? "animate-spin" : undefined} />
          Chamar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
