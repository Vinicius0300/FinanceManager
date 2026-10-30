import { open, save } from "@tauri-apps/plugin-dialog";

/**
 * Diálogos nativos do Windows (plugin dialog do Tauri). O capability libera só
 * `dialog:allow-save` e `dialog:allow-open`: o front escolhe o caminho e quem lê ou grava
 * o arquivo é o backend (exportação Excel, restauração de backup).
 * Devolvem `null` quando o usuário cancela.
 */
export async function escolherOndeSalvar(
  nomeSugerido: string,
  filtro: { nome: string; extensoes: string[] },
): Promise<string | null> {
  return await save({
    defaultPath: nomeSugerido,
    filters: [{ name: filtro.nome, extensions: filtro.extensoes }],
  });
}

export async function escolherArquivo(filtro: {
  nome: string;
  extensoes: string[];
}): Promise<string | null> {
  const escolhido = await open({
    multiple: false,
    directory: false,
    filters: [{ name: filtro.nome, extensions: filtro.extensoes }],
  });
  return typeof escolhido === "string" ? escolhido : null;
}
