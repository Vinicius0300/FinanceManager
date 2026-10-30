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
import { useEditarAtivo } from "./consultas";

/**
 * Edição de um ativo (nome, símbolo na fonte e campos específicos). Tipo, moeda e ticker
 * ficam bloqueados. Desde a Parte 4.1 o cadastro é feito na própria movimentação
 * (formulário único em Movimentações); não há mais "Novo ativo" separado.
 */
export function DialogoAtivo({
  aberto,
  aoMudar,
  ativo,
}: {
  aberto: boolean;
  aoMudar: (aberto: boolean) => void;
  ativo: Ativo;
}) {
  const tipos = useTiposAtivo();
  const editar = useEditarAtivo();
  const tipo = tipos.data?.find((t) => t.slug === ativo.tipo);

  const fechar = () => {
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
          <DialogTitle>{`Editar ${ativo.simbolo ?? ativo.nome}`}</DialogTitle>
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
            <Campo rotulo="Tipo de ativo" ajuda="O tipo não pode ser alterado.">
              <Select value={ativo.tipo} disabled>
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
                ocupado={editar.isPending}
                erro={editar.error}
                aoCancelar={fechar}
                aoSalvar={async (entrada) => {
                  await editar.mutateAsync({
                    id: ativo.id,
                    corpo: {
                      nome: entrada.nome,
                      simbolo_externo: entrada.simbolo_externo ?? null,
                      metadados: entrada.metadados ?? {},
                    },
                  });
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
