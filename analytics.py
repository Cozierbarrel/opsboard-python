"""Cálculos e processamento dos indicadores do OpsBoard.

Todas as funções aqui são "puras": recebem um DataFrame (e a data de hoje) e
devolvem um resultado, sem acessar banco de dados nem Streamlit. Isso torna os
testes simples e garante que o dashboard use sempre as mesmas regras.

Definições usadas em todo o sistema:
- Concluída:       status == "Concluída". "Em andamento" NÃO é concluída.
- Atrasada:        prazo anterior a hoje E status diferente de "Concluída".
- Prazo próximo:   prazo entre hoje e hoje + 3 dias (inclusive) E não concluída.
- % de conclusão:  concluídas / total * 100 (0 quando não há demandas).
"""

from datetime import timedelta

import pandas as pd

from constantes import (
    COLUNAS_DATA,
    COLUNAS_DEMANDA,
    DIAS_ALERTA_PRAZO,
    PRIORIDADE_ALTA,
    STATUS_CONCLUIDA,
    STATUS_EM_ANDAMENTO,
    STATUS_PENDENTE,
)
from validacao import normalizar_texto


# --- Preparação ---------------------------------------------------------------
def padronizar_dataframe(df):
    """Garante todas as colunas esperadas e converte as datas para datetime.

    Funciona também com DataFrames vazios, o que evita erros no banco vazio.
    """
    df = df.copy()
    for coluna in COLUNAS_DEMANDA:
        if coluna not in df.columns:
            df[coluna] = pd.NA
    df = df[COLUNAS_DEMANDA].copy()
    for coluna in COLUNAS_DATA:
        df[coluna] = pd.to_datetime(df[coluna], errors="coerce")
    return df


# --- Máscaras booleanas (uma linha = True/False por demanda) --------------------
def mascara_concluidas(df):
    return df["status"] == STATUS_CONCLUIDA


def mascara_atrasadas(df, hoje):
    """Prazo já passou (antes de hoje) e a demanda não está concluída."""
    return (df["prazo"] < pd.Timestamp(hoje)) & ~mascara_concluidas(df)


def mascara_prazo_proximo(df, hoje, dias=DIAS_ALERTA_PRAZO):
    """Prazo de hoje até hoje + `dias` (inclusive) e não concluída."""
    inicio = pd.Timestamp(hoje)
    limite = inicio + timedelta(days=dias)
    return (df["prazo"] >= inicio) & (df["prazo"] <= limite) & ~mascara_concluidas(df)


def mascara_alta_prioridade_aberta(df):
    return (df["prioridade"] == PRIORIDADE_ALTA) & ~mascara_concluidas(df)


# --- Listas de demandas para os alertas -------------------------------------------
def demandas_atrasadas(df, hoje):
    return df[mascara_atrasadas(df, hoje)]


def demandas_prazo_proximo(df, hoje, dias=DIAS_ALERTA_PRAZO):
    return df[mascara_prazo_proximo(df, hoje, dias)]


def demandas_alta_prioridade_abertas(df):
    return df[mascara_alta_prioridade_aberta(df)]


def classificar_situacao_prazo(df, hoje):
    """Série com a situação de cada demanda: No prazo, Vence em breve, Atrasada
    ou Concluída. A ordem das atribuições importa: a última regra vence."""
    situacao = pd.Series("No prazo", index=df.index, dtype="object")
    situacao[mascara_prazo_proximo(df, hoje)] = "Vence em breve"
    situacao[mascara_atrasadas(df, hoje)] = "Atrasada"
    situacao[mascara_concluidas(df)] = "Concluída"
    return situacao


def dias_para_prazo(df, hoje):
    """Dias até o prazo (negativo = já venceu)."""
    return (df["prazo"] - pd.Timestamp(hoje)).dt.days


# --- Indicadores ---------------------------------------------------------------
def percentual_conclusao(concluidas, total):
    """Concluídas / total * 100. Sem demandas, devolve 0.0 (evita divisão por zero)."""
    if total == 0:
        return 0.0
    return concluidas / total * 100


def calcular_indicadores(df, hoje):
    """Indicadores do dashboard, calculados a partir dos dados recebidos."""
    total = len(df)
    concluidas = int(mascara_concluidas(df).sum())
    return {
        "total": total,
        "pendentes": int((df["status"] == STATUS_PENDENTE).sum()),
        "em_andamento": int((df["status"] == STATUS_EM_ANDAMENTO).sum()),
        "concluidas": concluidas,
        "atrasadas": int(mascara_atrasadas(df, hoje).sum()),
        "percentual_conclusao": percentual_conclusao(concluidas, total),
        "prazo_proximo": int(mascara_prazo_proximo(df, hoje).sum()),
        "alta_prioridade_abertas": int(mascara_alta_prioridade_aberta(df).sum()),
    }


def contagem_por(df, coluna, ordem=None):
    """Quantidade de demandas por valor de `coluna`.

    Se `ordem` for informada, todos os valores dela aparecem (inclusive com zero),
    na ordem dada — útil para status e prioridade.
    """
    contagem = df[coluna].value_counts()
    if ordem is not None:
        contagem = contagem.reindex(ordem, fill_value=0)
    contagem = contagem.rename_axis(coluna).reset_index(name="quantidade")
    contagem["quantidade"] = contagem["quantidade"].astype(int)
    return contagem


def desempenho_mensal(df):
    """Demandas criadas e concluídas por mês.

    - "criadas" usa a data de criação.
    - "concluidas" usa a data de conclusão (só demandas com status Concluída).
    Meses sem movimento entre o primeiro e o último também aparecem (com zero).
    """
    colunas = ["mes", "criadas", "concluidas"]
    criadas = df["data_criacao"].dropna().dt.to_period("M").value_counts()
    datas_conclusao = df.loc[mascara_concluidas(df), "data_conclusao"].dropna()
    concluidas = datas_conclusao.dt.to_period("M").value_counts()

    todos = list(criadas.index) + list(concluidas.index)
    if not todos:
        return pd.DataFrame(columns=colunas)

    meses = pd.period_range(min(todos), max(todos), freq="M")
    return pd.DataFrame(
        {
            "mes": [mes.strftime("%m/%Y") for mes in meses],
            "criadas": [int(criadas.get(mes, 0)) for mes in meses],
            "concluidas": [int(concluidas.get(mes, 0)) for mes in meses],
        }
    )[colunas]


def resumo_por_responsavel(df, hoje):
    """Tabela com total, concluídas, atrasadas e % de conclusão por responsável."""
    colunas = ["responsavel", "total", "concluidas", "atrasadas", "percentual_conclusao"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    auxiliar = df.assign(
        _concluida=mascara_concluidas(df), _atrasada=mascara_atrasadas(df, hoje)
    )
    resumo = (
        auxiliar.groupby("responsavel")
        .agg(
            total=("id", "size"),
            concluidas=("_concluida", "sum"),
            atrasadas=("_atrasada", "sum"),
        )
        .reset_index()
    )
    resumo["percentual_conclusao"] = resumo["concluidas"] / resumo["total"] * 100
    return resumo.sort_values(["total", "responsavel"], ascending=[False, True])[colunas]


# --- Filtros -------------------------------------------------------------------
def filtrar_demandas(
    df,
    hoje,
    busca="",
    responsaveis=None,
    setores=None,
    prioridades=None,
    status=None,
    situacoes=None,
    campo_periodo=None,
    inicio=None,
    fim=None,
):
    """Aplica todos os filtros em conjunto (E lógico).

    Listas vazias ou None significam "sem filtro". A busca ignora maiúsculas e
    acentos. `campo_periodo` pode ser "prazo" ou "data_criacao".
    """
    mascara = pd.Series(True, index=df.index)

    if busca and busca.strip():
        alvo = normalizar_texto(busca)
        titulos = df["titulo"].map(normalizar_texto).astype(str)
        mascara &= titulos.str.contains(alvo, regex=False)
    if responsaveis:
        mascara &= df["responsavel"].isin(responsaveis)
    if setores:
        mascara &= df["setor"].isin(setores)
    if prioridades:
        mascara &= df["prioridade"].isin(prioridades)
    if status:
        mascara &= df["status"].isin(status)
    if situacoes:
        mascara &= classificar_situacao_prazo(df, hoje).isin(situacoes)
    if campo_periodo in ("prazo", "data_criacao"):
        if inicio:
            mascara &= df[campo_periodo] >= pd.Timestamp(inicio)
        if fim:
            mascara &= df[campo_periodo] <= pd.Timestamp(fim)

    return df[mascara]
