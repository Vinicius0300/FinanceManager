import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { Campo } from "@/components/Campo";
import { Carregando, EstadoErro, MensagemErro } from "@/components/Estados";
import { SeletorTema } from "@/components/SeletorTema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TelaStatusBackend } from "@/features/status-backend/TelaStatusBackend";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import { aplicarErrosDaApi } from "@/lib/formularios";
import { SecaoBackups } from "./Backups";
import { esquemaIntervalo } from "./definicoes";
import { SecaoIndicadores } from "./Indicadores";
import { SecaoListasTickers } from "./ListasTickers";

/**
 * Intervalo de atualização, tema, indicadores, lista de tickers, backup/restauração e
 * serviço interno.
 */
export function TelaConfiguracoes({ agora = new Date() }: { agora?: Date }) {
  return (
    <div className="flex flex-col gap-4">
      <CabecalhoPagina titulo="Configurações" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Secao titulo="Atualização automática">
          <FormularioIntervalo />
        </Secao>
        <Secao titulo="Aparência">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Tema</p>
              <p className="text-xs text-muted-foreground">Claro ou escuro (padrão: escuro).</p>
            </div>
            <SeletorTema />
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Todos os valores são exibidos em reais (BRL); ativos em dólar são convertidos pelo
            câmbio.
          </p>
        </Secao>
      </div>
      <SecaoIndicadores agora={agora} />
      <SecaoListasTickers />
      <SecaoBackups />
      <Secao titulo="Serviço interno">
        <TelaStatusBackend />
      </Secao>
    </div>
  );
}

function FormularioIntervalo() {
  const { cliente } = useClienteApi();
  const configuracoes = useQuery({
    queryKey: ["configuracoes"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/configuracoes", { signal })),
  });
  const salvar = useGravacao(async (dados: z.output<typeof esquemaIntervalo>) =>
    exigir(await cliente.PUT("/api/configuracoes", { body: dados })),
  );
  const form = useForm<
    { intervalo_atualizacao_min: string },
    unknown,
    z.output<typeof esquemaIntervalo>
  >({
    resolver: zodResolver(esquemaIntervalo),
    defaultValues: { intervalo_atualizacao_min: "" },
  });
  const [salvo, setSalvo] = useState(false);
  const atual = configuracoes.data?.intervalo_atualizacao_min;
  useEffect(() => {
    if (atual !== undefined) form.reset({ intervalo_atualizacao_min: String(atual) });
  }, [atual, form]);

  if (configuracoes.isPending) return <Carregando />;
  if (configuracoes.isError) return <EstadoErro erro={configuracoes.error} />;

  const enviar = form.handleSubmit(async (dados) => {
    setSalvo(false);
    try {
      await salvar.mutateAsync(dados);
      setSalvo(true);
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, ["intervalo_atualizacao_min"]);
    }
  });
  return (
    <form
      noValidate
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        void enviar(e);
      }}
    >
      <Campo
        rotulo="Intervalo de ações e cripto (minutos)"
        erro={form.formState.errors.intervalo_atualizacao_min?.message}
        ajuda="De 1 a 15 minutos (padrão 5). Vale na hora."
        className="w-64"
      >
        <Input
          type="number"
          min={1}
          max={15}
          step={1}
          {...form.register("intervalo_atualizacao_min")}
        />
      </Campo>
      <Button type="submit" disabled={salvar.isPending}>
        {salvar.isPending && <Loader2 aria-hidden className="animate-spin" />}
        Salvar
      </Button>
      {salvo && (
        <p role="status" className="w-full text-sm text-positivo">
          Intervalo salvo.
        </p>
      )}
      <div className="w-full">
        <MensagemErro erro={salvar.error} />
      </div>
    </form>
  );
}
