import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { TEMA_PADRAO, useAplicarTema, useTemaStore } from "@/theme/tema";
import { SeletorTema } from "./SeletorTema";

function ComTema() {
  useAplicarTema();
  return <SeletorTema />;
}

describe("SeletorTema", () => {
  beforeEach(() => {
    localStorage.clear();
    useTemaStore.setState({ tema: TEMA_PADRAO });
    document.documentElement.classList.remove("dark");
  });

  it("começa no modo escuro", () => {
    render(<ComTema />);
    expect(TEMA_PADRAO).toBe("escuro");
    expect(screen.getByRole("switch", { name: "Modo escuro" })).toBeChecked();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("alterna entre escuro e claro a cada clique", async () => {
    render(<ComTema />);
    const chave = screen.getByRole("switch", { name: "Modo escuro" });

    await userEvent.click(chave);
    expect(chave).not.toBeChecked();
    expect(document.documentElement).not.toHaveClass("dark");
    expect(useTemaStore.getState().tema).toBe("claro");

    await userEvent.click(chave);
    expect(chave).toBeChecked();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("guarda a escolha para a próxima abertura", async () => {
    render(<ComTema />);
    await userEvent.click(screen.getByRole("switch", { name: "Modo escuro" }));
    expect(localStorage.getItem("financas-tema")).toContain('"tema":"claro"');
  });

  it("migra a preferência antiga 'sistema' para escuro", async () => {
    localStorage.setItem(
      "financas-tema",
      JSON.stringify({ state: { preferencia: "sistema" }, version: 0 }),
    );
    await useTemaStore.persist.rehydrate();
    expect(useTemaStore.getState().tema).toBe("escuro");
  });
});
