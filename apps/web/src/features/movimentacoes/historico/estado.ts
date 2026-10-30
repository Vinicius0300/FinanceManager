import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { consultaDaApi, gravarEstado, lerEstado, type EstadoHistorico } from "./filtros";

/** Estado do histórico guardado na URL (filtros, ordem, página e visão). */
export function useEstadoHistorico(agora: Date) {
  const [params, setParams] = useSearchParams();
  const estado = useMemo(() => lerEstado(params), [params]);
  const consulta = useMemo(() => consultaDaApi(estado.filtros, agora), [estado.filtros, agora]);
  const atualizar = useCallback(
    (mudanca: Partial<EstadoHistorico>) => {
      setParams((atuais) => gravarEstado({ ...lerEstado(atuais), ...mudanca }, atuais), {
        replace: true,
      });
    },
    [setParams],
  );
  return { estado, consulta, atualizar };
}
