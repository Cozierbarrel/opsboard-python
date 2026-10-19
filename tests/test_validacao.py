"""Testes das regras de validação (validacao.py)."""

from datetime import date

import pandas as pd
import pytest

from validacao import (
    ErroValidacao,
    converter_data,
    gerar_chave_unica,
    normalizar_texto,
    validar_demanda,
)


def test_demanda_valida_e_normalizada(dados_validos, hoje):
    dados_validos.update(titulo="  Enviar   relatório  ", prioridade="alta", status="em ANDAMENTO")
    resultado = validar_demanda(dados_validos, hoje)
    assert resultado["titulo"] == "Enviar relatório"
    assert resultado["prioridade"] == "Alta"
    assert resultado["status"] == "Em andamento"
    assert resultado["data_conclusao"] is None


@pytest.mark.parametrize("titulo", ["", "   ", None])
def test_titulo_vazio_e_rejeitado(dados_validos, hoje, titulo):
    dados_validos["titulo"] = titulo
    with pytest.raises(ErroValidacao) as exc:
        validar_demanda(dados_validos, hoje)
    assert any("título" in erro for erro in exc.value.erros)


def test_titulo_muito_longo_e_rejeitado(dados_validos, hoje):
    dados_validos["titulo"] = "x" * 121
    with pytest.raises(ErroValidacao):
        validar_demanda(dados_validos, hoje)


def test_prazo_anterior_a_criacao_e_rejeitado(dados_validos, hoje):
    dados_validos.update(data_criacao=date(2026, 10, 10), prazo=date(2026, 10, 9))
    with pytest.raises(ErroValidacao) as exc:
        validar_demanda(dados_validos, hoje)
    assert any("anterior à data de criação" in erro for erro in exc.value.erros)


def test_prazo_igual_a_criacao_e_aceito(dados_validos, hoje):
    dados_validos.update(data_criacao=date(2026, 10, 10), prazo=date(2026, 10, 10))
    assert validar_demanda(dados_validos, hoje)["prazo"] == date(2026, 10, 10)


def test_prazo_obrigatorio(dados_validos, hoje):
    dados_validos["prazo"] = None
    with pytest.raises(ErroValidacao) as exc:
        validar_demanda(dados_validos, hoje)
    assert any("prazo é obrigatório" in erro for erro in exc.value.erros)


@pytest.mark.parametrize("campo, valor", [("prioridade", "urgente"), ("status", "cancelada")])
def test_opcoes_invalidas_sao_rejeitadas(dados_validos, hoje, campo, valor):
    dados_validos[campo] = valor
    with pytest.raises(ErroValidacao):
        validar_demanda(dados_validos, hoje)


def test_varios_erros_sao_reportados_juntos(hoje):
    with pytest.raises(ErroValidacao) as exc:
        validar_demanda({"titulo": "", "prioridade": "x", "status": "y"}, hoje)
    assert len(exc.value.erros) >= 5  # título, responsável, setor, prioridade, status, prazo


def test_data_de_criacao_padrao_e_hoje(dados_validos, hoje):
    dados_validos.pop("data_criacao")
    assert validar_demanda(dados_validos, hoje)["data_criacao"] == hoje


def test_conclusao_automatica_apenas_quando_concluida(dados_validos, hoje):
    dados_validos["status"] = "Concluída"
    assert validar_demanda(dados_validos, hoje)["data_conclusao"] == hoje
    dados_validos.update(status="Pendente", data_conclusao=date(2026, 10, 5))
    assert validar_demanda(dados_validos, hoje)["data_conclusao"] is None


def test_conclusao_anterior_a_criacao_e_rejeitada(dados_validos, hoje):
    dados_validos.update(status="Concluída", data_conclusao=date(2026, 9, 1))
    with pytest.raises(ErroValidacao):
        validar_demanda(dados_validos, hoje)


@pytest.mark.parametrize(
    "valor",
    ["2026-10-18", "18/10/2026", "2026-10-18 00:00:00", date(2026, 10, 18), pd.Timestamp("2026-10-18")],
)
def test_converter_data_aceita_varios_formatos(valor):
    assert converter_data(valor) == date(2026, 10, 18)


def test_converter_data_vazia_e_invalida():
    assert converter_data("") is None
    assert converter_data(None) is None
    with pytest.raises(ValueError):
        converter_data("31/02/2026")


def test_data_invalida_gera_erro_de_validacao(dados_validos, hoje):
    dados_validos["prazo"] = "amanhã"
    with pytest.raises(ErroValidacao) as exc:
        validar_demanda(dados_validos, hoje)
    assert any("Prazo" in erro for erro in exc.value.erros)


def test_normalizar_texto():
    assert normalizar_texto("  MÉDIA  ") == "media"
    assert normalizar_texto(None) == ""


def test_chave_unica_ignora_acentos_e_caixa(dados_validos, hoje):
    a = validar_demanda(dados_validos, hoje)
    dados_validos.update(titulo="ENVIAR RELATORIO", responsavel="ana souza")
    b = validar_demanda(dados_validos, hoje)
    assert gerar_chave_unica(a) == gerar_chave_unica(b)
