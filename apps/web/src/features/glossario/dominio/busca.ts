import { compararTitulos } from "./indice";
import type { Termo } from "./termo";

/** Minúsculas e sem acentos: "Ação" e "acao" ficam iguais. */
export function normalizar(texto: string): string {
  return texto.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * Busca por título, sinônimos e resumo, sem diferenciar acentos e maiúsculas.
 * Ordem do resultado: (0) título ou sinônimo igual ao texto, (1) título ou sinônimo
 * começando com o texto, (2) o texto aparece em qualquer parte; empate por título.
 * Busca vazia devolve todos os termos na ordem recebida.
 */
export function buscarTermos(termos: readonly Termo[], consulta: string): Termo[] {
  const alvo = normalizar(consulta);
  if (!alvo) return [...termos];
  const pontuados: { termo: Termo; nota: number }[] = [];
  for (const termo of termos) {
    const nomes = [termo.titulo, ...termo.sinonimos].map(normalizar);
    let nota: number | null = null;
    if (nomes.some((n) => n === alvo)) nota = 0;
    else if (nomes.some((n) => n.startsWith(alvo))) nota = 1;
    else if ([...nomes, normalizar(termo.resumo)].some((n) => n.includes(alvo))) nota = 2;
    if (nota !== null) pontuados.push({ termo, nota });
  }
  return pontuados
    .sort((x, y) => x.nota - y.nota || compararTitulos(x.termo.titulo, y.termo.titulo))
    .map((p) => p.termo);
}
