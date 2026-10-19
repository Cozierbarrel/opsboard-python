"""Persistência em SQLite: criação do banco e operações de CRUD.

Pontos importantes para estudar:
- Todas as consultas usam parâmetros (`?`), nunca texto concatenado. Isso evita
  SQL injection: o valor digitado pelo usuário é tratado como dado, não como código.
- `init_db()` usa CREATE TABLE IF NOT EXISTS, então pode ser chamado a qualquer
  momento sem apagar dados existentes.
- Uma restrição UNIQUE na coluna `chave_unica` impede duplicatas no próprio banco,
  mesmo que a interface falhe em evitá-las (por exemplo, com cliques repetidos).
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pandas as pd

from analytics import padronizar_dataframe
from constantes import COLUNAS_DATA, COLUNAS_DEMANDA, PRIORIDADES, STATUS
from validacao import gerar_chave_unica, validar_demanda

RAIZ_PROJETO = Path(__file__).resolve().parent
PASTA_DADOS = RAIZ_PROJETO / "data"


class DemandaDuplicada(Exception):
    """Já existe uma demanda com o mesmo título, responsável e prazo."""


class DemandaNaoEncontrada(LookupError):
    """Não existe demanda com o ID informado."""


def caminho_padrao():
    """Caminho do banco. Pode ser trocado pela variável de ambiente OPSBOARD_DB
    (útil nos testes, para não mexer no banco real)."""
    return Path(os.environ.get("OPSBOARD_DB", PASTA_DADOS / "opsboard.db"))


def _lista_sql(valores):
    # Usada só com as constantes do projeto (nunca com dados do usuário).
    return ", ".join("'" + valor.replace("'", "''") + "'" for valor in valores)


SQL_CRIAR_TABELA = f"""
CREATE TABLE IF NOT EXISTS demandas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo         TEXT NOT NULL CHECK (length(trim(titulo)) > 0),
    descricao      TEXT NOT NULL DEFAULT '',
    responsavel    TEXT NOT NULL,
    setor          TEXT NOT NULL,
    prioridade     TEXT NOT NULL CHECK (prioridade IN ({_lista_sql(PRIORIDADES)})),
    status         TEXT NOT NULL CHECK (status IN ({_lista_sql(STATUS)})),
    data_criacao   TEXT NOT NULL,
    prazo          TEXT NOT NULL,
    data_conclusao TEXT,
    chave_unica    TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_demandas_status ON demandas (status);
CREATE INDEX IF NOT EXISTS idx_demandas_prazo ON demandas (prazo);
"""

SQL_INSERIR = """
INSERT INTO demandas
    (titulo, descricao, responsavel, setor, prioridade, status,
     data_criacao, prazo, data_conclusao, chave_unica)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SQL_ATUALIZAR = """
UPDATE demandas SET
    titulo = ?, descricao = ?, responsavel = ?, setor = ?, prioridade = ?,
    status = ?, data_criacao = ?, prazo = ?, data_conclusao = ?, chave_unica = ?
WHERE id = ?
"""


@contextmanager
def conexao(db_path=None):
    """Abre uma conexão, confirma (commit) no sucesso, desfaz (rollback) no erro
    e sempre fecha ao final."""
    caminho = Path(db_path) if db_path else caminho_padrao()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db(db_path=None):
    """Cria o banco e as tabelas, se ainda não existirem. Nunca apaga dados."""
    with conexao(db_path) as con:
        con.executescript(SQL_CRIAR_TABELA)


def _valores(demanda):
    """Converte a demanda validada na tupla de valores esperada pelo SQL."""
    conclusao = demanda["data_conclusao"]
    return (
        demanda["titulo"],
        demanda["descricao"],
        demanda["responsavel"],
        demanda["setor"],
        demanda["prioridade"],
        demanda["status"],
        demanda["data_criacao"].isoformat(),
        demanda["prazo"].isoformat(),
        conclusao.isoformat() if conclusao else None,
        gerar_chave_unica(demanda),
    )


def _violacao_de_unicidade(erro):
    return "UNIQUE" in str(erro).upper()


def criar_demanda(dados, db_path=None, hoje=None):
    """Valida e grava uma nova demanda. Devolve o ID criado.

    Levanta ErroValidacao (dados inválidos) ou DemandaDuplicada.
    """
    demanda = validar_demanda(dados, hoje)
    try:
        with conexao(db_path) as con:
            cursor = con.execute(SQL_INSERIR, _valores(demanda))
            return cursor.lastrowid
    except sqlite3.IntegrityError as erro:
        if _violacao_de_unicidade(erro):
            raise DemandaDuplicada(
                "Já existe uma demanda com o mesmo título, responsável e prazo."
            ) from erro
        raise


def atualizar_demanda(demanda_id, dados, db_path=None, hoje=None):
    """Valida e atualiza uma demanda existente.

    `dados` deve trazer todos os campos (inclusive `data_criacao`).
    Levanta ErroValidacao, DemandaDuplicada ou DemandaNaoEncontrada.
    """
    demanda = validar_demanda(dados, hoje)
    try:
        with conexao(db_path) as con:
            cursor = con.execute(SQL_ATUALIZAR, (*_valores(demanda), demanda_id))
            if cursor.rowcount == 0:
                raise DemandaNaoEncontrada(f"Demanda #{demanda_id} não encontrada.")
    except sqlite3.IntegrityError as erro:
        if _violacao_de_unicidade(erro):
            raise DemandaDuplicada(
                "Já existe outra demanda com o mesmo título, responsável e prazo."
            ) from erro
        raise


def excluir_demanda(demanda_id, db_path=None):
    """Exclui a demanda. Devolve True se existia e False se o ID não foi achado."""
    with conexao(db_path) as con:
        cursor = con.execute("DELETE FROM demandas WHERE id = ?", (demanda_id,))
        return cursor.rowcount > 0


def _linha_para_dict(linha):
    demanda = dict(linha)
    demanda.pop("chave_unica", None)
    for campo in COLUNAS_DATA:
        demanda[campo] = date.fromisoformat(demanda[campo]) if demanda[campo] else None
    return demanda


def buscar_demanda(demanda_id, db_path=None):
    """Devolve a demanda como dicionário (datas como `date`) ou None."""
    with conexao(db_path) as con:
        linha = con.execute(
            "SELECT * FROM demandas WHERE id = ?", (demanda_id,)
        ).fetchone()
    return _linha_para_dict(linha) if linha else None


def listar_demandas(db_path=None):
    """Todas as demandas em um DataFrame padronizado (vazio, se não houver)."""
    colunas_sql = ", ".join(COLUNAS_DEMANDA)  # constantes do projeto, não do usuário
    with conexao(db_path) as con:
        df = pd.read_sql_query(
            f"SELECT {colunas_sql} FROM demandas ORDER BY prazo, id", con
        )
    return padronizar_dataframe(df)


def importar_demandas(registros, db_path=None, hoje=None):
    """Insere várias demandas de uma vez, ignorando as que já existem.

    Tudo ocorre em uma única transação: se algo inesperado acontecer no meio,
    nada é gravado. Devolve {"inseridas": n, "duplicadas": m}.
    """
    inseridas = duplicadas = 0
    validadas = [validar_demanda(registro, hoje) for registro in registros]
    with conexao(db_path) as con:
        for demanda in validadas:
            try:
                con.execute(SQL_INSERIR, _valores(demanda))
                inseridas += 1
            except sqlite3.IntegrityError as erro:
                if not _violacao_de_unicidade(erro):
                    raise
                duplicadas += 1
    return {"inseridas": inseridas, "duplicadas": duplicadas}
