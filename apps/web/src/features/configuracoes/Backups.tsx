import { useQuery } from "@tanstack/react-query";
import { DatabaseBackup, FolderOpen, Loader2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Secao } from "@/components/CabecalhoPagina";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Carregando, EstadoErro, EstadoVazio, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao } from "@/lib/consultas-comuns";
import { escolherArquivo } from "@/lib/dialogos-nativos";
import { formatarDataHora } from "@/lib/formatacao";

type Origem = { nome: string } | { caminho: string };

function tamanho(bytes: number): string {
  if (bytes < 1024 * 1024)
    return `${(bytes / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} KB`;
  return `${(bytes / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`;
}

/**
 * Backup manual e restauração (da lista ou de um arquivo escolhido no diálogo nativo).
 * A restauração pede confirmação; a API faz antes um backup de segurança.
 */
export function SecaoBackups() {
  const { cliente } = useClienteApi();
  const backups = useQuery({
    queryKey: ["backups"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/backups", { signal })),
  });
  const criar = useGravacao(async () => exigir(await cliente.POST("/api/backups")));
  const restaurar = useGravacao(async (origem: Origem) =>
    exigir(await cliente.POST("/api/backups/restaurar", { body: origem })),
  );
  const [confirmando, setConfirmando] = useState<Origem | null>(null);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erroDialogo, setErroDialogo] = useState<unknown>(null);

  const escolher = async () => {
    setErroDialogo(null);
    try {
      const caminho = await escolherArquivo({ nome: "Banco do Finanças", extensoes: ["db"] });
      if (caminho) {
        restaurar.reset();
        setConfirmando({ caminho });
      }
    } catch (erro) {
      setErroDialogo(erro);
    }
  };

  return (
    <Secao
      titulo="Backup e restauração"
      acoes={
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={criar.isPending}
            onClick={() => {
              setMensagem(null);
              criar.mutate(undefined, {
                onSuccess: (b) => {
                  setMensagem(`Backup criado: ${b.nome}.`);
                },
              });
            }}
          >
            {criar.isPending ? (
              <Loader2 aria-hidden className="animate-spin" />
            ) : (
              <DatabaseBackup aria-hidden />
            )}
            Fazer backup agora
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              void escolher();
            }}
          >
            <FolderOpen aria-hidden />
            Restaurar de um arquivo…
          </Button>
        </div>
      }
    >
      {mensagem && (
        <p role="status" className="mb-2 text-sm text-positivo">
          {mensagem}
        </p>
      )}
      <MensagemErro erro={criar.error ?? erroDialogo} />
      {backups.isPending ? (
        <Carregando />
      ) : backups.isError ? (
        <EstadoErro
          erro={backups.error}
          aoTentarNovamente={() => {
            void backups.refetch();
          }}
        />
      ) : backups.data.length === 0 ? (
        <EstadoVazio titulo="Nenhum backup ainda" />
      ) : (
        <Table aria-label="Backups">
          <TableHeader>
            <TableRow>
              <TableHead>Arquivo</TableHead>
              <TableHead>Criado em</TableHead>
              <TableHead className="text-right">Tamanho</TableHead>
              <TableHead className="text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {backups.data.map((b) => (
              <TableRow key={b.nome}>
                <TableCell className="font-mono text-xs">{b.nome}</TableCell>
                <TableCell>{formatarDataHora(b.criado_em)}</TableCell>
                <TableCell className="tabular text-right">{tamanho(b.tamanho_bytes)}</TableCell>
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      restaurar.reset();
                      setConfirmando({ nome: b.nome });
                    }}
                  >
                    <RotateCcw aria-hidden />
                    Restaurar
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <DialogoConfirmacao
        aberto={confirmando !== null}
        aoMudar={(aberto) => {
          if (!aberto) setConfirmando(null);
        }}
        titulo="Restaurar este backup?"
        descricao={
          <>
            Todos os dados atuais serão substituídos pelo conteúdo de{" "}
            <strong>
              {confirmando && ("nome" in confirmando ? confirmando.nome : confirmando.caminho)}
            </strong>
            . Antes disso, o app faz um backup de segurança do estado atual.
          </>
        }
        textoConfirmar="Restaurar"
        ocupado={restaurar.isPending}
        erro={restaurar.error}
        aoConfirmar={() => {
          if (!confirmando) return;
          restaurar.mutate(confirmando, {
            onSuccess: (r) => {
              setConfirmando(null);
              setMensagem(
                `Dados restaurados de ${r.restaurado}. Backup de segurança: ${r.backup_seguranca.nome}.`,
              );
            },
          });
        }}
      />
    </Secao>
  );
}
