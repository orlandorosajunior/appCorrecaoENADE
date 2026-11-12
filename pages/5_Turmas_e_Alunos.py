"""
Pagina: cadastro de turmas e alunos.
Turmas e alunos cadastrados aqui ficam disponiveis para selecao (em vez de
redigitar) na pagina Corrigir Prova.
"""

import os

import streamlit as st

from auth import exigir_login

from db import (
    create_aluno,
    create_turma,
    delete_aluno,
    delete_turma,
    import_alunos_bulk,
    init_db,
    list_alunos,
    list_turmas,
)
from import_utils import PlanilhaError, carregar_planilha, extrair_alunos, sugerir_coluna, COLUNAS_MATRICULA_PROVAVEIS, COLUNAS_NOME_PROVAVEIS

st.set_page_config(page_title="Turmas e Alunos", layout="wide")

exigir_login()
init_db()

st.title("Turmas e Alunos")
st.caption(
    "Cadastre aqui uma vez e depois só selecione na página \"Corrigir Prova\" — "
    "sem precisar redigitar nome e turma a cada correção."
)

tab_turmas, tab_alunos = st.tabs(["Turmas", "Alunos"])

# ---------------------------------------------------------------------------
# Turmas
# ---------------------------------------------------------------------------
with tab_turmas:
    with st.expander("Cadastrar nova turma", expanded=False):
        with st.form("nova_turma_form", clear_on_submit=True):
            nome_turma = st.text_input("Nome da turma", placeholder="Ex.: ADS-3A Manhã")
            obs_turma = st.text_area("Observações (opcional)", height=68, key="obs_turma_form")
            submitted = st.form_submit_button("Cadastrar")
            if submitted:
                if not nome_turma.strip():
                    st.error("Informe um nome para a turma.")
                else:
                    try:
                        create_turma(nome_turma, obs_turma.strip())
                        st.success(f'Turma "{nome_turma}" cadastrada.')
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    st.subheader("Turmas cadastradas")
    turmas_df = list_turmas()
    if len(turmas_df) == 0:
        st.info("Nenhuma turma cadastrada ainda.")
    else:
        view = turmas_df.rename(
            columns={"id": "ID", "nome": "Nome", "n_alunos": "Alunos", "observacoes": "Observações", "data_criacao": "Criada em"}
        )
        st.dataframe(view[["ID", "Nome", "Alunos", "Observações", "Criada em"]], width='stretch', hide_index=True)

        with st.expander("Excluir uma turma"):
            st.warning(
                "Alunos vinculados a essa turma NÃO são excluídos — ficam sem turma associada "
                "(você pode reatribuí-los a outra turma na aba Alunos)."
            )
            opcoes_turma = {f"#{row.id} — {row.nome}": row.id for row in turmas_df.itertuples()}
            escolha_turma = st.selectbox("Turma", list(opcoes_turma.keys()), key="del_turma_select")
            confirmar_turma = st.checkbox("Confirmo a exclusão desta turma.", key="del_turma_confirm")
            if st.button("Excluir turma", disabled=not confirmar_turma):
                delete_turma(opcoes_turma[escolha_turma])
                st.success("Turma excluída.")
                st.rerun()

# ---------------------------------------------------------------------------
# Alunos
# ---------------------------------------------------------------------------
with tab_alunos:
    turmas_df = list_turmas()
    opcoes_turma_cadastro = {"Sem turma": None}
    opcoes_turma_cadastro.update({row.nome: row.id for row in turmas_df.itertuples()})

    # -----------------------------------------------------------------
    # Importar alunos de uma planilha
    # -----------------------------------------------------------------
    with st.expander("Importar alunos de uma planilha de turma", expanded=False):
        st.caption(
            "Aceita .xlsx, .xls (inclusive os exportados como HTML por sistemas acadêmicos, "
            "como listas de chamada) ou .csv. Você escolhe qual coluna é o nome antes de "
            "importar, e pode revisar/desmarcar linhas antes de confirmar."
        )

        arquivo_planilha = st.file_uploader(
            "Planilha de turma", type=["xlsx", "xls", "csv"], key="import_planilha_upload"
        )

        if arquivo_planilha is not None:
            assinatura_planilha = (arquivo_planilha.name, arquivo_planilha.size)
            if st.session_state.get("import_planilha_assinatura") != assinatura_planilha:
                st.session_state["import_planilha_assinatura"] = assinatura_planilha
                try:
                    st.session_state["import_planilha_df"] = carregar_planilha(arquivo_planilha.getvalue())
                    st.session_state.pop("import_planilha_erro", None)
                except PlanilhaError as e:
                    st.session_state["import_planilha_erro"] = str(e)
                    st.session_state.pop("import_planilha_df", None)

            if st.session_state.get("import_planilha_erro"):
                st.error(st.session_state["import_planilha_erro"])
            elif "import_planilha_df" in st.session_state:
                df_bruto = st.session_state["import_planilha_df"]
                st.caption(f"Planilha lida: {df_bruto.shape[0]} linha(s), {df_bruto.shape[1]} coluna(s).")
                with st.expander("Ver planilha original (bruta)"):
                    st.dataframe(df_bruto, width='stretch', hide_index=True)

                colunas = list(df_bruto.columns)
                sugestao_nome = sugerir_coluna(colunas, COLUNAS_NOME_PROVAVEIS)
                sugestao_matricula = sugerir_coluna(colunas, COLUNAS_MATRICULA_PROVAVEIS)

                col1, col2, col3 = st.columns(3)
                coluna_nome = col1.selectbox(
                    "Coluna com o nome do aluno",
                    colunas,
                    index=colunas.index(sugestao_nome) if sugestao_nome in colunas else 0,
                    key="import_col_nome",
                )
                opcoes_matricula = ["(nenhuma)"] + colunas
                coluna_matricula_escolha = col2.selectbox(
                    "Coluna com a matrícula (opcional)",
                    opcoes_matricula,
                    index=opcoes_matricula.index(sugestao_matricula) if sugestao_matricula in colunas else 0,
                    key="import_col_matricula",
                )
                coluna_matricula = None if coluna_matricula_escolha == "(nenhuma)" else coluna_matricula_escolha

                nome_sugerido_turma = os.path.splitext(arquivo_planilha.name)[0]
                opcoes_turma_import = ["+ Criar nova turma"] + [row.nome for row in turmas_df.itertuples()]
                turma_destino_escolha = col3.selectbox(
                    "Turma de destino", opcoes_turma_import, key="import_turma_destino"
                )

                if turma_destino_escolha == "+ Criar nova turma":
                    nome_nova_turma = st.text_input(
                        "Nome da nova turma", value=nome_sugerido_turma, key="import_nova_turma_nome"
                    )
                else:
                    nome_nova_turma = None

                alunos_extraidos = extrair_alunos(df_bruto, coluna_nome, coluna_matricula)
                st.markdown(f"**Revise antes de importar** ({len(alunos_extraidos)} linha(s) detectada(s)):")
                alunos_editados = st.data_editor(
                    alunos_extraidos,
                    width='stretch',
                    hide_index=True,
                    key="import_alunos_editor",
                    column_config={
                        "Incluir": st.column_config.CheckboxColumn(),
                    },
                )

                n_incluidos = int(alunos_editados["Incluir"].sum())
                turma_valida = (turma_destino_escolha != "+ Criar nova turma") or bool(
                    (nome_nova_turma or "").strip()
                )

                if st.button(
                    f"Importar {n_incluidos} aluno(s)",
                    disabled=n_incluidos == 0 or not turma_valida,
                    type="primary",
                    key="import_confirmar",
                ):
                    if turma_destino_escolha == "+ Criar nova turma":
                        try:
                            turma_id_destino = create_turma(nome_nova_turma)
                        except ValueError:
                            turma_id_destino = [
                                row.id for row in list_turmas().itertuples() if row.nome == nome_nova_turma.strip()
                            ][0]
                    else:
                        turma_id_destino = opcoes_turma_cadastro[turma_destino_escolha]

                    linhas_incluidas = alunos_editados[alunos_editados["Incluir"]]
                    lista_para_importar = [
                        {"nome": r["Nome"], "matricula": r["Matrícula"]} for _, r in linhas_incluidas.iterrows()
                    ]
                    resultado = import_alunos_bulk(lista_para_importar, turma_id=turma_id_destino)

                    st.success(
                        f"Importação concluída: {resultado['criados']} cadastrado(s) novo(s), "
                        f"{resultado['ja_existiam']} já existiam nessa turma, "
                        f"{resultado['turma_atualizada']} tiveram a turma atualizada."
                    )
                    for chave in ("import_planilha_assinatura", "import_planilha_df", "import_planilha_erro"):
                        st.session_state.pop(chave, None)
                    st.rerun()

    # -----------------------------------------------------------------
    # Cadastro manual
    # -----------------------------------------------------------------
    with st.expander("Cadastrar novo aluno manualmente", expanded=False):
        with st.form("novo_aluno_form", clear_on_submit=True):
            nome_aluno = st.text_input("Nome completo do aluno")
            turma_escolhida = st.selectbox("Turma", list(opcoes_turma_cadastro.keys()), key="turma_aluno_form")
            matricula_aluno = st.text_input("Matrícula (opcional)", key="matricula_aluno_form")
            obs_aluno = st.text_area("Observações (opcional)", height=68, key="obs_aluno_form")
            submitted_aluno = st.form_submit_button("Cadastrar")
            if submitted_aluno:
                if not nome_aluno.strip():
                    st.error("Informe o nome do aluno.")
                else:
                    create_aluno(
                        nome_aluno,
                        opcoes_turma_cadastro[turma_escolhida],
                        obs_aluno.strip(),
                        matricula_aluno.strip() or None,
                    )
                    st.success(f'Aluno "{nome_aluno}" cadastrado.')
                    st.rerun()

    st.subheader("Alunos cadastrados")
    filtro_opcoes = {"Todas as turmas": None}
    filtro_opcoes.update({row.nome: row.id for row in turmas_df.itertuples()})
    filtro_turma = st.selectbox("Filtrar por turma", list(filtro_opcoes.keys()), key="filtro_turma_alunos")

    alunos_df = list_alunos(turma_id=filtro_opcoes[filtro_turma])
    if len(alunos_df) == 0:
        st.info("Nenhum aluno cadastrado com esse filtro.")
    else:
        view = alunos_df.rename(
            columns={
                "id": "ID",
                "nome": "Nome",
                "turma": "Turma",
                "matricula": "Matrícula",
                "observacoes": "Observações",
                "data_criacao": "Cadastrado em",
            }
        )
        view["Turma"] = view["Turma"].fillna("—")
        view["Matrícula"] = view["Matrícula"].fillna("—")
        st.dataframe(
            view[["ID", "Nome", "Matrícula", "Turma", "Observações", "Cadastrado em"]],
            width='stretch',
            hide_index=True,
        )

        with st.expander("Excluir um aluno"):
            st.warning(
                "Excluir o aluno não apaga correções já salvas com o nome dele, mas elas deixam "
                "de estar vinculadas a um cadastro (o nome continua aparecendo no histórico)."
            )
            opcoes_aluno = {f"#{row.id} — {row.nome}": row.id for row in alunos_df.itertuples()}
            escolha_aluno = st.selectbox("Aluno", list(opcoes_aluno.keys()), key="del_aluno_select")
            confirmar_aluno = st.checkbox("Confirmo a exclusão deste aluno.", key="del_aluno_confirm")
            if st.button("Excluir aluno", disabled=not confirmar_aluno):
                delete_aluno(opcoes_aluno[escolha_aluno])
                st.success("Aluno excluído.")
                st.rerun()
