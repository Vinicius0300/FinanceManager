import { useEffect, useMemo, useRef, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { rotuloCategoria, tokenCategoria, type IdCategoria } from "./dominio/categorias";
import { relacionados, type IndiceGlossario } from "./dominio/indice";
import { converterLinks, ROTA_GLOSSARIO, rotaDoTermo } from "./dominio/links";
import { formatarRevisao, type Termo } from "./dominio/termo";

/** Bolinha com a cor da categoria (cor vinda do token do gráfico). */
export function MarcadorCategoria({
  categoria,
  className,
}: {
  categoria: IdCategoria;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2.5 shrink-0 rounded-full", className)}
      style={{ backgroundColor: tokenCategoria(categoria) }}
    />
  );
}

/**
 * Elementos do Markdown com o estilo do app (tokens). Links para `/glossario/...` viram
 * links do React Router (navegação sem recarregar); o conteúdo não tem links externos, e
 * qualquer outro endereço vira texto simples.
 */
const COMPONENTES: Components = {
  a: ({ href, children }) =>
    href?.startsWith(`${ROTA_GLOSSARIO}/`) ? (
      <Link
        to={href}
        className="font-medium text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary"
      >
        {children}
      </Link>
    ) : (
      <span>{children}</span>
    ),
  h2: ({ children }) => <h3 className="mt-5 mb-1.5 text-sm font-bold first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-3 mb-1 text-sm font-semibold">{children}</h4>,
  p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border">
      <table className="w-full border-collapse text-[0.8rem]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b px-2.5 py-1.5 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border-b px-2.5 py-1.5 align-top">{children}</td>,
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 text-[0.8em]">{children}</code>
  ),
};

function Rotulo({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </p>
  );
}

/** Explicação de um termo: cabeçalho, corpo em Markdown, relacionados e data de revisão. */
export function Verbete({ termo, indice }: { termo: Termo; indice: IndiceGlossario }) {
  const titulo = useRef<HTMLHeadingElement>(null);
  const corpo = useMemo(
    () => converterLinks(termo.corpo, (slug) => indice.porSlug.get(slug)?.titulo),
    [termo, indice],
  );
  const vizinhos = relacionados(indice, termo.slug);

  // Ao trocar de termo, o foco vai para o título: o leitor de tela anuncia o verbete novo
  // e quem navega pelo teclado continua dali. Em janela estreita o verbete fica abaixo do
  // grafo; se ele estiver fora da vista, a tela rola até ele.
  useEffect(() => {
    const elemento = titulo.current;
    if (!elemento) return;
    elemento.focus({ preventScroll: true });
    const { top, bottom } = elemento.getBoundingClientRect();
    if (top > window.innerHeight || bottom < 0) {
      elemento.scrollIntoView({ block: "start" });
    }
  }, [termo.slug]);

  return (
    <article aria-labelledby="titulo-verbete" className="text-sm">
      <header className="mb-3 space-y-1.5">
        <h2
          id="titulo-verbete"
          ref={titulo}
          tabIndex={-1}
          className="text-lg leading-tight font-bold outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {termo.titulo}
        </h2>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <MarcadorCategoria categoria={termo.categoria} />
          {rotuloCategoria(termo.categoria)}
        </p>
        {termo.sinonimos.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Também chamado de: {termo.sinonimos.join(", ")}
          </p>
        )}
      </header>

      <Markdown remarkPlugins={[remarkGfm]} components={COMPONENTES} skipHtml>
        {corpo}
      </Markdown>

      <footer className="mt-5 space-y-3 border-t pt-3">
        <div className="space-y-1.5">
          <Rotulo>Relacionados</Rotulo>
          {vizinhos.length === 0 ? (
            <p className="text-muted-foreground">Nenhum termo relacionado.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {vizinhos.map((v) => (
                <li key={v.slug}>
                  <Link
                    to={rotaDoTermo(v.slug)}
                    className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <MarcadorCategoria categoria={v.categoria} className="size-2" />
                    {v.titulo}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Revisado em {formatarRevisao(termo.revisadoEm)}.
        </p>
      </footer>
    </article>
  );
}
