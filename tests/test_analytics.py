"""Testes dos indicadores, regras de prazo e filtros (analytics.py)."""

from datetime import date

import pandas as pd
import pytest

import analytics


# --- Percentual de conclusão ---------------------------------------------------
def test_percentual_sem_demandas_e_zero():
    assert analytics.percentual_conclusao(0, 0) == 0.0


@pytest.mark.parametrize(
    "concluidas, total, esperado",
    [(0, 4, 0.0), (1, 4, 25.0), (2, 3, 66.666667), (5, 5, 100.0)],
)
def test_percentual_conclusao(concluidas, total, esperado):
    assert analytics.percentual_conclusao(concluidas, total) == pytest.approx(esperado, abs=1e-4)


# --- Atrasadas -----------------------------------------------------------------
def test_identifica_demandas_atrasadas(criar_df, hoje):
    df = criar_df(
        [
            {"prazo": "2026-10-17", "status": "Pendente"},  # 1: venceu ontem -> atrasada
            {"prazo": "2026-10-17", "status": "Em andamento"},  # 2: em andamento NÃO é concluída
            {"prazo": "2026-10-17", "status": "Concluída"},  # 3: concluída nunca é atrasada
            {"prazo": "2026-10-18", "status": "Pendente"},  # 4: vence hoje -> ainda no prazo
            {"prazo": "2026-10-19", "status": "Pendente"},  # 5: futuro
        ]
    )
    assert list(analytics.demandas_atrasadas(df, hoje)["id"]) == [1, 2]


# --- Prazo próximo ---------------------------------------------------------------
def test_identifica_prazo_proximo_nos_proximos_tres_dias(criar_df, hoje):
    df = criar_df(
        [
            {"prazo": "2026-10-18"},  # 1: hoje -> entra
            {"prazo": "2026-10-21"},  # 2: hoje + 3 dias -> entra (limite inclusivo)
            {"prazo": "2026-10-22"},  # 3: hoje + 4 dias -> fora
            {"prazo": "2026-10-17"},  # 4: já atrasada -> não é "próxima"
            {"prazo": "2026-10-19", "status": "Concluída"},  # 5: concluída -> fora
            {"prazo": "2026-10-20", "status": "Em andamento"},  # 6: em andamento -> entra
        ]
    )
    assert list(analytics.demandas_prazo_proximo(df, hoje)["id"]) == [1, 2, 6]


def test_alta_prioridade_abertas_ignora_concluidas(criar_df):
    df = criar_df(
        [
            {"prioridade": "Alta", "status": "Pendente"},
            {"prioridade": "Alta", "status": "Em andamento"},
            {"prioridade": "Alta", "status": "Concluída"},
            {"prioridade": "Baixa", "status": "Pendente"},
        ]
    )
    assert list(analytics.demandas_alta_prioridade_abertas(df)["id"]) == [1, 2]


def test_situacao_do_prazo(criar_df, hoje):
    df = criar_df(
        [
            {"prazo": "2026-10-10"},  # Atrasada
            {"prazo": "2026-10-20"},  # Vence em breve
            {"prazo": "2026-11-30"},  # No prazo
            {"prazo": "2026-10-10", "status": "Concluída"},  # Concluída
        ]
    )
    assert list(analytics.classificar_situacao_prazo(df, hoje)) == [
        "Atrasada",
        "Vence em breve",
        "No prazo",
        "Concluída",
    ]


# --- Indicadores -----------------------------------------------------------------
def test_indicadores_com_banco_vazio(criar_df, hoje):
    indicadores = analytics.calcular_indicadores(criar_df([]), hoje)
    assert indicadores == {
        "total": 0,
        "pendentes": 0,
        "em_andamento": 0,
        "concluidas": 0,
        "atrasadas": 0,
        "percentual_conclusao": 0.0,
        "prazo_proximo": 0,
        "alta_prioridade_abertas": 0,
    }


def test_demais_funcoes_aceitam_dataframe_vazio(criar_df, hoje):
    df = criar_df([])
    assert analytics.demandas_atrasadas(df, hoje).empty
    assert analytics.demandas_prazo_proximo(df, hoje).empty
    assert analytics.desempenho_mensal(df).empty
    assert analytics.resumo_por_responsavel(df, hoje).empty
    assert analytics.filtrar_demandas(df, hoje, busca="x", status=["Pendente"]).empty
    assert analytics.contagem_por(df, "status", ["Pendente"])["quantidade"].tolist() == [0]


def test_indicadores_calculados_a_partir_dos_dados(criar_df, hoje):
    df = criar_df(
        [
            {"status": "Pendente", "prazo": "2026-10-10"},  # atrasada
            {"status": "Em andamento", "prazo": "2026-10-12"},  # atrasada
            {"status": "Em andamento", "prazo": "2026-10-20", "prioridade": "Alta"},  # próxima
            {"status": "Concluída", "prazo": "2026-10-01", "data_conclusao": "2026-10-02"},
        ]
    )
    indicadores = analytics.calcular_indicadores(df, hoje)
    assert indicadores["total"] == 4
    assert indicadores["pendentes"] == 1
    assert indicadores["em_andamento"] == 2
    assert indicadores["concluidas"] == 1
    assert indicadores["atrasadas"] == 2
    assert indicadores["percentual_conclusao"] == pytest.approx(25.0)
    assert indicadores["prazo_proximo"] == 1
    assert indicadores["alta_prioridade_abertas"] == 1


def test_contagem_por_inclui_valores_com_zero(criar_df):
    df = criar_df([{"prioridade": "Alta"}, {"prioridade": "Alta"}])
    contagem = analytics.contagem_por(df, "prioridade", ["Baixa", "Média", "Alta"])
    assert contagem["prioridade"].tolist() == ["Baixa", "Média", "Alta"]
    assert contagem["quantidade"].tolist() == [0, 0, 2]


def test_desempenho_mensal_inclui_meses_intermediarios(criar_df):
    df = criar_df(
        [
            {"data_criacao": "2026-08-10", "prazo": "2026-08-30"},
            {
                "data_criacao": "2026-08-15",
                "prazo": "2026-09-01",
                "status": "Concluída",
                "data_conclusao": "2026-10-03",
            },
            {"data_criacao": "2026-10-05", "prazo": "2026-10-30"},
        ]
    )
    mensal = analytics.desempenho_mensal(df)
    assert mensal["mes"].tolist() == ["08/2026", "09/2026", "10/2026"]
    assert mensal["criadas"].tolist() == [2, 0, 1]
    assert mensal["concluidas"].tolist() == [0, 0, 1]


def test_resumo_por_responsavel(criar_df, hoje):
    df = criar_df(
        [
            {"responsavel": "Ana", "status": "Concluída", "prazo": "2026-10-01"},
            {"responsavel": "Ana", "status": "Pendente", "prazo": "2026-10-01"},  # atrasada
            {"responsavel": "Bia", "status": "Pendente", "prazo": "2026-12-01"},
        ]
    )
    resumo = analytics.resumo_por_responsavel(df, hoje).set_index("responsavel")
    assert resumo.loc["Ana", "total"] == 2
    assert resumo.loc["Ana", "atrasadas"] == 1
    assert resumo.loc["Ana", "percentual_conclusao"] == pytest.approx(50.0)
    assert resumo.loc["Bia", "percentual_conclusao"] == pytest.approx(0.0)


# --- Filtros ---------------------------------------------------------------------
@pytest.fixture
def df_filtros(criar_df):
    return criar_df(
        [
            {"titulo": "Relatório mensal", "status": "Pendente", "prioridade": "Alta",
             "responsavel": "Ana", "setor": "TI", "prazo": "2026-10-10"},
            {"titulo": "Revisar contrato", "status": "Concluída", "prioridade": "Alta",
             "responsavel": "Bia", "setor": "Jurídico", "prazo": "2026-10-20"},
            {"titulo": "Comprar notebooks", "status": "Pendente", "prioridade": "Baixa",
             "responsavel": "Ana", "setor": "TI", "prazo": "2026-11-20"},
            {"titulo": "Atualizar site", "status": "Em andamento", "prioridade": "Média",
             "responsavel": "Caio", "setor": "Marketing", "prazo": "2026-12-01"},
        ]
    )


def test_filtra_por_status(df_filtros, hoje):
    resultado = analytics.filtrar_demandas(df_filtros, hoje, status=["Pendente"])
    assert list(resultado["id"]) == [1, 3]


def test_filtra_por_prioridade(df_filtros, hoje):
    resultado = analytics.filtrar_demandas(df_filtros, hoje, prioridades=["Alta"])
    assert list(resultado["id"]) == [1, 2]


def test_filtros_funcionam_em_conjunto(df_filtros, hoje):
    resultado = analytics.filtrar_demandas(
        df_filtros, hoje, status=["Pendente"], prioridades=["Alta"], responsaveis=["Ana"]
    )
    assert list(resultado["id"]) == [1]


def test_filtros_sem_correspondencia_devolvem_vazio(df_filtros, hoje):
    resultado = analytics.filtrar_demandas(
        df_filtros, hoje, status=["Concluída"], prioridades=["Baixa"]
    )
    assert resultado.empty


def test_sem_filtros_devolve_tudo(df_filtros, hoje):
    resultado = analytics.filtrar_demandas(
        df_filtros, hoje, busca="  ", responsaveis=[], setores=[], status=None
    )
    assert len(resultado) == len(df_filtros)


def test_busca_ignora_maiusculas_e_acentos(df_filtros, hoje):
    resultado = analytics.filtrar_demandas(df_filtros, hoje, busca="RELATORIO")
    assert list(resultado["id"]) == [1]


def test_filtra_por_setor_e_situacao_do_prazo(df_filtros, hoje):
    por_setor = analytics.filtrar_demandas(df_filtros, hoje, setores=["TI"])
    assert list(por_setor["id"]) == [1, 3]
    atrasadas = analytics.filtrar_demandas(df_filtros, hoje, situacoes=["Atrasada"])
    assert list(atrasadas["id"]) == [1]


def test_filtra_por_periodo_do_prazo(df_filtros, hoje):
    resultado = analytics.filtrar_demandas(
        df_filtros,
        hoje,
        campo_periodo="prazo",
        inicio=date(2026, 10, 15),
        fim=date(2026, 11, 30),
    )
    assert list(resultado["id"]) == [2, 3]


def test_padronizar_converte_datas(criar_df):
    df = criar_df([{"prazo": "2026-10-30"}])
    assert pd.api.types.is_datetime64_any_dtype(df["prazo"])
