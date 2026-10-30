import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Carregando, EstadoErro, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import {
  useCategorias,
  useExcluirCategoria,
  useSalvarCategoria,
  type Categoria,
  type TipoLancamento,
} from "./consultas";

const TAMANHO_NOME = 80;

function validarNome(nome: string): string | null {
  const limpo = nome.trim();
  if (!limpo) return "Informe o nome da categoria.";
  if (limpo.length > TAMANHO_NOME) return `Use no máximo ${TAMANHO_NOME} caracteres.`;
  return null;
}

/** Gerenciamento de categorias: criar, renomear e excluir (a API recusa se estiver em uso). */
export function DialogoCategorias({ aoFechar }: { aoFechar: () => void }) {
  const categorias = useCategorias();
  const salvar = useSalvarCategoria();
  const excluir = useExcluirCategoria();
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<TipoLancamento>("despesa");
  const [erroNome, setErroNome] = useState<string | null>(null);
  const [editando, setEditando] = useState<{ id: number; nome: string } | null>(null);
  const [excluindo, setExcluindo] = useState<Categoria | null>(null);

  const criar = () => {
    const erro = validarNome(nome);
    setErroNome(erro);
    if (erro) return;
    salvar.mutate(
      { nome: nome.trim(), tipo },
      {
        onSuccess: () => {
          setNome("");
        },
      },
    );
  };

  const renomear = () => {
    if (!editando) return;
    const erro = validarNome(editando.nome);
    setErroNome(erro);
    if (erro) return;
    const categoria = categorias.data?.find((c) => c.id === editando.id);
    if (!categoria) return;
    salvar.mutate(
      { id: editando.id, nome: editando.nome.trim(), tipo: categoria.tipo },
      {
        onSuccess: () => {
          setEditando(null);
        },
      },
    );
  };

  const grupos: { tipo: TipoLancamento; titulo: string }[] = [
    { tipo: "despesa", titulo: "Despesas" },
    { tipo: "receita", titulo: "Receitas" },
  ];

  return (
    <>
      <Dialog
        open
        onOpenChange={(aberto) => {
          if (!aberto) aoFechar();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Categorias</DialogTitle>
            <DialogDescription>
              Usadas para agrupar receitas e despesas. Só o nome pode ser alterado.
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-wrap items-start gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              criar();
            }}
          >
            <div className="flex min-w-48 flex-1 flex-col gap-1">
              <Input
                aria-label="Nome da nova categoria"
                placeholder="Nova categoria"
                maxLength={TAMANHO_NOME}
                value={nome}
                aria-invalid={erroNome && !editando ? true : undefined}
                onChange={(e) => {
                  setNome(e.target.value);
                }}
              />
            </div>
            <Select
              aria-label="Tipo da nova categoria"
              className="w-32"
              value={tipo}
              onChange={(e) => {
                setTipo(e.target.value as TipoLancamento);
              }}
            >
              <option value="despesa">Despesa</option>
              <option value="receita">Receita</option>
            </Select>
            <Button type="submit" disabled={salvar.isPending}>
              <Plus aria-hidden />
              Adicionar
            </Button>
          </form>
          {erroNome && (
            <p role="alert" className="text-xs text-negativo">
              {erroNome}
            </p>
          )}
          <MensagemErro erro={salvar.error} />
          {categorias.isPending ? (
            <Carregando />
          ) : categorias.isError ? (
            <EstadoErro erro={categorias.error} />
          ) : (
            grupos.map((g) => (
              <section key={g.tipo}>
                <h3 className="mb-1 text-sm font-semibold">{g.titulo}</h3>
                <ul className="grid gap-1">
                  {categorias.data
                    .filter((c) => c.tipo === g.tipo)
                    .map((c) => (
                      <li key={c.id} className="flex items-center justify-between gap-2 text-sm">
                        {editando?.id === c.id ? (
                          <>
                            <Input
                              aria-label={`Novo nome para ${c.nome}`}
                              value={editando.nome}
                              maxLength={TAMANHO_NOME}
                              onChange={(e) => {
                                setEditando({ id: c.id, nome: e.target.value });
                              }}
                            />
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label="Salvar nome"
                              onClick={renomear}
                            >
                              <Check aria-hidden />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label="Cancelar edição"
                              onClick={() => {
                                setEditando(null);
                              }}
                            >
                              <X aria-hidden />
                            </Button>
                          </>
                        ) : (
                          <>
                            <span>{c.nome}</span>
                            <span className="flex">
                              <Button
                                size="sm"
                                variant="ghost"
                                aria-label={`Renomear ${c.nome}`}
                                onClick={() => {
                                  setEditando({ id: c.id, nome: c.nome });
                                }}
                              >
                                <Pencil aria-hidden />
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                aria-label={`Excluir ${c.nome}`}
                                onClick={() => {
                                  excluir.reset();
                                  setExcluindo(c);
                                }}
                              >
                                <Trash2 aria-hidden />
                              </Button>
                            </span>
                          </>
                        )}
                      </li>
                    ))}
                </ul>
              </section>
            ))
          )}
        </DialogContent>
      </Dialog>
      <DialogoConfirmacao
        aberto={excluindo !== null}
        aoMudar={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo={`Excluir a categoria ${excluindo?.nome ?? ""}?`}
        descricao="Categorias com lançamentos não podem ser excluídas."
        ocupado={excluir.isPending}
        erro={excluir.error}
        aoConfirmar={() => {
          if (!excluindo) return;
          excluir.mutate(excluindo.id, {
            onSuccess: () => {
              setExcluindo(null);
            },
          });
        }}
      />
    </>
  );
}
