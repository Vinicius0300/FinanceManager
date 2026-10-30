import { Loader2, Search, X } from "lucide-react";
import { useId, useState, type KeyboardEvent } from "react";
import { MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { nomeDoTipo, type TipoAtivo } from "@/lib/consultas-comuns";
import { cn } from "@/lib/utils";
import { useBuscaSimbolos, useTextoComEspera, type ItemBusca } from "./consultas";

/** O que o usuário escolheu na busca: um resultado ou um ticker digitado à mão. */
export type Escolha =
  { origem: "resultado"; item: ItemBusca } | { origem: "manual"; simbolo: string };

const NOMES_BOLSA: Record<string, string> = { B3: "B3", EUA: "bolsa americana (NASDAQ)" };

/** Etiqueta curta de cada resultado (de onde veio e o que vai acontecer). */
function etiquetaDoItem(
  item: ItemBusca,
  tipoEscolhido: string,
  tipos: readonly TipoAtivo[] | undefined,
): string {
  if (item.origem === "carteira") {
    return item.tipo === tipoEscolhido
      ? "Na carteira"
      : `Na carteira como ${nomeDoTipo(tipos, item.tipo ?? "")}`;
  }
  if (item.tipo === null) return "Fora da lista oficial · novo";
  if (item.tipo !== tipoEscolhido) return `Lista oficial: ${nomeDoTipo(tipos, item.tipo)} · novo`;
  return "Novo, será cadastrado";
}

/**
 * Combobox de busca do ativo (compra e aporte dos tipos com ticker): digite o ticker ou
 * parte do nome; aparecem os ativos da carteira, a lista oficial da bolsa e a pesquisa
 * externa. Também dá para cadastrar um ticker que não aparece (com aviso).
 * Teclado: ↑/↓ escolhem, Enter confirma, Esc fecha.
 */
export function BuscaAtivo({
  tipo,
  tipos,
  erro,
  aoEscolher,
}: {
  tipo: TipoAtivo;
  tipos: readonly TipoAtivo[] | undefined;
  erro?: string | undefined;
  aoEscolher: (escolha: Escolha) => void;
}) {
  const id = useId();
  const idLista = `${id}-lista`;
  const idStatus = `${id}-status`;
  const idErro = `${id}-erro`;
  const [texto, setTexto] = useState("");
  const [aberta, setAberta] = useState(false);
  const [destaque, setDestaque] = useState(0);
  const termo = useTextoComEspera(texto);
  const busca = useBuscaSimbolos(tipo.slug, termo);
  const resultado = busca.data;
  const digitado = texto.trim().toUpperCase();
  // O cadastro manual só aparece depois que a busca do texto atual respondeu (senão ele
  // passaria na frente dos resultados ainda a caminho).
  const buscaConcluida = busca.isSuccess && !busca.isFetching && termo === texto.trim();
  const opcoes: Escolha[] = [
    ...(resultado?.itens ?? []).map((item): Escolha => ({ origem: "resultado", item })),
    ...(buscaConcluida && !(resultado?.itens ?? []).some((i) => i.simbolo === digitado)
      ? [{ origem: "manual", simbolo: digitado } as Escolha]
      : []),
  ];
  const mostrarLista = aberta && texto.trim() !== "";
  const atual = Math.min(destaque, Math.max(opcoes.length - 1, 0));

  const escolher = (escolha: Escolha | undefined) => {
    if (!escolha) return;
    aoEscolher(escolha);
    setAberta(false);
    setTexto("");
  };

  const aoTeclar = (evento: KeyboardEvent<HTMLInputElement>) => {
    if (evento.key === "ArrowDown") {
      evento.preventDefault();
      setAberta(true);
      setDestaque((atual + 1) % Math.max(opcoes.length, 1));
    } else if (evento.key === "ArrowUp") {
      evento.preventDefault();
      setDestaque((atual - 1 + opcoes.length) % Math.max(opcoes.length, 1));
    } else if (evento.key === "Enter") {
      if (mostrarLista) {
        evento.preventDefault();
        escolher(opcoes[atual]);
      }
    } else if (evento.key === "Escape") {
      setAberta(false);
    }
  };

  const bolsa = resultado?.bolsa ? (NOMES_BOLSA[resultado.bolsa] ?? resultado.bolsa) : null;
  const avisos: string[] = [];
  if (resultado?.atualizando_lista && bolsa) {
    avisos.push(`Atualizando a lista oficial da ${bolsa}… a busca se refaz sozinha.`);
  } else if (resultado && !resultado.lista_disponivel && bolsa) {
    avisos.push(
      `A lista oficial da ${bolsa} ainda não foi baixada (Configurações > Lista de tickers).`,
    );
  }
  if (resultado?.aviso) avisos.push(resultado.aviso);

  return (
    <div className="relative flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>
        Ativo
        <span aria-hidden className="text-muted-foreground">
          {" "}
          *
        </span>
      </Label>
      <div className="relative">
        <Search
          aria-hidden
          className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground"
        />
        <Input
          id={id}
          role="combobox"
          aria-expanded={mostrarLista}
          aria-controls={idLista}
          aria-autocomplete="list"
          aria-activedescendant={mostrarLista && opcoes.length > 0 ? `${id}-${atual}` : undefined}
          aria-invalid={erro ? true : undefined}
          aria-describedby={[idStatus, erro ? idErro : ""].filter(Boolean).join(" ")}
          autoComplete="off"
          className="pl-8"
          placeholder={
            tipo.lista_simbolos ? "Ticker ou nome (ex.: PETR4, Petrobras)" : "Símbolo ou nome"
          }
          value={texto}
          maxLength={60}
          onChange={(e) => {
            setTexto(e.target.value);
            setAberta(true);
            setDestaque(0);
          }}
          onFocus={() => {
            setAberta(true);
          }}
          onBlur={() => {
            setAberta(false);
          }}
          onKeyDown={aoTeclar}
        />
        {busca.isFetching && (
          <Loader2
            aria-hidden
            className="absolute top-2.5 right-2.5 size-4 animate-spin text-muted-foreground"
          />
        )}
      </div>
      <p id={idStatus} className="text-xs text-muted-foreground" aria-live="polite">
        {avisos.join(" ")}
      </p>
      {erro && (
        <p id={idErro} role="alert" className="text-xs text-negativo">
          {erro}
        </p>
      )}
      {mostrarLista && (
        <ul
          id={idLista}
          role="listbox"
          aria-label="Resultados da busca"
          className="absolute top-16 z-50 max-h-72 w-full overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {busca.isPending && termo === texto.trim() ? (
            <li className="px-2 py-1.5 text-sm text-muted-foreground">Buscando…</li>
          ) : busca.isError ? (
            <li className="px-2 py-1.5">
              <MensagemErro erro={busca.error} />
            </li>
          ) : null}
          {opcoes.map((opcao, indice) => (
            <li
              key={
                opcao.origem === "manual"
                  ? `manual-${opcao.simbolo}`
                  : `${opcao.item.origem}-${opcao.item.tipo ?? ""}-${opcao.item.ativo_id ?? ""}-${opcao.item.simbolo_externo ?? opcao.item.simbolo ?? opcao.item.nome}`
              }
              id={`${id}-${indice}`}
              role="option"
              aria-selected={indice === atual}
              className={cn(
                "flex cursor-pointer flex-col rounded-sm px-2 py-1.5 text-sm",
                indice === atual && "bg-accent text-accent-foreground",
              )}
              onMouseDown={(e) => {
                e.preventDefault(); // não perde o foco antes do clique
                escolher(opcao);
              }}
              onMouseEnter={() => {
                setDestaque(indice);
              }}
            >
              {opcao.origem === "manual" ? (
                <>
                  <span className="font-medium">Cadastrar “{opcao.simbolo}” manualmente</span>
                  <span className="text-xs text-muted-foreground">
                    Não encontrado nas listas; a cotação pode falhar.
                  </span>
                </>
              ) : (
                <>
                  <span className="font-medium">
                    {opcao.item.simbolo ? `${opcao.item.simbolo} · ` : ""}
                    {opcao.item.nome}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {etiquetaDoItem(opcao.item, tipo.slug, tipos)}
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Ativo já escolhido: resumo com o botão "Trocar". */
export function AtivoEscolhido({
  titulo,
  detalhe,
  bloqueado,
  aoTrocar,
}: {
  titulo: string;
  detalhe?: string | undefined;
  bloqueado?: boolean;
  aoTrocar: () => void;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span className="text-sm leading-none font-medium select-none">Ativo</span>
      <div className="flex min-h-9 items-center justify-between gap-2 rounded-md border bg-card px-3 py-1.5 text-sm">
        <div className="min-w-0">
          <p className="truncate font-medium">{titulo}</p>
          {detalhe && <p className="truncate text-xs text-muted-foreground">{detalhe}</p>}
        </div>
        {!bloqueado && (
          <Button type="button" variant="ghost" size="sm" onClick={aoTrocar}>
            <X aria-hidden />
            Trocar
          </Button>
        )}
      </div>
    </div>
  );
}
