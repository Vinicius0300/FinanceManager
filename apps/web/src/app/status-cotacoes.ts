/**
 * Contagem do chip de status das cotações (Parte 5A, decisão 10): só ativos com posição
 * aberta; cada ativo numa única categoria, com prioridade erro > defasado > em dia.
 */
export interface StatusParaContagem {
  ativo_id: number;
  defasado: boolean;
  ultimo_erro?: string | null;
}

export interface ContagemStatus {
  emDia: number;
  defasadas: number;
  comErro: number;
}

export function contarStatus(
  status: readonly StatusParaContagem[],
  abertos: ReadonlySet<number>,
): ContagemStatus {
  const contagem: ContagemStatus = { emDia: 0, defasadas: 0, comErro: 0 };
  for (const item of status) {
    if (!abertos.has(item.ativo_id)) continue;
    if (item.ultimo_erro) contagem.comErro += 1;
    else if (item.defasado) contagem.defasadas += 1;
    else contagem.emDia += 1;
  }
  return contagem;
}

/** "N em dia · N defasadas · N com erro", sem as categorias zeradas (tudo zero: "0 em dia"). */
export function textoStatus({ emDia, defasadas, comErro }: ContagemStatus): string {
  const partes = [
    emDia > 0 && `${emDia} em dia`,
    defasadas > 0 && `${defasadas} ${defasadas === 1 ? "defasada" : "defasadas"}`,
    comErro > 0 && `${comErro} com erro`,
  ].filter((p): p is string => typeof p === "string");
  return partes.length > 0 ? partes.join(" · ") : "0 em dia";
}
