const formatadorDataHora = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "medium",
});

/** Formata um instante ISO 8601 (vindo da API) no fuso local, em pt-BR. */
export function formatarDataHora(iso: string): string {
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "data inválida";
  return formatadorDataHora.format(data);
}
