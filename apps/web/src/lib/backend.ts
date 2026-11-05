import { getVersion } from "@tauri-apps/api/app";
import { invoke, isTauri } from "@tauri-apps/api/core";
import createClient from "openapi-fetch";
import type { components, paths } from "@/api/schema";

/** Endereço e token do backend local, gerados pelo Tauri a cada abertura do app. */
export interface ConexaoBackend {
  urlBase: string;
  token: string;
}

export type ErroApi = components["schemas"]["ErroApi"];
export type DetalheErro = components["schemas"]["DetalheErro"];

export const MENSAGEM_FORA_DO_APP =
  "Esta tela precisa ser aberta pelo app Finanças (npm run dev). " +
  "No navegador comum o serviço interno não está disponível.";

/**
 * Aguarda o backend responder ao /health e devolve a conexão.
 * O Rust faz a espera (com timeout) e rejeita com mensagem em pt-BR.
 */
export async function obterConexaoBackend(): Promise<ConexaoBackend> {
  if (!isTauri()) throw new Error(MENSAGEM_FORA_DO_APP);
  try {
    return await invoke<ConexaoBackend>("conexao_backend");
  } catch (erro) {
    const mensagem =
      typeof erro === "string" ? erro : "Não foi possível iniciar o serviço interno.";
    throw new Error(mensagem, { cause: erro });
  }
}

/**
 * Versão do app instalado (a do `tauri.conf.json`, que vem do `package.json` da raiz).
 * Fora do Tauri (navegador comum, testes) devolve `null`.
 */
export async function obterVersaoApp(): Promise<string | null> {
  if (!isTauri()) return null;
  return getVersion();
}

/** Encerra e inicia novamente o backend (botão "Tentar novamente"). */
export async function reiniciarBackend(): Promise<void> {
  if (!isTauri()) throw new Error(MENSAGEM_FORA_DO_APP);
  await invoke("reiniciar_backend");
}

export function criarClienteApi(conexao: ConexaoBackend, fetchFn?: typeof fetch) {
  return createClient<paths>({
    baseUrl: conexao.urlBase,
    headers: { Authorization: `Bearer ${conexao.token}` },
    ...(fetchFn ? { fetch: fetchFn } : {}),
  });
}

export type ClienteApi = ReturnType<typeof criarClienteApi>;

/** Erro padronizado devolvido pela API ({codigo, mensagem, detalhes}), como exceção. */
export class FalhaApi extends Error {
  readonly codigo: string;
  readonly detalhes: DetalheErro[];
  readonly status: number | undefined;

  constructor(erro: ErroApi, status?: number) {
    super(erro.mensagem);
    this.name = "FalhaApi";
    this.codigo = erro.codigo;
    this.detalhes = erro.detalhes ?? [];
    this.status = status;
  }

  /** Mensagem de um campo específico (`detalhes` da API), se houver. */
  detalhe(campo: string): string | undefined {
    return this.detalhes.find((d) => d.campo === campo)?.mensagem;
  }
}

function ehErroApi(valor: unknown): valor is ErroApi {
  return (
    typeof valor === "object" &&
    valor !== null &&
    "mensagem" in valor &&
    typeof valor.mensagem === "string"
  );
}

export const MENSAGEM_SEM_CONEXAO =
  "Não foi possível conectar ao serviço interno. Ele pode ter sido encerrado.";
export const MENSAGEM_INESPERADA = "Ocorreu um erro inesperado.";

/**
 * Textos do `TypeError` que o `fetch` (e a leitura do corpo) lançam quando a conexão falha:
 * WebView2/Chromium ("Failed to fetch", "network error"), Firefox ("NetworkError when
 * attempting to fetch resource.") e WebKit ("Load failed").
 */
const FALHA_DE_REDE = /failed to fetch|networkerror|network error|load failed/i;

/** `true` só para a falha de rede do `fetch`, não para qualquer `TypeError`. */
export function ehFalhaDeRede(erro: unknown): erro is TypeError {
  return erro instanceof TypeError && FALHA_DE_REDE.test(erro.message);
}

/** Erros inesperados já enviados ao console (a mensagem é pedida a cada renderização). */
const registrados = new WeakSet();

function registrarNoConsole(erro: Error): void {
  if (registrados.has(erro)) return;
  registrados.add(erro);
  console.error("Erro inesperado no app:", erro);
}

/**
 * Converte qualquer falha (rede, erro da API, exceção) em texto compreensível. Um `TypeError`
 * que não é falha de rede é bug de código: mostra a mensagem genérica e vai para o console.
 */
export function mensagemDeErro(erro: unknown): string {
  if (ehErroApi(erro)) return erro.mensagem;
  if (ehFalhaDeRede(erro)) return MENSAGEM_SEM_CONEXAO;
  if (erro instanceof TypeError) {
    registrarNoConsole(erro);
    return MENSAGEM_INESPERADA;
  }
  if (erro instanceof Error && erro.message) return erro.message;
  return MENSAGEM_INESPERADA;
}
