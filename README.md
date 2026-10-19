# OpsBoard

Sistema de gestão de operações para pequenas equipes e empresas, com foco em **gerenciamento de demandas, acompanhamento de prazos e análise de indicadores**. Desenvolvido em Python com Streamlit, SQLite, Pandas e Plotly.

> Projeto de portfólio (MVP). Roda 100% local, sem contas, sem serviços externos e sem autenticação.

## Problema que o projeto resolve

Em equipes pequenas, as demandas costumam ficar espalhadas em planilhas, mensagens e anotações. Isso dificulta saber **o que está atrasado, quem é responsável por quê e como a equipe está evoluindo**. O OpsBoard centraliza as demandas em um banco de dados, destaca o que precisa de atenção e transforma os registros em indicadores e gráficos.

## Funcionalidades

- **Gerenciamento de demandas:** cadastrar, visualizar, editar e excluir, com validação de dados (título vazio, prazo anterior à criação, prioridade/status inválidos etc.).
- **Dashboard (Visão geral):** total, pendentes, em andamento, concluídas, atrasadas e percentual de conclusão; gráficos interativos por status, prioridade, setor e desempenho mensal.
- **Pesquisa e filtros combinados:** busca por título (ignora maiúsculas e acentos) e filtros por responsável, setor, prioridade, status, período (prazo ou data de criação) e situação do prazo, com botão para limpar tudo.
- **Importação:** arquivos CSV ou Excel (.xlsx) com validação de colunas, tipos e campos obrigatórios, mensagens de erro por linha e prevenção de duplicatas.
- **Exportação:** demandas filtradas em CSV ou Excel, com nomes de colunas claros e datas em DD/MM/AAAA.
- **Alertas de prazo:** demandas atrasadas, com prazo nos próximos 3 dias e de alta prioridade ainda não concluídas.
- **Dados persistentes** em SQLite, criados automaticamente na primeira execução.

## Tecnologias

| Tecnologia | Uso |
|---|---|
| Python 3.10+ | Linguagem principal |
| Streamlit | Interface web |
| SQLite (módulo `sqlite3`) | Banco de dados local e persistente |
| Pandas | Filtros, agregações e leitura/escrita de arquivos |
| Plotly | Gráficos interativos |
| openpyxl | Leitura e escrita de arquivos Excel |
| Pytest | Testes automatizados |

## Estrutura do projeto

```
opsboard-python/
├── app.py                  # Interface e navegação (Streamlit)
├── analytics.py            # Indicadores, regras de prazo e filtros (funções puras)
├── database.py             # Criação do banco e operações de persistência (SQLite)
├── validacao.py            # Regras de validação de uma demanda
├── io_dados.py             # Importação e exportação (CSV/Excel)
├── constantes.py           # Status, prioridades, cores e nomes de colunas
├── requirements.txt        # Dependências
├── pytest.ini              # Configuração do Pytest
├── .gitignore
├── .streamlit/config.toml  # Tema e configurações do Streamlit
├── data/
│   └── exemplo_demandas.csv   # Dados fictícios de demonstração
├── tests/
│   ├── conftest.py            # Fixtures (data fixa de teste, banco temporário)
│   ├── test_analytics.py      # Indicadores, atrasos, prazos e filtros
│   ├── test_validacao.py      # Validação de dados
│   ├── test_database.py       # CRUD, duplicatas, persistência, SQL injection
│   ├── test_io_dados.py       # Importação e exportação
│   └── test_app_smoke.py      # Abre todas as páginas do app sem erros
└── screenshots/            # Capturas de tela do sistema
```

**Por que os módulos extras?** `validacao.py` concentra a regra "o que é uma demanda válida?" para que formulário, banco e importação usem exatamente a mesma. `io_dados.py` isola a leitura/escrita de arquivos. `constantes.py` evita repetir textos e cores. Assim, `app.py` fica só com a interface.

## Requisitos

- Python 3.10 ou superior
- pip

## Instalação e execução

**Linux / macOS**

```bash
git clone https://github.com/SEU-USUARIO/opsboard-python.git
cd opsboard-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/SEU-USUARIO/opsboard-python.git
cd opsboard-python
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

O navegador abrirá em `http://localhost:8501`. O banco `data/opsboard.db` é criado automaticamente na primeira execução e **não é versionado**.

## Exemplos de utilização

1. Na **Visão geral** com o banco vazio, clique em **Carregar dados de demonstração** para importar `data/exemplo_demandas.csv`.
2. Em **Nova demanda**, preencha o formulário e clique em *Salvar demanda*.
3. Em **Demandas**, combine filtros, escolha uma demanda e use as abas *Editar* ou *Excluir*.
4. Em **Relatórios e dados**, use *Exportar* (respeita os filtros) e *Importar* (mostra a validação antes de gravar).
5. Em **Alertas de prazo**, veja o que está atrasado, vence em breve ou é de alta prioridade.

### Formato dos arquivos de importação

| Coluna | Obrigatória | Valores |
|---|---|---|
| `titulo` | sim | até 120 caracteres |
| `responsavel` | sim | texto |
| `setor` | sim | texto |
| `prioridade` | sim | Baixa, Média ou Alta (sem acento também é aceito) |
| `status` | sim | Pendente, Em andamento ou Concluída |
| `prazo` | sim | `AAAA-MM-DD` ou `DD/MM/AAAA` |
| `descricao` | não | texto |
| `data_criacao` | não | padrão: data da importação |
| `data_conclusao` | não | só vale para status Concluída; padrão: data da importação |

Arquivos exportados pelo próprio sistema (com colunas como "Título" e "Data de criação") também podem ser importados de volta. Demandas com o mesmo título, responsável e prazo (ignorando maiúsculas e acentos) são consideradas duplicadas e não são inseridas novamente.

## Indicadores

| Indicador | Definição |
|---|---|
| Total | Quantidade de demandas cadastradas |
| Pendentes / Em andamento / Concluídas | Quantidade por status |
| **Atrasadas** | Prazo **anterior a hoje** e status **diferente de Concluída** (demandas *em andamento* com prazo vencido são atrasadas) |
| **Prazo próximo** | Prazo entre hoje e hoje + 3 dias (inclusive) e não concluída |
| **Alta prioridade em aberto** | Prioridade Alta e status diferente de Concluída |
| **Percentual de conclusão** | Concluídas ÷ total × 100. Sem demandas, o resultado é 0% |
| Desempenho mensal | "Criadas" por mês de criação; "concluídas" por mês da data de conclusão |

Todos os valores são calculados a partir do banco de dados; nenhum número é fixo no código.

## Testes

```bash
pytest
```

A suíte cobre percentual de conclusão, demandas atrasadas e com prazo próximo, indicadores com banco vazio, filtros por status e prioridade, validação de dados inválidos, operações de banco (CRUD, duplicatas, persistência e SQL injection), importação/exportação e a abertura de todas as páginas do app. Os testes usam uma **data fixa** (`18/10/2026`) e bancos temporários, por isso o resultado não depende do dia em que são executados nem toca no banco real.

## Decisões técnicas

- **Funções puras em `analytics.py`:** recebem o DataFrame e a data de hoje; por isso são fáceis de testar.
- **Consultas parametrizadas (`?`)** em todo o `database.py`, evitando SQL injection.
- **Chave de unicidade no banco** (título + responsável + prazo normalizados): duplicatas são barradas mesmo com cliques repetidos.
- **Restrições `CHECK`** no SQLite como segunda linha de defesa para status e prioridade.
- **Estado do Streamlit:** o app roda de novo a cada interação. Mensagens e navegação ficam em `st.session_state`, e o formulário de cadastro troca de chave após cada sucesso para não repetir registros.
- **Campo extra `data_conclusao`:** necessário para calcular o desempenho mensal de conclusão.

## Limitações conhecidas

- Sem autenticação nem controle de acesso: qualquer pessoa com acesso ao app vê todos os dados.
- Banco local único (SQLite), sem edição simultânea por muitas pessoas.
- Importação aceita apenas `.csv` e `.xlsx`; demandas importadas como concluídas sem `data_conclusao` recebem a data da importação.
- A coluna "Situação do prazo" é calculada com a data do computador onde o app roda.
- Exclusão é permanente (não há lixeira nem histórico de alterações).
- Ainda não há capturas de tela automáticas; adicione as suas.

## Melhorias futuras

- Autenticação e perfis de usuário.
- Histórico de alterações e comentários por demanda.
- Notificações por e-mail para prazos próximos.
- Campos personalizados, anexos e subtarefas.
- Migração opcional para PostgreSQL e implantação na nuvem.
- Relatórios em PDF e gráficos de tendência por responsável.

## Autor

Caio Paixão · [LinkedIn](https://www.linkedin.com/in/caionpaix%C3%A3o) · [GitHub](https://github.com/Cozierbarrel)
