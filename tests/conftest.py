"""Fixtures compartilhadas pelos testes.

Todos os testes usam uma data fixa (HOJE) em vez de date.today(), para que o
resultado seja sempre o mesmo, em qualquer dia em que o teste for executado.
"""

from datetime import date

import pandas as pd
import pytest

import analytics
import database
from constantes import COLUNAS_DEMANDA

HOJE = date(2026, 10, 18)


@pytest.fixture
def hoje():
    return HOJE


@pytest.fixture
def criar_df():
    """Devolve uma função que monta um DataFrame de demandas a partir de dicts.

    Só é preciso informar os campos que importam para o teste; os demais recebem
    valores padrão.
    """

    def _criar(linhas):
        padrao = {
            "titulo": "Demanda",
            "descricao": "",
            "responsavel": "Ana",
            "setor": "TI",
            "prioridade": "Média",
            "status": "Pendente",
            "data_criacao": "2026-10-01",
            "prazo": "2026-10-30",
            "data_conclusao": None,
        }
        registros = [{**padrao, "id": i, **linha} for i, linha in enumerate(linhas, start=1)]
        return analytics.padronizar_dataframe(pd.DataFrame(registros, columns=COLUNAS_DEMANDA))

    return _criar


@pytest.fixture
def caminho_banco(tmp_path):
    """Banco SQLite temporário e já inicializado (apagado após cada teste)."""
    caminho = tmp_path / "teste.db"
    database.init_db(caminho)
    return caminho


@pytest.fixture
def dados_validos():
    """Dados mínimos de uma demanda válida."""
    return {
        "titulo": "Enviar relatório",
        "descricao": "Relatório mensal",
        "responsavel": "Ana Souza",
        "setor": "Operações",
        "prioridade": "Alta",
        "status": "Pendente",
        "data_criacao": date(2026, 10, 1),
        "prazo": date(2026, 10, 30),
    }
