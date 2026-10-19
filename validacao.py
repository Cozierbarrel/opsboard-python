"""Validação e normalização dos dados de uma demanda.

Este módulo é usado em três lugares: pelo formulário, pelo banco de dados e pela
importação de arquivos. Assim a regra "o que é uma demanda válida?" existe em um
único lugar e nunca fica diferente entre as telas.
"""

import unicodedata
from datetime import date, datetime

import pandas as pd

from constantes import (
    PRIORIDADES,
    STATUS,
    STATUS_CONCLUIDA,
    TAMANHO_MAXIMO,
)

FORMATOS_DATA = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
)


class ErroValidacao(ValueError):
    """Erro com uma LISTA de mensagens, para mostrar todos os problemas de uma vez."""

    def __init__(self, erros):
        self.erros = list(erros)
        super().__init__("; ".join(self.erros))


def valor_vazio(valor):
    """True para None, NaN/NaT e textos vazios ou só com espaços."""
    if valor is None:
        return True
    try:
        if pd.isna(valor):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(valor, str) and not valor.strip()


def normalizar_texto(valor):
    """Minúsculas, sem acentos e sem espaços repetidos.

    Usado para comparar textos ("Média" == "media") e detectar duplicatas.
    """
    if valor_vazio(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().split())


def texto_limpo(valor, colapsar_espacos=True):
    """Converte para str e remove espaços extras. Valores vazios viram ''."""
    if valor_vazio(valor):
        return ""
    texto = str(valor).strip()
    return " ".join(texto.split()) if colapsar_espacos else texto


def converter_data(valor):
    """Converte texto, datetime ou date em `date`. Vazio vira None.

    Aceita 2026-10-18 e 18/10/2026. Levanta ValueError se não reconhecer a data.
    """
    if valor_vazio(valor):
        return None
    if isinstance(valor, datetime):  # inclui pd.Timestamp
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"data inválida '{texto}' (use AAAA-MM-DD ou DD/MM/AAAA)")


def normalizar_opcao(valor, opcoes):
    """Devolve a opção oficial equivalente ao valor ('media' -> 'Média') ou None."""
    mapa = {normalizar_texto(opcao): opcao for opcao in opcoes}
    return mapa.get(normalizar_texto(str(valor).replace("_", " ")))


def _ler_data(dados, campo, rotulo, erros):
    try:
        return converter_data(dados.get(campo))
    except ValueError as exc:
        erros.append(f"{rotulo}: {exc}.")
        return None


def _validar_texto(dados, campo, rotulo, erros, obrigatorio=True):
    texto = texto_limpo(dados.get(campo), colapsar_espacos=(campo != "descricao"))
    if obrigatorio and not texto:
        erros.append(f"{rotulo} é obrigatório.")
    elif len(texto) > TAMANHO_MAXIMO[campo]:
        erros.append(f"{rotulo} deve ter no máximo {TAMANHO_MAXIMO[campo]} caracteres.")
    return texto


def validar_demanda(dados, hoje=None):
    """Valida e limpa os dados de uma demanda.

    Recebe um dicionário e devolve outro, já normalizado (textos sem espaços
    extras, prioridade/status com a grafia oficial, datas como `date`).
    Se algo estiver errado, levanta ErroValidacao com todas as mensagens.

    `hoje` é usado só para valores padrão (data de criação e de conclusão) e
    existe como parâmetro para que os testes não dependam do relógio.
    """
    hoje = hoje or date.today()
    erros = []

    titulo = _validar_texto(dados, "titulo", "O título", erros)
    descricao = _validar_texto(dados, "descricao", "A descrição", erros, obrigatorio=False)
    responsavel = _validar_texto(dados, "responsavel", "O responsável", erros)
    setor = _validar_texto(dados, "setor", "O setor", erros)

    prioridade = normalizar_opcao(dados.get("prioridade"), PRIORIDADES)
    if prioridade is None:
        erros.append(f"Prioridade inválida: use {', '.join(PRIORIDADES)}.")

    status = normalizar_opcao(dados.get("status"), STATUS)
    if status is None:
        erros.append(f"Status inválido: use {', '.join(STATUS)}.")

    # Datas ---------------------------------------------------------------
    qtd = len(erros)
    data_criacao = _ler_data(dados, "data_criacao", "Data de criação", erros)
    if data_criacao is None and len(erros) == qtd:  # campo vazio (e não inválido)
        data_criacao = hoje

    qtd = len(erros)
    prazo = _ler_data(dados, "prazo", "Prazo", erros)
    if prazo is None and len(erros) == qtd:
        erros.append("O prazo é obrigatório.")

    if prazo and data_criacao and prazo < data_criacao:
        erros.append("O prazo não pode ser anterior à data de criação.")

    # A data de conclusão só existe para demandas concluídas.
    data_conclusao = None
    if status == STATUS_CONCLUIDA:
        qtd = len(erros)
        data_conclusao = _ler_data(dados, "data_conclusao", "Data de conclusão", erros)
        if data_conclusao is None and len(erros) == qtd:
            data_conclusao = max(hoje, data_criacao) if data_criacao else hoje
        if data_conclusao and data_criacao and data_conclusao < data_criacao:
            erros.append("A data de conclusão não pode ser anterior à data de criação.")

    if erros:
        raise ErroValidacao(erros)

    return {
        "titulo": titulo,
        "descricao": descricao,
        "responsavel": responsavel,
        "setor": setor,
        "prioridade": prioridade,
        "status": status,
        "data_criacao": data_criacao,
        "prazo": prazo,
        "data_conclusao": data_conclusao,
    }


def gerar_chave_unica(demanda):
    """Chave usada para impedir duplicatas: título + responsável + prazo.

    Dois cadastros com o mesmo título, responsável e prazo (ignorando maiúsculas,
    acentos e espaços extras) são considerados a mesma demanda.
    """
    return "|".join(
        [
            normalizar_texto(demanda["titulo"]),
            normalizar_texto(demanda["responsavel"]),
            demanda["prazo"].isoformat(),
        ]
    )
