"""Testes da persistência em SQLite (database.py). Cada teste usa um banco temporário."""

import sqlite3
from datetime import date

import pytest

import database
from validacao import ErroValidacao


def test_init_db_cria_tabela_e_nao_apaga_dados(caminho_banco, dados_validos, hoje):
    database.criar_demanda(dados_validos, caminho_banco, hoje)
    database.init_db(caminho_banco)  # segunda inicialização (ex.: app reiniciado)
    assert len(database.listar_demandas(caminho_banco)) == 1


def test_listar_banco_vazio_devolve_dataframe_com_colunas(caminho_banco):
    df = database.listar_demandas(caminho_banco)
    assert df.empty
    assert "prazo" in df.columns


def test_criar_e_buscar_demanda(caminho_banco, dados_validos, hoje):
    novo_id = database.criar_demanda(dados_validos, caminho_banco, hoje)
    demanda = database.buscar_demanda(novo_id, caminho_banco)
    assert demanda["titulo"] == "Enviar relatório"
    assert demanda["prazo"] == date(2026, 10, 30)
    assert demanda["data_conclusao"] is None


def test_dados_persistem_apos_reabrir_o_banco(tmp_path, dados_validos, hoje):
    caminho = tmp_path / "persistente.db"
    database.init_db(caminho)
    database.criar_demanda(dados_validos, caminho, hoje)
    # Uma nova chamada abre uma nova conexão, como se o app tivesse sido reiniciado.
    assert database.listar_demandas(caminho)["titulo"].tolist() == ["Enviar relatório"]


def test_criar_com_dados_invalidos_nao_grava(caminho_banco, dados_validos, hoje):
    dados_validos["titulo"] = "   "
    with pytest.raises(ErroValidacao):
        database.criar_demanda(dados_validos, caminho_banco, hoje)
    assert database.listar_demandas(caminho_banco).empty


def test_demanda_duplicada_e_bloqueada(caminho_banco, dados_validos, hoje):
    database.criar_demanda(dados_validos, caminho_banco, hoje)
    dados_validos["titulo"] = "ENVIAR RELATORIO"  # mesma demanda, outra grafia
    with pytest.raises(database.DemandaDuplicada):
        database.criar_demanda(dados_validos, caminho_banco, hoje)
    assert len(database.listar_demandas(caminho_banco)) == 1


def test_atualizar_demanda(caminho_banco, dados_validos, hoje):
    novo_id = database.criar_demanda(dados_validos, caminho_banco, hoje)
    dados_validos.update(titulo="Novo título", prioridade="Baixa")
    database.atualizar_demanda(novo_id, dados_validos, caminho_banco, hoje)
    demanda = database.buscar_demanda(novo_id, caminho_banco)
    assert demanda["titulo"] == "Novo título"
    assert demanda["prioridade"] == "Baixa"


def test_concluir_define_data_e_reabrir_limpa(caminho_banco, dados_validos, hoje):
    novo_id = database.criar_demanda(dados_validos, caminho_banco, hoje)
    dados_validos["status"] = "Concluída"
    database.atualizar_demanda(novo_id, dados_validos, caminho_banco, hoje)
    assert database.buscar_demanda(novo_id, caminho_banco)["data_conclusao"] == hoje
    dados_validos["status"] = "Em andamento"
    database.atualizar_demanda(novo_id, dados_validos, caminho_banco, hoje)
    assert database.buscar_demanda(novo_id, caminho_banco)["data_conclusao"] is None


def test_atualizar_demanda_inexistente(caminho_banco, dados_validos, hoje):
    with pytest.raises(database.DemandaNaoEncontrada):
        database.atualizar_demanda(999, dados_validos, caminho_banco, hoje)


def test_atualizar_para_duplicar_outra_e_bloqueado(caminho_banco, dados_validos, hoje):
    database.criar_demanda(dados_validos, caminho_banco, hoje)
    outra = {**dados_validos, "titulo": "Outra demanda"}
    outro_id = database.criar_demanda(outra, caminho_banco, hoje)
    with pytest.raises(database.DemandaDuplicada):
        database.atualizar_demanda(outro_id, dados_validos, caminho_banco, hoje)


def test_excluir_demanda(caminho_banco, dados_validos, hoje):
    novo_id = database.criar_demanda(dados_validos, caminho_banco, hoje)
    assert database.excluir_demanda(novo_id, caminho_banco) is True
    assert database.excluir_demanda(novo_id, caminho_banco) is False  # já não existe
    assert database.listar_demandas(caminho_banco).empty


def test_texto_malicioso_e_gravado_como_dado(caminho_banco, dados_validos, hoje):
    """Consultas parametrizadas: o 'código SQL' digitado vira apenas texto."""
    dados_validos["titulo"] = "x'); DROP TABLE demandas; --"
    database.criar_demanda(dados_validos, caminho_banco, hoje)
    df = database.listar_demandas(caminho_banco)  # a tabela continua existindo
    assert df["titulo"].tolist() == ["x'); DROP TABLE demandas; --"]


def test_banco_rejeita_status_invalido_mesmo_sem_validacao(caminho_banco):
    """As restrições CHECK do banco são uma segunda linha de defesa."""
    with pytest.raises(sqlite3.IntegrityError):
        with database.conexao(caminho_banco) as con:
            con.execute(
                "INSERT INTO demandas (titulo, responsavel, setor, prioridade, status,"
                " data_criacao, prazo, chave_unica) VALUES ('a','b','c','Alta','Inventado',"
                " '2026-01-01', '2026-01-02', 'k')"
            )


def test_importar_demandas_ignora_duplicadas(caminho_banco, dados_validos, hoje):
    outra = {**dados_validos, "titulo": "Outra"}
    resumo = database.importar_demandas([dados_validos, outra, dados_validos], caminho_banco, hoje)
    assert resumo == {"inseridas": 2, "duplicadas": 1}
    resumo = database.importar_demandas([dados_validos], caminho_banco, hoje)
    assert resumo == {"inseridas": 0, "duplicadas": 1}
