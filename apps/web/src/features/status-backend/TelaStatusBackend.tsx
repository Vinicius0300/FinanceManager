import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { mensagemDeErro } from "@/lib/backend";
import { useClienteApi } from "@/lib/cliente-api";
import { formatarDataHora } from "@/lib/formatacao";
import { useHealth, usePing, useVersaoApp } from "./consultas";

/**
 * "Sobre" (versões do app e do serviço interno) e estado do backend: chamada à rota
 * protegida e verificação periódica do /health.
 */
export function TelaStatusBackend() {
  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 md:grid-cols-2">
      <CartaoSobre />
      <CartaoServico />
      <CartaoPing />
    </div>
  );
}

function CartaoSobre() {
  const app = useVersaoApp();
  const health = useHealth();
  const versaoApp = app.data ?? null;
  const versaoServico = health.data?.versao ?? null;
  const divergentes = versaoApp !== null && versaoServico !== null && versaoApp !== versaoServico;

  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Finanças</CardTitle>
        <CardDescription>
          App desktop local de finanças pessoais. Dados só neste computador, em
          <code className="mx-1">{"%APPDATA%\\Financas"}</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Versão do app</span>
          <span>{app.isPending ? "…" : (versaoApp ?? "—")}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Versão do serviço interno</span>
          <span>{health.isPending ? "…" : (versaoServico ?? "—")}</span>
        </div>
        {divergentes && (
          <p role="alert" className="flex items-start gap-2 text-aviso-texto">
            <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
            As versões do app ({versaoApp}) e do serviço interno ({versaoServico}) são diferentes.
            Reinstale o aplicativo para atualizar os dois juntos.
          </p>
        )}
      </CardContent>
    </Card>
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
