"""Testes de fumaça da interface: abrem o app de verdade (sem navegador) e conferem
que nenhuma página quebra, com o banco vazio e com dados.

Usam `streamlit.testing.v1.AppTest`, que executa o app.py em memória. O banco é
temporário (variável de ambiente OPSBOARD_DB), então o banco real nunca é tocado.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import database

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PAGINAS = ["Visão geral", "Demandas", "Nova demanda", "Relatórios e dados", "Alertas de prazo"]


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    caminho = tmp_path / "app.db"
    monkeypatch.setenv("OPSBOARD_DB", str(caminho))
    return caminho


def _popular(caminho):
    hoje = date.today()
    database.init_db(caminho)
    exemplos = [
        ("Atrasada", "Pendente", "Alta", -5),
        ("Em andamento vencida", "Em andamento", "Média", -2),
        ("Vence logo", "Pendente", "Alta", 2),
        ("No prazo", "Pendente", "Baixa", 30),
        ("Concluída", "Concluída", "Média", -10),
    ]
    for titulo, status, prioridade, dias in exemplos:
        database.criar_demanda(
            {
                "titulo": titulo,
                "responsavel": "Ana",
                "setor": "TI",
                "prioridade": prioridade,
                "status": status,
                "data_criacao": hoje - timedelta(days=40),
                "prazo": hoje + timedelta(days=dias),
            },
            caminho,
        )


@pytest.mark.parametrize("pagina", PAGINAS)
def test_paginas_abrem_com_banco_vazio(banco_temporario, pagina):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["pagina"] = pagina
    at.run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_paginas_abrem_com_dados(banco_temporario, pagina):
    _popular(banco_temporario)
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["pagina"] = pagina
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_visao_geral_mostra_indicadores_do_banco(banco_temporario):
    _popular(banco_temporario)
    at = AppTest.from_file(APP, default_timeout=30).run()
    metricas = {m.label: m.value for m in at.metric}
    assert metricas["Total de demandas"] == "5"
    assert metricas["Concluídas"] == "1"
    assert metricas["Atrasadas"] == "2"
    assert metricas["Percentual de conclusão"] == "20.0%"
