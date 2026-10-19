"""Testes de importação e exportação (io_dados.py)."""

from pathlib import Path

import pytest

import database
import io_dados

CABECALHO = "titulo,descricao,responsavel,setor,prioridade,status,prazo\n"


def _csv(tmp_path, conteudo, nome="demandas.csv", codificacao="utf-8"):
    caminho = tmp_path / nome
    caminho.write_bytes(conteudo.encode(codificacao))
    return caminho


def test_importa_csv_valido(tmp_path, hoje):
    caminho = _csv(
        tmp_path,
        CABECALHO + "Enviar relatório,Mensal,Ana,TI,media,pendente,2026-11-01\n"
        "Revisar contrato,,Bia,Jurídico,Alta,Em andamento,15/11/2026\n",
    )
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert resultado.total_linhas == 2
    assert resultado.erros == []
    assert resultado.validas[0]["prioridade"] == "Média"
    assert resultado.validas[1]["prazo"].isoformat() == "2026-11-15"


def test_colunas_obrigatorias_ausentes(tmp_path, hoje):
    caminho = _csv(tmp_path, "titulo,responsavel\nAlgo,Ana\n")
    with pytest.raises(io_dados.ErroImportacao) as exc:
        io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    mensagem = str(exc.value)
    assert "setor" in mensagem and "prazo" in mensagem


def test_erros_apontam_a_linha_do_arquivo(tmp_path, hoje):
    caminho = _csv(
        tmp_path,
        CABECALHO
        + "Boa,,Ana,TI,Alta,Pendente,2026-11-01\n"  # linha 2: ok
        + ",,Ana,TI,Alta,Pendente,2026-11-01\n"  # linha 3: título vazio
        + "Ruim,,Ana,TI,Urgente,Pendente,2026-11-01\n"  # linha 4: prioridade inválida
        + "Data,,Ana,TI,Alta,Pendente,31/02/2026\n",  # linha 5: data inválida
    )
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert len(resultado.validas) == 1
    texto = " | ".join(resultado.erros)
    assert "Linha 3" in texto and "Linha 4" in texto and "Linha 5" in texto


def test_linhas_em_branco_sao_ignoradas(tmp_path, hoje):
    caminho = _csv(tmp_path, CABECALHO + "A,,Ana,TI,Alta,Pendente,2026-11-01\n,,,,,,\n")
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert resultado.total_linhas == 1 and resultado.erros == []


def test_aceita_ponto_e_virgula_e_latin1(tmp_path, hoje):
    conteudo = "Título;Responsável;Setor;Prioridade;Status;Prazo\nDefinir orçamento;Ana;Finanças;Alta;Pendente;01/12/2026\n"
    caminho = _csv(tmp_path, conteudo, codificacao="cp1252")
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert resultado.erros == []
    assert resultado.validas[0]["titulo"] == "Definir orçamento"


def test_colunas_extras_sao_ignoradas_e_informadas(tmp_path, hoje):
    caminho = _csv(tmp_path, CABECALHO.strip() + ",observacao\nA,,Ana,TI,Alta,Pendente,2026-11-01,x\n")
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert resultado.ignoradas == ["observacao"]
    assert len(resultado.validas) == 1


def test_formatos_nao_suportados_e_arquivo_vazio(tmp_path):
    with pytest.raises(io_dados.ErroImportacao):
        io_dados.ler_arquivo(_csv(tmp_path, "abc", nome="dados.txt"))
    with pytest.raises(io_dados.ErroImportacao):
        io_dados.ler_arquivo(_csv(tmp_path, "", nome="vazio.csv"))
    with pytest.raises(io_dados.ErroImportacao):
        io_dados.ler_arquivo(b"isto nao e um excel", nome="quebrado.xlsx")


def test_exportar_csv_tem_nomes_claros_e_datas_legiveis(criar_df, hoje):
    df = criar_df([{"titulo": "Teste", "prazo": "2026-10-30"}])
    texto = io_dados.exportar_csv(df, hoje).decode("utf-8-sig")
    cabecalho = texto.splitlines()[0]
    assert "Título" in cabecalho and "Data de criação" in cabecalho and "Situação do prazo" in cabecalho
    assert "30/10/2026" in texto


def test_exportacao_csv_pode_ser_importada_de_volta(criar_df, hoje, tmp_path):
    df = criar_df(
        [
            {"titulo": "Com acento: ação", "prazo": "2026-10-30"},
            {"titulo": "Outra", "status": "Concluída", "data_conclusao": "2026-10-05"},
        ]
    )
    caminho = tmp_path / "exportado.csv"
    caminho.write_bytes(io_dados.exportar_csv(df, hoje))
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert resultado.erros == []
    assert [d["titulo"] for d in resultado.validas] == ["Com acento: ação", "Outra"]
    assert resultado.validas[1]["data_conclusao"].isoformat() == "2026-10-05"


def test_exportacao_excel_pode_ser_importada_de_volta(criar_df, hoje):
    df = criar_df([{"titulo": "Linha Excel"}])
    conteudo = io_dados.exportar_excel(df, hoje)
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(conteudo, nome="saida.xlsx"), hoje)
    assert resultado.erros == []
    assert resultado.validas[0]["titulo"] == "Linha Excel"


def test_arquivo_de_exemplo_do_projeto_e_totalmente_valido(hoje):
    caminho = Path(database.PASTA_DADOS) / "exemplo_demandas.csv"
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert resultado.erros == []
    assert len(resultado.validas) == 24


def test_modelo_csv_e_importavel(tmp_path, hoje):
    caminho = tmp_path / "modelo.csv"
    caminho.write_bytes(io_dados.modelo_csv())
    resultado = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje)
    assert resultado.erros == [] and len(resultado.validas) == 1


def test_importacao_completa_nao_duplica_ao_repetir(tmp_path, hoje, caminho_banco):
    caminho = Path(database.PASTA_DADOS) / "exemplo_demandas.csv"
    validas = io_dados.validar_importacao(io_dados.ler_arquivo(caminho), hoje).validas
    assert database.importar_demandas(validas, caminho_banco, hoje) == {"inseridas": 24, "duplicadas": 0}
    assert database.importar_demandas(validas, caminho_banco, hoje) == {"inseridas": 0, "duplicadas": 24}
