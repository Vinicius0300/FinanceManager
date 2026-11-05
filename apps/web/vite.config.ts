/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

/**
 * O Vitest guarda em disco os módulos já transformados (`fsModuleCache`) e só os refaz
 * quando o próprio arquivo muda. O índice do glossário usa `import.meta.glob` sobre a
 * pasta `conteudo/`: um termo novo (arquivo `.md` novo) não muda o `glossario.ts`, e o
 * teste de conteúdo continuaria vendo a lista antiga de arquivos. Este plugin tira só esse
 * módulo do cache; os `.md` e o resto continuam em cache.
 */
function semCacheDoIndiceDoGlossario(): Plugin {
  return {
    name: "financas:sem-cache-indice-glossario",
    configureVitest({ defineCacheKeyGenerator }) {
      defineCacheKeyGenerator(({ id }) =>
        id.replace(/\\/g, "/").endsWith("/features/glossario/conteudo/glossario.ts")
          ? false
          : undefined,
      );
    },
  };
}

// Porta fixa: o Tauri (devUrl) e o CORS do backend em modo dev esperam a 5173.
export default defineConfig({
  plugins: [react(), tailwindcss(), semCacheDoIndiceDoGlossario()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: "localhost",
  },
  build: {
    target: "es2022",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.tsx"],
    css: false,
  },
});
