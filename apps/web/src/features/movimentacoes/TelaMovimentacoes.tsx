import { FileSpreadsheet, Loader2, Plus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CabecalhoPagina } from "@/components/CabecalhoPagina";
import { MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { escolherOndeSalvar } from "@/lib/dialogos-nativos";
import { hojeIso } from "@/lib/datas";
import { plural } from "@/lib/formatacao";
import { AbaCaixa } from "./caixa/AbaCaixa";
import { AbaEventos } from "./eventos/AbaEventos";
import { AbaHistorico } from "./historico/AbaHistorico";
import { useEstadoHistorico } from "./historico/estado";
import { useExportarHistorico } from "./historico/consultas";
import { DialogoTransacao } from "./transacao/DialogoTransacao";

const ABAS = ["historico", "eventos", "caixa"] as const;
type Aba = (typeof ABAS)[number];

/** Movimentações: Histórico de operações, Eventos corporativos e Caixa (aba na URL). */
export function TelaMovimentacoes() {
  const [agora] = useState(() => new Date());
  const [params, setParams] = useSearchParams();
  const abaUrl = params.get("aba");
  const aba: Aba = ABAS.includes(abaUrl as Aba) ? (abaUrl as Aba) : "historico";
  const [nova, setNova] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <CabecalhoPagina
        titulo="Movimentações"
        acoes={
          <>
            {aba === "historico" && <BotaoExportar agora={agora} />}
            <Button
              onClick={() => {
                setNova(true);
              }}
            >
              <Plus aria-hidden />
              Nova movimentação
            </Button>
          </>
        }
      />
      <Tabs
        value={aba}
        onValueChange={(valor) => {
          setParams(
            (atuais) => {
              const novos = new URLSearchParams(atuais);
              if (valor === "historico") novos.delete("aba");
              else novos.set("aba", valor);
              return novos;
            },
            { replace: true },
          );
        }}
      >
        <TabsList>
          <TabsTrigger value="historico">Histórico de operações</TabsTrigger>
          <TabsTrigger value="eventos">Eventos corporativos</TabsTrigger>
          <TabsTrigger value="caixa">Caixa</TabsTrigger>
        </TabsList>
        <TabsContent value="historico">
          <AbaHistorico agora={agora} />
        </TabsContent>
        <TabsContent value="eventos">
          <AbaEventos agora={agora} />
        </TabsContent>
        <TabsContent value="caixa">
          <AbaCaixa agora={agora} />
        </TabsContent>
      </Tabs>
      {nova && <DialogoTransacao aberto={nova} aoMudar={setNova} agora={agora} />}
    </div>
  );
}

/**
 * Exporta o resultado filtrado (todos os filtros e todas as páginas) para Excel. O caminho
 * vem do diálogo nativo de salvar; quem grava é o backend.
 */
export function BotaoExportar({ agora }: { agora: Date }) {
  const { estado, consulta } = useEstadoHistorico(agora);
  const exportar = useExportarHistorico();
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erroDialogo, setErroDialogo] = useState<unknown>(null);

  const executar = async () => {
    setMensagem(null);
    setErroDialogo(null);
    exportar.reset();
    if (consulta === null) {
      setMensagem("Nenhuma operação marcada nos filtros: nada para exportar.");
      return;
    }
    let caminho: string | null;
    try {
      caminho = await escolherOndeSalvar(`historico-operacoes-${hojeIso(agora)}.xlsx`, {
        nome: "Planilha do Excel",
        extensoes: ["xlsx"],
      });
    } catch (erro) {
      setErroDialogo(erro);
      return;
    }
    if (!caminho) return; // cancelado
    const resultado = await exportar
      .mutateAsync({ consulta, ordem: estado.ordem, direcao: estado.direcao, caminho })
      .catch(() => null);
    if (resultado) {
      setMensagem(
        `Planilha salva em ${resultado.caminho} (${plural(resultado.linhas, "operação", "operações")}).`,
      );
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant="secondary"
        disabled={exportar.isPending}
        onClick={() => {
          void executar();
        }}
      >
        {exportar.isPending ? (
          <Loader2 aria-hidden className="animate-spin" />
        ) : (
          <FileSpreadsheet aria-hidden />
        )}
        Exportar Excel
      </Button>
      {mensagem && (
        <p role="status" className="max-w-sm text-right text-xs text-muted-foreground">
          {mensagem}
        </p>
      )}
      <MensagemErro erro={exportar.error ?? erroDialogo} />
    </div>
  );
}
