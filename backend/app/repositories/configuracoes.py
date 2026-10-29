"""Repositório de configurações (chave/valor JSON)."""

from app.repositories.base import RepositorioBase
from app.repositories.modelos import Configuracao


class RepositorioConfiguracoes(RepositorioBase[Configuracao]):
    modelo = Configuracao

    def valor(self, chave: str, padrao: object = None) -> object:
        registro = self.obter(chave)
        return padrao if registro is None else registro.valor

    def gravar(self, chave: str, valor: object) -> Configuracao:
        """Insere ou atualiza a chave (persistência simples, sem regra de negócio)."""
        registro = self.obter(chave)
        if registro is None:
            return self.adicionar(Configuracao(chave=chave, valor=valor))
        registro.valor = valor
        self.sessao.flush()
        return registro
