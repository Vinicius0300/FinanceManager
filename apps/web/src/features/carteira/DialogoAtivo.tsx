import { useState } from "react";
import { Campo } from "@/components/Campo";
import { Carregando, EstadoErro } from "@/components/Estados";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/input";
import { useTiposAtivo, type Ativo } from "@/lib/consultas-comuns";
import { FormularioAtivo } from "./FormularioAtivo";
import { useCriarAtivo, useEditarAtivo } from "./consultas";

/** Cadastro (tipo escolhível) ou edição (tipo, moeda e símbolo bloqueados) de um ativo. */
export function DialogoAtivo({
  aberto,
  aoMudar,
  ativo,
}: {
  aberto: boolean;
  aoMudar: (aberto: boolean) => void;
  ativo?: Ativo;
}) {
  const tipos = useTiposAtivo();
  const [slug, setSlug] = useState<string>(ativo?.tipo ?? "acao_br");
  const criar = useCriarAtivo();
  const editar = useEditarAtivo();
  const edicao = ativo !== undefined;
  const tipo = tipos.data?.find((t) => t.slug === (ativo?.tipo ?? slug));
  const mutacao = edicao ? editar : criar;

  const fechar = () => {
    criar.reset();
    editar.reset();
    aoMudar(false);
  };

  return (
    <Dialog
      open={aberto}
      onOpenChange={(abrir) => {
        if (!abrir) fechar();
        else aoMudar(true);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {edicao ? `Editar ${ativo.simbolo ?? ativo.nome}` : "Novo ativo"}
          </DialogTitle>
          <DialogDescription>
            Os campos mudam conforme o tipo de ativo. Valores com vírgula: 1.234,56.
          </DialogDescription>
        </DialogHeader>
        {tipos.isPending ? (
          <Carregando />
        ) : tipos.isError ? (
          <EstadoErro erro={tipos.error} />
        ) : (
          <>
            <Campo
              rotulo="Tipo de ativo"
              ajuda={edicao ? "O tipo não pode ser alterado." : tipo?.descricao}
            >
              <Select
                value={ativo?.tipo ?? slug}
                disabled={edicao}
                onChange={(e) => {
                  setSlug(e.target.value);
                  criar.reset();
                }}
              >
                {tipos.data.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.nome}
                  </option>
                ))}
              </Select>
            </Campo>
            {tipo && (
              <FormularioAtivo
                key={tipo.slug}
                tipo={tipo}
                ativo={ativo}
                ocupado={mutacao.isPending}
                erro={mutacao.error}
                aoCancelar={fechar}
                aoSalvar={async (entrada) => {
                  if (edicao) {
                    await editar.mutateAsync({
                      id: ativo.id,
                      corpo: {
                        nome: entrada.nome,
                        simbolo_externo: entrada.simbolo_externo ?? null,
                        metadados: entrada.metadados ?? {},
                      },
                    });
                  } else {
                    await criar.mutateAsync(entrada);
                  }
                  fechar();
                }}
              />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
