"""OpsBoard — interface web (Streamlit).

Este arquivo cuida apenas de apresentação e navegação. As regras ficam em:
- analytics.py  (indicadores, atrasos e filtros)
- validacao.py  (o que é uma demanda válida)
- database.py   (SQLite)
- io_dados.py   (CSV/Excel)

Lembrete importante: o Streamlit executa este arquivo inteiro, do começo ao fim,
a cada interação (clique, digitação...). Por isso:
- os dados são lidos do banco a cada execução (sempre atualizados);
- o que precisa "sobreviver" entre execuções fica em `st.session_state`;
- depois de gravar algo, usamos `st.rerun()` para redesenhar a tela com os novos
  dados e uma mensagem de confirmação (guardada em `st.session_state["flash"]`).
"""

import inspect
import sqlite3
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import analytics
import database
import io_dados
from constantes import (
    COR_PRIORIDADE,
    COR_SITUACAO,
    COR_STATUS,
    DIAS_ALERTA_PRAZO,
    PRIORIDADES,
    SITUACOES_PRAZO,
    STATUS,
    TAMANHO_MAXIMO,
)
from validacao import ErroValidacao

st.set_page_config(
    page_title="OpsBoard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGINAS = [
    "Visão geral",
    "Demandas",
    "Nova demanda",
    "Relatórios e dados",
    "Alertas de prazo",
]
SEM_PERIODO = "Sem filtro de período"
CAMPOS_PERIODO = {"Prazo": "prazo", "Data de criação": "data_criacao"}
CORES_TEXTO = {**COR_PRIORIDADE, **COR_STATUS, **COR_SITUACAO}
COLUNAS_COLORIDAS = ["Prioridade", "Status", "Situação do prazo"]
DATA_MINIMA, DATA_MAXIMA = date(2000, 1, 1), date(2100, 12, 31)

# Versões novas do Streamlit usam width="stretch"; as antigas, use_container_width.
if "width" in inspect.signature(st.plotly_chart).parameters:
    LARGURA_TOTAL = {"width": "stretch"}
else:  # pragma: no cover - depende da versão instalada
    LARGURA_TOTAL = {"use_container_width": True}

st.markdown(
    "<style>.block-container {padding-top: 2.5rem; max-width: 1400px;}</style>",
    unsafe_allow_html=True,
)


# =============================================================================
# Utilidades de interface
# =============================================================================
def avisar(tipo, texto):
    """Guarda uma mensagem para ser exibida na próxima execução da tela.

    `tipo` é o nome de uma função do Streamlit: success, warning, error ou info.
    """
    st.session_state["flash"] = (tipo, texto)


def exibir_aviso_pendente():
    aviso = st.session_state.pop("flash", None)
    if aviso:
        tipo, texto = aviso
        getattr(st, tipo)(texto)


def ir_para(pagina):
    """Callback de botão: muda a página selecionada no menu lateral."""
    st.session_state["pagina"] = pagina


def cartao(coluna, rotulo, valor, ajuda=None):
    with coluna:
        with st.container(border=True):
            st.metric(rotulo, valor, help=ajuda)


def mostrar_grafico(figura):
    figura.update_layout(margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
    st.plotly_chart(figura, **LARGURA_TOTAL)


def colorir_celula(valor):
    cor = CORES_TEXTO.get(valor)
    if not cor:
        return ""
    return f"background-color: {cor}26; color: {cor}; font-weight: 600"


def mostrar_tabela(tabela):
    """Exibe uma tabela legível, com cores consistentes para prioridade/status."""
    colunas = [c for c in COLUNAS_COLORIDAS if c in tabela.columns]
    estilo = tabela.style
    aplicar = getattr(estilo, "map", None) or estilo.applymap
    st.dataframe(aplicar(colorir_celula, subset=colunas), hide_index=True, **LARGURA_TOTAL)


def carregar_demonstracao(hoje):
    """Callback: importa data/exemplo_demandas.csv (dados fictícios)."""
    arquivo = database.PASTA_DADOS / "exemplo_demandas.csv"
    try:
        resultado = io_dados.validar_importacao(io_dados.ler_arquivo(arquivo), hoje)
        resumo = database.importar_demandas(resultado.validas, hoje=hoje)
    except (io_dados.ErroImportacao, OSError, sqlite3.Error) as exc:
        avisar("error", f"Não foi possível carregar os dados de demonstração: {exc}")
        return
    avisar("success", f"{resumo['inseridas']} demandas de demonstração carregadas.")


# =============================================================================
# Filtros (usados em "Demandas" e em "Relatórios e dados")
# =============================================================================
def _multiselect(rotulo, opcoes, chave):
    # Se uma opção escolhida deixou de existir (ex.: demanda excluída), remove-a
    # do estado antes de criar o widget; senão o Streamlit levantaria erro.
    if chave in st.session_state:
        st.session_state[chave] = [v for v in st.session_state[chave] if v in opcoes]
    return st.multiselect(rotulo, opcoes, key=chave, placeholder="Todos")


def limpar_filtros(prefixo):
    """Callback do botão 'Limpar filtros'."""
    for sufixo in ("resp", "setor", "prioridade", "status", "situacao"):
        st.session_state[f"{prefixo}_{sufixo}"] = []
    st.session_state[f"{prefixo}_busca"] = ""
    st.session_state[f"{prefixo}_campo"] = SEM_PERIODO
    st.session_state.pop(f"{prefixo}_inicio", None)
    st.session_state.pop(f"{prefixo}_fim", None)


def painel_filtros(df, hoje, prefixo):
    """Desenha os filtros e devolve o DataFrame já filtrado.

    `prefixo` dá chaves próprias a cada página, para os filtros de uma não
    interferirem nos da outra.
    """
    chave = lambda nome: f"{prefixo}_{nome}"  # noqa: E731
    with st.container(border=True):
        busca = st.text_input(
            "Buscar por título", key=chave("busca"), placeholder="Digite parte do título..."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            responsaveis = _multiselect(
                "Responsável", sorted(set(df["responsavel"].dropna())), chave("resp")
            )
        with c2:
            setores = _multiselect("Setor", sorted(set(df["setor"].dropna())), chave("setor"))
        with c3:
            prioridades = _multiselect("Prioridade", PRIORIDADES, chave("prioridade"))

        c4, c5, c6 = st.columns(3)
        with c4:
            status = _multiselect("Status", STATUS, chave("status"))
        with c5:
            situacoes = _multiselect("Situação do prazo", SITUACOES_PRAZO, chave("situacao"))
        with c6:
            campo = st.selectbox(
                "Período por", [SEM_PERIODO, *CAMPOS_PERIODO], key=chave("campo")
            )

        inicio = fim = None
        if campo != SEM_PERIODO:
            d1, d2 = st.columns(2)
            inicio = d1.date_input(
                "De",
                value=hoje - timedelta(days=30),
                min_value=DATA_MINIMA,
                max_value=DATA_MAXIMA,
                format="DD/MM/YYYY",
                key=chave("inicio"),
            )
            fim = d2.date_input(
                "Até",
                value=hoje + timedelta(days=30),
                min_value=DATA_MINIMA,
                max_value=DATA_MAXIMA,
                format="DD/MM/YYYY",
                key=chave("fim"),
            )
            if inicio > fim:
                st.warning("A data inicial é posterior à data final; nenhum resultado será exibido.")

        st.button("Limpar filtros", on_click=limpar_filtros, args=(prefixo,), key=chave("limpar"))

    return analytics.filtrar_demandas(
        df,
        hoje,
        busca=busca,
        responsaveis=responsaveis,
        setores=setores,
        prioridades=prioridades,
        status=status,
        situacoes=situacoes,
        campo_periodo=CAMPOS_PERIODO.get(campo),
        inicio=inicio,
        fim=fim,
    )


# =============================================================================
# Página: Visão geral
# =============================================================================
def pagina_visao_geral(df, hoje):
    st.title("Visão geral")
    st.caption("Indicadores calculados em tempo real a partir das demandas gravadas no banco.")

    if df.empty:
        st.info("Ainda não há demandas cadastradas. Cadastre a primeira ou carregue os dados de exemplo.")
        c1, c2, _ = st.columns([1, 1, 2])
        c1.button("Cadastrar demanda", on_click=ir_para, args=("Nova demanda",), type="primary")
        c2.button("Carregar dados de demonstração", on_click=carregar_demonstracao, args=(hoje,))
        return

    ind = analytics.calcular_indicadores(df, hoje)

    linha1 = st.columns(3)
    cartao(linha1[0], "Total de demandas", ind["total"])
    cartao(linha1[1], "Pendentes", ind["pendentes"])
    cartao(linha1[2], "Em andamento", ind["em_andamento"])
    linha2 = st.columns(3)
    cartao(linha2[0], "Concluídas", ind["concluidas"])
    cartao(
        linha2[1],
        "Atrasadas",
        ind["atrasadas"],
        "Prazo anterior a hoje e status diferente de Concluída.",
    )
    cartao(
        linha2[2],
        "Percentual de conclusão",
        f"{ind['percentual_conclusao']:.1f}%",
        "Concluídas ÷ total de demandas × 100.",
    )

    if ind["atrasadas"]:
        st.warning(
            f"Há {ind['atrasadas']} demanda(s) atrasada(s). Veja os detalhes em **Alertas de prazo**."
        )

    graf1, graf2 = st.columns(2)
    with graf1:
        por_status = analytics.contagem_por(df, "status", STATUS)
        figura = px.pie(
            por_status,
            names="status",
            values="quantidade",
            hole=0.55,
            color="status",
            color_discrete_map=COR_STATUS,
            title="Demandas por status",
        )
        figura.update_traces(sort=False)
        mostrar_grafico(figura)
    with graf2:
        por_prioridade = analytics.contagem_por(df, "prioridade", PRIORIDADES)
        figura = px.bar(
            por_prioridade,
            x="prioridade",
            y="quantidade",
            color="prioridade",
            color_discrete_map=COR_PRIORIDADE,
            text_auto=True,
            title="Demandas por prioridade",
            labels={"prioridade": "Prioridade", "quantidade": "Quantidade"},
        )
        figura.update_layout(showlegend=False)
        mostrar_grafico(figura)

    graf3, graf4 = st.columns(2)
    with graf3:
        por_setor = analytics.contagem_por(df, "setor")
        figura = px.bar(
            por_setor,
            x="quantidade",
            y="setor",
            orientation="h",
            text_auto=True,
            title="Demandas por setor",
            labels={"setor": "Setor", "quantidade": "Quantidade"},
        )
        figura.update_traces(marker_color="#3B82F6")
        figura.update_layout(yaxis={"categoryorder": "total ascending"})
        mostrar_grafico(figura)
    with graf4:
        mensal = analytics.desempenho_mensal(df)
        longo = mensal.melt(
            id_vars="mes",
            value_vars=["criadas", "concluidas"],
            var_name="indicador",
            value_name="quantidade",
        )
        longo["indicador"] = longo["indicador"].map(
            {"criadas": "Criadas", "concluidas": "Concluídas"}
        )
        figura = px.bar(
            longo,
            x="mes",
            y="quantidade",
            color="indicador",
            barmode="group",
            title="Desempenho mensal: criadas x concluídas",
            color_discrete_map={"Criadas": "#94A3B8", "Concluídas": "#2E9E6A"},
            labels={"mes": "Mês", "quantidade": "Quantidade"},
        )
        figura.update_xaxes(type="category")
        mostrar_grafico(figura)


# =============================================================================
# Página: Demandas (lista, filtros, edição e exclusão)
# =============================================================================
COLUNAS_LISTA = [
    "ID",
    "Título",
    "Responsável",
    "Setor",
    "Prioridade",
    "Status",
    "Data de criação",
    "Prazo",
    "Situação do prazo",
]


def formulario_edicao(demanda_id, hoje):
    demanda = database.buscar_demanda(demanda_id)
    if demanda is None:
        st.error("Esta demanda não existe mais.")
        return

    # A chave do formulário inclui o ID: ao trocar de demanda, os campos recarregam.
    with st.form(f"form_editar_{demanda_id}"):
        titulo = st.text_input("Título *", value=demanda["titulo"], max_chars=TAMANHO_MAXIMO["titulo"])
        descricao = st.text_area(
            "Descrição", value=demanda["descricao"], max_chars=TAMANHO_MAXIMO["descricao"]
        )
        c1, c2 = st.columns(2)
        responsavel = c1.text_input(
            "Responsável *", value=demanda["responsavel"], max_chars=TAMANHO_MAXIMO["responsavel"]
        )
        setor = c2.text_input("Setor *", value=demanda["setor"], max_chars=TAMANHO_MAXIMO["setor"])
        c3, c4 = st.columns(2)
        prioridade = c3.selectbox(
            "Prioridade", PRIORIDADES, index=PRIORIDADES.index(demanda["prioridade"])
        )
        status = c4.selectbox("Status", STATUS, index=STATUS.index(demanda["status"]))
        c5, c6 = st.columns(2)
        c5.date_input(
            "Data de criação", value=demanda["data_criacao"], disabled=True, format="DD/MM/YYYY"
        )
        prazo = c6.date_input(
            "Prazo de conclusão *",
            value=demanda["prazo"],
            min_value=DATA_MINIMA,
            max_value=DATA_MAXIMA,
            format="DD/MM/YYYY",
        )
        enviado = st.form_submit_button("Salvar alterações", type="primary")

    if not enviado:
        return

    dados = {
        "titulo": titulo,
        "descricao": descricao,
        "responsavel": responsavel,
        "setor": setor,
        "prioridade": prioridade,
        "status": status,
        "data_criacao": demanda["data_criacao"],
        "prazo": prazo,
        "data_conclusao": demanda["data_conclusao"],
    }
    try:
        database.atualizar_demanda(demanda_id, dados, hoje=hoje)
    except ErroValidacao as exc:
        for erro in exc.erros:
            st.error(erro)
    except database.DemandaDuplicada as exc:
        st.warning(str(exc))
    except database.DemandaNaoEncontrada as exc:
        st.error(str(exc))
    except sqlite3.Error as exc:
        st.error(f"Erro ao gravar no banco de dados: {exc}")
    else:
        avisar("success", f"Demanda #{demanda_id} atualizada com sucesso.")
        st.rerun()


def secao_exclusao(demanda_id):
    confirmar = st.checkbox(
        "Confirmo que desejo excluir esta demanda permanentemente.",
        key=f"confirmar_exclusao_{demanda_id}",
    )
    if st.button("Excluir demanda", disabled=not confirmar, key=f"excluir_{demanda_id}"):
        try:
            existia = database.excluir_demanda(demanda_id)
        except sqlite3.Error as exc:
            st.error(f"Erro ao excluir no banco de dados: {exc}")
            return
        if existia:
            avisar("success", f"Demanda #{demanda_id} excluída.")
        else:
            avisar("warning", f"A demanda #{demanda_id} já havia sido excluída.")
        st.rerun()


def pagina_demandas(df, hoje):
    st.title("Demandas")
    if df.empty:
        st.info("Nenhuma demanda cadastrada ainda.")
        st.button("Cadastrar demanda", on_click=ir_para, args=("Nova demanda",), type="primary")
        return

    filtrado = painel_filtros(df, hoje, "dem")
    st.caption(f"Exibindo {len(filtrado)} de {len(df)} demanda(s).")

    if filtrado.empty:
        st.warning("Nenhuma demanda encontrada com os filtros atuais.")
        return

    tabela = io_dados.tabela_legivel(filtrado, hoje)[COLUNAS_LISTA]
    mostrar_tabela(tabela)

    st.subheader("Editar ou excluir")
    ids = [int(i) for i in filtrado["id"]]
    if st.session_state.get("sel_demanda") not in ids:
        st.session_state.pop("sel_demanda", None)
    titulos = dict(zip(ids, filtrado["titulo"]))
    escolhido = st.selectbox(
        "Escolha a demanda", ids, format_func=lambda i: f"#{i} — {titulos[i]}", key="sel_demanda"
    )
    aba_editar, aba_excluir = st.tabs(["Editar", "Excluir"])
    with aba_editar:
        formulario_edicao(escolhido, hoje)
    with aba_excluir:
        secao_exclusao(escolhido)


# =============================================================================
# Página: Nova demanda
# =============================================================================
def pagina_nova_demanda(df, hoje):
    st.title("Nova demanda")
    st.caption("Campos marcados com * são obrigatórios.")

    # O número do formulário muda após cada cadastro bem-sucedido; assim os campos
    # voltam em branco e um novo clique não repete o cadastro anterior.
    numero = st.session_state.setdefault("form_nova_n", 0)
    chave = lambda nome: f"nova_{nome}_{numero}"  # noqa: E731
    setores = sorted(set(df["setor"].dropna()))

    with st.form(f"form_nova_{numero}"):
        titulo = st.text_input("Título *", max_chars=TAMANHO_MAXIMO["titulo"], key=chave("titulo"))
        descricao = st.text_area(
            "Descrição", max_chars=TAMANHO_MAXIMO["descricao"], key=chave("descricao")
        )
        c1, c2 = st.columns(2)
        responsavel = c1.text_input(
            "Responsável *", max_chars=TAMANHO_MAXIMO["responsavel"], key=chave("responsavel")
        )
        setor = c2.text_input(
            "Setor *",
            max_chars=TAMANHO_MAXIMO["setor"],
            key=chave("setor"),
            help=("Setores já usados: " + ", ".join(setores)) if setores else None,
        )
        c3, c4 = st.columns(2)
        prioridade = c3.selectbox("Prioridade", PRIORIDADES, index=1, key=chave("prioridade"))
        status = c4.selectbox("Status", STATUS, key=chave("status"))
        c5, c6 = st.columns(2)
        data_criacao = c5.date_input(
            "Data de criação",
            value=hoje,
            min_value=DATA_MINIMA,
            max_value=DATA_MAXIMA,
            format="DD/MM/YYYY",
            key=chave("data_criacao"),
        )
        prazo = c6.date_input(
            "Prazo de conclusão *",
            value=hoje + timedelta(days=7),
            min_value=DATA_MINIMA,
            max_value=DATA_MAXIMA,
            format="DD/MM/YYYY",
            key=chave("prazo"),
        )
        enviado = st.form_submit_button("Salvar demanda", type="primary")

    if not enviado:
        return

    dados = {
        "titulo": titulo,
        "descricao": descricao,
        "responsavel": responsavel,
        "setor": setor,
        "prioridade": prioridade,
        "status": status,
        "data_criacao": data_criacao,
        "prazo": prazo,
    }
    try:
        novo_id = database.criar_demanda(dados, hoje=hoje)
    except ErroValidacao as exc:
        for erro in exc.erros:
            st.error(erro)
    except database.DemandaDuplicada as exc:
        st.warning(str(exc))
    except sqlite3.Error as exc:
        st.error(f"Erro ao gravar no banco de dados: {exc}")
    else:
        avisar("success", f"Demanda #{novo_id} cadastrada com sucesso.")
        st.session_state["form_nova_n"] = numero + 1
        st.rerun()


# =============================================================================
# Página: Relatórios e dados
# =============================================================================
def aba_resumo(df, hoje):
    resumo = analytics.resumo_por_responsavel(df, hoje)
    st.subheader("Desempenho por responsável")
    st.dataframe(
        resumo,
        hide_index=True,
        column_config={
            "responsavel": "Responsável",
            "total": "Total",
            "concluidas": "Concluídas",
            "atrasadas": "Atrasadas",
            "percentual_conclusao": st.column_config.ProgressColumn(
                "% de conclusão", min_value=0, max_value=100, format="%.0f%%"
            ),
        },
        **LARGURA_TOTAL,
    )
    with st.expander("Como os indicadores são calculados"):
        st.markdown(
            f"""
- **Concluída:** status igual a *Concluída*. Demandas *Em andamento* não contam como concluídas.
- **Atrasada:** prazo anterior a hoje **e** status diferente de *Concluída*.
- **Prazo próximo:** prazo entre hoje e hoje + {DIAS_ALERTA_PRAZO} dias (inclusive), ainda não concluída.
- **Percentual de conclusão:** concluídas ÷ total × 100. Sem demandas, o resultado é 0%.
- **Desempenho mensal:** "criadas" usa a data de criação; "concluídas" usa a data de conclusão.
"""
        )


def aba_exportar(df, hoje):
    st.subheader("Exportar demandas")
    st.caption("Os arquivos contêm apenas as demandas que passam pelos filtros abaixo.")
    filtrado = painel_filtros(df, hoje, "exp")
    st.write(f"**{len(filtrado)}** demanda(s) selecionada(s) para exportação.")
    if filtrado.empty:
        st.warning("Não há demandas para exportar com os filtros atuais.")
        return

    with st.spinner("Preparando arquivos..."):
        csv = io_dados.exportar_csv(filtrado, hoje)
        excel = io_dados.exportar_excel(filtrado, hoje)
    nome = f"opsboard_demandas_{hoje:%Y%m%d}"
    c1, c2, _ = st.columns([1, 1, 2])
    c1.download_button("Baixar CSV", csv, f"{nome}.csv", "text/csv")
    c2.download_button(
        "Baixar Excel",
        excel,
        f"{nome}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def aba_importar(hoje):
    st.subheader("Importar demandas")
    st.caption(
        "Colunas obrigatórias: título, responsável, setor, prioridade, status e prazo. "
        "Opcionais: descrição, data_criacao e data_conclusao. Datas: AAAA-MM-DD ou DD/MM/AAAA."
    )
    st.download_button("Baixar modelo CSV", io_dados.modelo_csv(), "modelo_opsboard.csv", "text/csv")

    contador = st.session_state.setdefault("upload_n", 0)
    arquivo = st.file_uploader(
        "Selecione um arquivo CSV ou Excel (.xlsx)",
        type=["csv", "xlsx"],
        key=f"upload_{contador}",
    )
    if arquivo is None:
        st.info("Envie um arquivo para ver a validação antes de importar.")
        return

    with st.spinner("Lendo e validando o arquivo..."):
        try:
            resultado = io_dados.validar_importacao(io_dados.ler_arquivo(arquivo), hoje)
        except io_dados.ErroImportacao as exc:
            st.error(str(exc))
            return

    if resultado.ignoradas:
        st.info("Colunas ignoradas: " + ", ".join(map(str, resultado.ignoradas)) + ".")

    c1, c2, c3 = st.columns(3)
    cartao(c1, "Linhas lidas", resultado.total_linhas)
    cartao(c2, "Linhas válidas", len(resultado.validas))
    cartao(c3, "Erros encontrados", len(resultado.erros))

    if resultado.erros:
        st.warning("Linhas com erro não serão importadas. Corrija o arquivo e envie novamente, se necessário.")
        with st.expander(f"Ver erros ({len(resultado.erros)})", expanded=True):
            for erro in resultado.erros[:50]:
                st.write(f"- {erro}")
            if len(resultado.erros) > 50:
                st.write(f"... e mais {len(resultado.erros) - 50} erro(s).")

    if resultado.validas:
        st.write("Pré-visualização das linhas válidas:")
        previa = analytics.padronizar_dataframe(pd.DataFrame(resultado.validas))
        previa = io_dados.tabela_legivel(previa, hoje).drop(columns=["ID"])
        st.dataframe(previa.head(10), hide_index=True, **LARGURA_TOTAL)

    if st.button(
        f"Importar {len(resultado.validas)} demanda(s) válida(s)",
        type="primary",
        disabled=not resultado.validas,
    ):
        try:
            with st.spinner("Importando..."):
                resumo = database.importar_demandas(resultado.validas, hoje=hoje)
        except sqlite3.Error as exc:
            st.error(f"Erro ao gravar no banco de dados: {exc}")
            return
        partes = [f"{resumo['inseridas']} demanda(s) importada(s)."]
        if resumo["duplicadas"]:
            partes.append(f"{resumo['duplicadas']} ignorada(s) por já existirem.")
        if resultado.erros:
            partes.append(f"{len(resultado.erros)} erro(s) em linhas não importadas.")
        avisar("success" if resumo["inseridas"] else "warning", " ".join(partes))
        st.session_state["upload_n"] = contador + 1  # limpa o campo de upload
        st.rerun()


def pagina_relatorios(df, hoje):
    st.title("Relatórios e dados")
    aba1, aba2, aba3 = st.tabs(["Resumo", "Exportar", "Importar"])
    with aba1:
        if df.empty:
            st.info("Sem dados para resumir ainda.")
        else:
            aba_resumo(df, hoje)
    with aba2:
        if df.empty:
            st.info("Sem dados para exportar ainda.")
        else:
            aba_exportar(df, hoje)
    with aba3:
        aba_importar(hoje)


# =============================================================================
# Página: Alertas de prazo
# =============================================================================
def tabela_de_alerta(subconjunto, hoje, coluna_extra):
    """Tabela enxuta para alertas, com uma coluna extra de dias."""
    base = io_dados.tabela_legivel(subconjunto, hoje)
    colunas = ["ID", "Título", "Responsável", "Setor", "Prioridade", "Status", "Prazo"]
    tabela = base[colunas].copy()
    dias = analytics.dias_para_prazo(subconjunto, hoje)
    if coluna_extra == "Dias de atraso":
        tabela[coluna_extra] = (-dias).astype(int)
    elif coluna_extra == "Dias restantes":
        tabela[coluna_extra] = dias.astype(int)
    else:
        tabela[coluna_extra] = base[coluna_extra]
    return tabela


def secao_alerta(titulo, subconjunto, hoje, funcao_aviso, mensagem, coluna_extra, vazio):
    st.subheader(titulo)
    if subconjunto.empty:
        st.success(vazio)
        return
    funcao_aviso(mensagem.format(n=len(subconjunto)))
    mostrar_tabela(tabela_de_alerta(subconjunto.sort_values(["prazo", "id"]), hoje, coluna_extra))


def pagina_alertas(df, hoje):
    st.title("Alertas de prazo")
    st.caption(f"Situação em {hoje:%d/%m/%Y}. Demandas em andamento só deixam de ser alerta quando são concluídas.")
    if df.empty:
        st.info("Nenhuma demanda cadastrada ainda.")
        return

    atrasadas = analytics.demandas_atrasadas(df, hoje)
    proximas = analytics.demandas_prazo_proximo(df, hoje)
    alta = analytics.demandas_alta_prioridade_abertas(df)

    c1, c2, c3 = st.columns(3)
    cartao(c1, "Atrasadas", len(atrasadas))
    cartao(c2, f"Prazo nos próximos {DIAS_ALERTA_PRAZO} dias", len(proximas))
    cartao(c3, "Alta prioridade em aberto", len(alta))

    secao_alerta(
        "Demandas atrasadas",
        atrasadas,
        hoje,
        st.error,
        "{n} demanda(s) com prazo vencido e ainda não concluída(s).",
        "Dias de atraso",
        "Nenhuma demanda atrasada.",
    )
    secao_alerta(
        f"Prazo nos próximos {DIAS_ALERTA_PRAZO} dias",
        proximas,
        hoje,
        st.warning,
        "{n} demanda(s) vencem em breve.",
        "Dias restantes",
        "Nenhuma demanda vence nos próximos dias.",
    )
    secao_alerta(
        "Alta prioridade ainda não concluída",
        alta,
        hoje,
        st.warning,
        "{n} demanda(s) de alta prioridade em aberto.",
        "Situação do prazo",
        "Todas as demandas de alta prioridade estão concluídas.",
    )


# =============================================================================
# Execução principal
# =============================================================================
PAGINAS_FUNCOES = {
    "Visão geral": pagina_visao_geral,
    "Demandas": pagina_demandas,
    "Nova demanda": pagina_nova_demanda,
    "Relatórios e dados": pagina_relatorios,
    "Alertas de prazo": pagina_alertas,
}


def main():
    hoje = date.today()
    try:
        database.init_db()
        df = database.listar_demandas()
    except sqlite3.Error as exc:
        st.error(f"Não foi possível acessar o banco de dados: {exc}")
        st.stop()

    st.session_state.setdefault("pagina", PAGINAS[0])
    with st.sidebar:
        st.title("📊 OpsBoard")
        st.caption("Gestão de operações para pequenas equipes")
        st.radio("Navegação", PAGINAS, key="pagina", label_visibility="collapsed")
        st.divider()
        st.caption(f"Hoje: {hoje:%d/%m/%Y}")
        atrasadas = int(analytics.mascara_atrasadas(df, hoje).sum())
        if atrasadas:
            st.caption(f"⚠️ {atrasadas} demanda(s) atrasada(s)")

    exibir_aviso_pendente()
    PAGINAS_FUNCOES[st.session_state["pagina"]](df, hoje)


main()
