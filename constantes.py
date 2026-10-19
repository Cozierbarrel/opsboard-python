"""Constantes compartilhadas por todos os módulos do OpsBoard.

Manter os valores "fixos" (status, prioridades, cores, nomes de colunas) em um só
lugar evita erros de digitação e facilita mudanças futuras: se amanhã surgir o
status "Cancelada", basta alterar este arquivo.
"""

# --- Valores permitidos -------------------------------------------------------
PRIORIDADES = ["Baixa", "Média", "Alta"]
PRIORIDADE_ALTA = "Alta"

STATUS_PENDENTE = "Pendente"
STATUS_EM_ANDAMENTO = "Em andamento"
STATUS_CONCLUIDA = "Concluída"
STATUS = [STATUS_PENDENTE, STATUS_EM_ANDAMENTO, STATUS_CONCLUIDA]

# Situação do prazo é calculada (não é gravada no banco): depende da data de hoje.
SITUACOES_PRAZO = ["No prazo", "Vence em breve", "Atrasada", "Concluída"]

# Quantos dias à frente uma demanda é considerada "com prazo próximo".
DIAS_ALERTA_PRAZO = 3

# --- Limites de tamanho dos textos --------------------------------------------
TAMANHO_MAXIMO = {"titulo": 120, "descricao": 1000, "responsavel": 80, "setor": 60}

# --- Colunas ------------------------------------------------------------------
COLUNAS_DEMANDA = [
    "id",
    "titulo",
    "descricao",
    "responsavel",
    "setor",
    "prioridade",
    "status",
    "data_criacao",
    "prazo",
    "data_conclusao",
]
COLUNAS_DATA = ["data_criacao", "prazo", "data_conclusao"]

# Nomes amigáveis usados na tela e nos arquivos exportados.
ROTULOS_COLUNAS = {
    "id": "ID",
    "titulo": "Título",
    "descricao": "Descrição",
    "responsavel": "Responsável",
    "setor": "Setor",
    "prioridade": "Prioridade",
    "status": "Status",
    "data_criacao": "Data de criação",
    "prazo": "Prazo",
    "data_conclusao": "Data de conclusão",
    "situacao_prazo": "Situação do prazo",
}

# --- Cores (iguais em gráficos e tabelas, para a leitura ficar consistente) ----
COR_PRIORIDADE = {"Baixa": "#2E9E6A", "Média": "#D98E04", "Alta": "#E5484D"}
COR_STATUS = {"Pendente": "#6B7280", "Em andamento": "#3B82F6", "Concluída": "#2E9E6A"}
COR_SITUACAO = {
    "No prazo": "#64748B",
    "Vence em breve": "#D98E04",
    "Atrasada": "#E5484D",
    "Concluída": "#2E9E6A",
}
