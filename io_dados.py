"""Importação e exportação de demandas (CSV e Excel).

Fluxo da importação, em três passos separados (cada um pode ser testado sozinho):
1. `ler_arquivo`        -> lê o arquivo e devolve um DataFrame de textos;
2. `validar_importacao` -> confere colunas e valida linha a linha;
3. `database.importar_demandas` -> grava as linhas válidas, ignorando duplicatas.
"""

import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from analytics import classificar_situacao_prazo
from constantes import COLUNAS_DATA, COLUNAS_DEMANDA, ROTULOS_COLUNAS
from validacao import ErroValidacao, normalizar_texto, valor_vazio, validar_demanda

COLUNAS_OBRIGATORIAS = ["titulo", "responsavel", "setor", "prioridade", "status", "prazo"]
COLUNAS_OPCIONAIS = ["descricao", "data_criacao", "data_conclusao"]
COLUNAS_CONHECIDAS = COLUNAS_OBRIGATORIAS + COLUNAS_OPCIONAIS

# Nomes alternativos aceitos (inclusive os rótulos dos arquivos exportados, para
# que um arquivo exportado possa ser importado de volta).
APELIDOS_COLUNAS = {
    "data_de_criacao": "data_criacao",
    "data_de_conclusao": "data_conclusao",
    "prazo_de_conclusao": "prazo",
}


class ErroImportacao(Exception):
    """Problema que impede a importação do arquivo inteiro (formato, colunas...)."""


@dataclass
class ResultadoImportacao:
    validas: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    ignoradas: list = field(default_factory=list)
    total_linhas: int = 0


# --- Leitura -------------------------------------------------------------------
def _decodificar(conteudo):
    """Tenta UTF-8 (com ou sem BOM) e, se falhar, o padrão do Excel no Windows."""
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise ErroImportacao("Não foi possível ler os caracteres do arquivo. Salve-o como UTF-8.")


def ler_arquivo(arquivo, nome=None):
    """Lê um CSV ou XLSX (caminho, bytes ou arquivo enviado pelo Streamlit).

    Todas as células são lidas como texto; a conversão e a validação dos tipos
    acontecem em `validar_importacao`, com mensagens por linha.
    """
    if isinstance(arquivo, (bytes, bytearray)):
        conteudo = bytes(arquivo)
    elif hasattr(arquivo, "getvalue"):  # UploadedFile do Streamlit
        conteudo = arquivo.getvalue()
        nome = nome or getattr(arquivo, "name", None)
    elif hasattr(arquivo, "read"):
        arquivo.seek(0)
        conteudo = arquivo.read()
        nome = nome or getattr(arquivo, "name", None)
    else:
        caminho = Path(arquivo)
        conteudo = caminho.read_bytes()
        nome = nome or caminho.name

    nome = (nome or "").lower()
    if not conteudo.strip():
        raise ErroImportacao("O arquivo está vazio.")

    try:
        if nome.endswith(".csv"):
            texto = _decodificar(conteudo)
            primeira_linha = texto.splitlines()[0]
            separador = max([";", ",", "\t"], key=primeira_linha.count)
            tabela = pd.read_csv(
                io.StringIO(texto), sep=separador, dtype=str, keep_default_na=False
            )
        elif nome.endswith((".xlsx", ".xlsm")):
            tabela = pd.read_excel(
                io.BytesIO(conteudo), dtype=str, keep_default_na=False, engine="openpyxl"
            )
        else:
            raise ErroImportacao("Formato não suportado. Envie um arquivo .csv ou .xlsx.")
    except ErroImportacao:
        raise
    except Exception as exc:  # arquivo corrompido pode gerar vários tipos de erro
        raise ErroImportacao(f"Não foi possível ler o arquivo: {exc}") from exc

    return tabela


# --- Validação -------------------------------------------------------------------
def normalizar_nome_coluna(nome):
    """'Data de criação' -> 'data_criacao'; 'Título ' -> 'titulo'."""
    base = normalizar_texto(nome).replace(" ", "_")
    return APELIDOS_COLUNAS.get(base, base)


def validar_importacao(tabela, hoje=None):
    """Valida o DataFrame lido. Levanta ErroImportacao se faltarem colunas
    obrigatórias; erros em linhas específicas vão para `resultado.erros`."""
    tabela = tabela.rename(columns={c: normalizar_nome_coluna(c) for c in tabela.columns})

    faltantes = [c for c in COLUNAS_OBRIGATORIAS if c not in tabela.columns]
    if faltantes:
        raise ErroImportacao(
            "Colunas obrigatórias ausentes: "
            + ", ".join(faltantes)
            + ". Colunas encontradas: "
            + (", ".join(map(str, tabela.columns)) or "nenhuma")
            + "."
        )

    resultado = ResultadoImportacao(
        ignoradas=[c for c in tabela.columns if c not in COLUNAS_CONHECIDAS]
    )

    for posicao, (_, linha) in enumerate(tabela.iterrows()):
        if all(valor_vazio(valor) for valor in linha.values):
            continue  # linha totalmente em branco
        resultado.total_linhas += 1
        numero_linha = posicao + 2  # +1 do cabeçalho, +1 porque a contagem começa em 1
        try:
            resultado.validas.append(validar_demanda(linha.to_dict(), hoje))
        except ErroValidacao as exc:
            resultado.erros.extend(f"Linha {numero_linha}: {erro}" for erro in exc.erros)

    return resultado


# --- Exportação ------------------------------------------------------------------
def tabela_legivel(df, hoje):
    """Cópia do DataFrame pronta para exibir/exportar: colunas com nomes claros,
    datas em DD/MM/AAAA e a coluna calculada 'Situação do prazo'."""
    saida = df.copy()
    saida["situacao_prazo"] = classificar_situacao_prazo(df, hoje)
    for coluna in COLUNAS_DATA:
        saida[coluna] = saida[coluna].dt.strftime("%d/%m/%Y").fillna("")
    saida = saida[COLUNAS_DEMANDA + ["situacao_prazo"]]
    return saida.rename(columns=ROTULOS_COLUNAS)


def exportar_csv(df, hoje):
    """CSV com ';' e UTF-8 com BOM: abre corretamente no Excel em português."""
    texto = tabela_legivel(df, hoje).to_csv(index=False, sep=";")
    return texto.encode("utf-8-sig")


def exportar_excel(df, hoje):
    """Arquivo .xlsx (bytes) com cabeçalho congelado e colunas ajustadas."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        tabela_legivel(df, hoje).to_excel(escritor, sheet_name="Demandas", index=False)
        planilha = escritor.sheets["Demandas"]
        planilha.freeze_panes = "A2"
        for coluna in planilha.columns:
            maior = max(len(str(celula.value or "")) for celula in coluna)
            planilha.column_dimensions[coluna[0].column_letter].width = min(maior + 2, 60)
    return buffer.getvalue()


def modelo_csv():
    """CSV de exemplo com o cabeçalho esperado, para o usuário preencher."""
    cabecalho = ",".join(COLUNAS_OBRIGATORIAS[:1] + ["descricao"] + COLUNAS_OBRIGATORIAS[1:])
    exemplo = "Enviar relatório mensal,Resumo das atividades do mês,Ana Souza,Operações,Média,Pendente,2026-12-15"
    return f"{cabecalho}\n{exemplo}\n".encode("utf-8")
