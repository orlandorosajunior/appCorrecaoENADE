"""
Pagina: cadastro de simulados e definicao do gabarito oficial
(manualmente ou fotografando uma folha ja preenchida com as respostas certas).
"""

import os

import cv2
import pandas as pd
import streamlit as st

from auth import exigir_login

from config import load_config
from db import (
    create_simulado,
    delete_simulado,
    get_simulado,
    init_db,
    list_simulados,
    update_gabarito,
    update_rubrica_discursiva,
    update_temas_questoes,
)
from omr_utils import load_template
from enade_referencia import OBJETOS_ADS_ESPECIFICO, OBJETOS_FORMACAO_GERAL
from ui_common import (
    annotate,
    answers_to_df,
    capture_image_ui,
    df_to_answers,
    editable_answers_table,
    run_omr,
)

st.set_page_config(page_title="Simulados e Gabaritos", layout="wide")

exigir_login()
init_db()

cfg = load_config()

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template_gabarito.json")
template = load_template(TEMPLATE_PATH)
N_QUESTIONS = len(template["questions"])
CANVAS_W = 1200
CANVAS_H = round(CANVAS_W / template["ref_box_aspect_w_over_h"])

st.title("Simulados e Gabaritos")
st.caption(
    "Cada simulado tem duas partes independentes: o **gabarito das questões objetivas** "
    "(01 a 31, obrigatório) e, opcionalmente, a **rubrica da questão discursiva** (32) — "
    "role até o final da página depois de definir o gabarito para cadastrá-la."
)

# ---------------------------------------------------------------------------
# 1. Cadastrar novo simulado
# ---------------------------------------------------------------------------
with st.expander("Cadastrar novo simulado", expanded=False):
    with st.form("novo_simulado_form", clear_on_submit=True):
        nome = st.text_input("Nome do simulado", placeholder="Ex.: Simulado ENADE 2026.2")
        observacoes = st.text_area("Observações (opcional)", height=80)
        submitted = st.form_submit_button("Cadastrar")
        if submitted:
            if not nome.strip():
                st.error("Informe um nome para o simulado.")
            else:
                new_id = create_simulado(nome.strip(), N_QUESTIONS, observacoes.strip())
                st.success(f"Simulado \"{nome}\" cadastrado (ID {new_id}).")
                st.rerun()

# ---------------------------------------------------------------------------
# 2. Selecionar simulado existente
# ---------------------------------------------------------------------------
simulados_df = list_simulados()

if len(simulados_df) == 0:
    st.info("Nenhum simulado cadastrado ainda. Use o formulário acima para começar.")
    st.stop()

opcoes = {
    f"#{row.id} — {row.nome} "
    f"({'gabarito definido' if row.tem_gabarito else 'SEM gabarito'} · "
    f"{'com rubrica' if row.tem_rubrica else 'sem rubrica'})": row.id
    for row in simulados_df.itertuples()
}
escolha = st.selectbox("Selecione um simulado", list(opcoes.keys()))
simulado_id = opcoes[escolha]
simulado = get_simulado(simulado_id)

st.divider()
st.subheader(f"Gabarito — {simulado['nome']}")

if simulado["gabarito_dict"]:
    resumo = ", ".join(f"{q}:{simulado['gabarito_dict'][q]}" for q in sorted(simulado["gabarito_dict"], key=int))
    st.success("Gabarito já definido para este simulado:")
    st.code(resumo, language=None)
else:
    st.warning("Este simulado ainda não tem gabarito definido.")

tab_manual, tab_foto = st.tabs(["Preencher manualmente", "Carregar via foto"])

# --- Manual -----------------------------------------------------------
with tab_manual:
    st.caption("Escolha a alternativa correta de cada questão e clique em salvar.")
    initial_answers = {int(q): letra for q, letra in simulado["gabarito_dict"].items()} if simulado["gabarito_dict"] else {}
    df_inicial = answers_to_df(initial_answers, N_QUESTIONS)
    edited_df = editable_answers_table(df_inicial, key=f"gabarito_manual_{simulado_id}")

    if st.button("Salvar gabarito (manual)", key=f"salvar_manual_{simulado_id}"):
        novo_gabarito = df_to_answers(edited_df)
        faltando = [q for q, letra in novo_gabarito.items() if letra is None]
        if faltando:
            st.error(f"Faltam {len(faltando)} questão(ões) sem alternativa definida: {faltando}")
        else:
            update_gabarito(simulado_id, {str(q): letra for q, letra in novo_gabarito.items()})
            st.success("Gabarito salvo com sucesso.")
            st.rerun()

# --- Via foto -----------------------------------------------------------
with tab_foto:
    st.caption(
        "Fotografe (ou envie o PDF/scan de) uma folha do Cartão-Resposta já preenchida com as "
        "respostas corretas. O sistema lê as marcações automaticamente — revise antes de salvar."
    )

    with st.expander("Ajuste fino da leitura"):
        fill_threshold = st.slider(
            "Sensibilidade mínima de preenchimento",
            0.10,
            0.80,
            float(cfg["fill_threshold"]),
            step=0.05,
            key=f"ft_{simulado_id}",
        )
        relative_margin = st.slider(
            "Margem relativa (marca vs. demais bolhas)",
            1.05,
            2.0,
            float(cfg["relative_margin"]),
            step=0.05,
            key=f"rm_{simulado_id}",
        )

    image_bgr = capture_image_ui(key_prefix=f"gabarito_foto_{simulado_id}")

    if image_bgr is not None:
        warped, answers, fills, corners_found = run_omr(
            image_bgr, template, CANVAS_W, CANVAS_H, fill_threshold, relative_margin
        )

        if not corners_found:
            st.warning(
                "Não consegui detectar automaticamente a moldura da tabela de questões — a "
                "imagem foi apenas redimensionada. Confira com atenção a leitura abaixo antes "
                "de salvar."
            )

        annotated = annotate(warped, template, CANVAS_W, CANVAS_H, answers)
        st.image(
            cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
            caption="Leitura automática (revise abaixo antes de salvar)",
            width='stretch',
        )

        st.markdown("**Revise e corrija a leitura, se necessário:**")
        df_detectado = answers_to_df(answers, N_QUESTIONS)
        edited_df_foto = editable_answers_table(df_detectado, key=f"gabarito_foto_editor_{simulado_id}")

        if st.button("Salvar gabarito (via foto)", key=f"salvar_foto_{simulado_id}"):
            novo_gabarito = df_to_answers(edited_df_foto)
            faltando = [q for q, letra in novo_gabarito.items() if letra is None]
            if faltando:
                st.error(f"Faltam {len(faltando)} questão(ões) sem alternativa definida: {faltando}")
            else:
                update_gabarito(simulado_id, {str(q): letra for q, letra in novo_gabarito.items()})
                st.success("Gabarito salvo com sucesso.")
                st.rerun()

# ---------------------------------------------------------------------------
# 3. Rubrica da questão discursiva (32)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Rubrica da questão discursiva (32)")
st.info(
    "Esta seção é separada do gabarito acima — role até aqui depois de definir as respostas "
    "objetivas para também configurar a questão discursiva."
)
st.caption(
    "A questão 32 é dissertativa e não é lida pelo OMR. Se você definir uma rubrica aqui, "
    "na página \"Corrigir Prova\" será possível fotografar a resposta do aluno e pedir uma "
    "avaliação sugerida (via IA, com a API do Google Gemini) com base nesses critérios — você "
    "sempre revisa e confirma a nota antes de salvar."
)

exemplo_rubrica = """a) Funcional x não funcional
Requisitos funcionais são o que o sistema efetivamente FAZ [...]. Já o requisito não \
funcional é sobre um atributo de qualidade do sistema, não uma função nova [...].

b) Estrutura de banco de dados
A resposta esperada não precisa necessariamente de um diagrama, só descrever as tabelas \
principais [...].

c) Verificação e validação (V&V)
A resposta precisa citar pelo menos duas práticas que garantam que a regra crítica \
realmente funcione antes de o sistema ir pra produção [...].

Critérios de correção: 0 a 3 pontos por item (a, b, c), totalizando até 9-10 pontos. \
Vale considerar um ponto adicional se o texto integrar os três aspectos entre si, em vez \
de tratar cada um isoladamente."""

rubrica_atual = simulado.get("rubrica_discursiva") or ""
rubrica_editada = st.text_area(
    "Rubrica (critérios de correção da questão 32)",
    value=rubrica_atual,
    height=280,
    placeholder=exemplo_rubrica,
    key=f"rubrica_{simulado_id}",
)
if st.button("Salvar rubrica", key=f"salvar_rubrica_{simulado_id}"):
    update_rubrica_discursiva(simulado_id, rubrica_editada.strip())
    st.success("Rubrica salva.")
    st.rerun()

# ---------------------------------------------------------------------------
# 3b. Temas das questões (objetos de aprendizagem) — opcional
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Temas das questões (opcional)")
st.caption(
    "Associe cada questão objetiva a um tema/objeto de conhecimento. Isso habilita, no PDF de "
    "feedback do aluno e no Relatório Geral (página Exportar), uma análise de quais objetos de "
    "conhecimento a turma (ou cada aluno) mais precisa reforçar."
)

with st.expander("Referência oficial: objetos de conhecimento do Enade 2026 (ADS)"):
    st.caption(
        "Use exatamente esses nomes ao preencher a tabela abaixo — isso evita que \"Banco de "
        "Dados\" e \"banco de dados\", por exemplo, sejam contados como temas diferentes nos "
        "relatórios."
    )
    col_fg, col_ads = st.columns(2)
    with col_fg:
        st.markdown("**Formação Geral** _(Portaria Inep nº 154/2026)_")
        for item in OBJETOS_FORMACAO_GERAL:
            st.markdown(f"- {item}")
    with col_ads:
        st.markdown("**Componente específico — ADS** _(Portaria Inep nº 169/2026)_")
        for item in OBJETOS_ADS_ESPECIFICO:
            st.markdown(f"- {item}")

temas_atuais = simulado.get("temas_questoes_dict") or {}
valores_customizados_existentes = sorted(
    {v for v in temas_atuais.values() if v and v not in OBJETOS_ADS_ESPECIFICO and v not in OBJETOS_FORMACAO_GERAL}
)
opcoes_tema = [""] + OBJETOS_ADS_ESPECIFICO + OBJETOS_FORMACAO_GERAL + valores_customizados_existentes + ["Outro (digite abaixo)"]
df_temas = pd.DataFrame(
    {"Questão": list(range(1, N_QUESTIONS + 1)), "Tema": [temas_atuais.get(str(q), "") for q in range(1, N_QUESTIONS + 1)]}
)
st.caption(
    "Dica: escolha \"Outro (digite abaixo)\" numa linha para digitar um tema que não está nas "
    "listas oficiais acima."
)
df_temas_editado = st.data_editor(
    df_temas,
    width='stretch',
    hide_index=True,
    key=f"temas_editor_{simulado_id}",
    column_config={
        "Questão": st.column_config.NumberColumn(disabled=True),
        "Tema": st.column_config.SelectboxColumn(options=opcoes_tema),
    },
)

tema_livre_texto = ""
if (df_temas_editado["Tema"] == "Outro (digite abaixo)").any():
    linhas_outro = df_temas_editado[df_temas_editado["Tema"] == "Outro (digite abaixo)"]["Questão"].tolist()
    st.markdown(f"**Questões marcadas como \"Outro\":** {', '.join(str(int(q)) for q in linhas_outro)}")
    tema_livre_texto = st.text_area(
        "Digite, uma por linha, no formato \"questão: tema\" (ex.: \"5: Testes automatizados\")",
        key=f"temas_livres_{simulado_id}",
        height=80,
    )

if st.button("Salvar temas das questões", key=f"salvar_temas_{simulado_id}"):
    novos_temas = {
        str(int(row["Questão"])): row["Tema"].strip()
        for _, row in df_temas_editado.iterrows()
        if row["Tema"] and row["Tema"].strip() and row["Tema"] != "Outro (digite abaixo)"
    }
    for linha in tema_livre_texto.splitlines():
        if ":" not in linha:
            continue
        num_str, tema_str = linha.split(":", 1)
        num_str, tema_str = num_str.strip(), tema_str.strip()
        if num_str.isdigit() and tema_str:
            novos_temas[num_str] = tema_str
    update_temas_questoes(simulado_id, novos_temas)
    st.success("Temas salvos.")
    st.rerun()

# ---------------------------------------------------------------------------
# 4. Excluir simulado
# ---------------------------------------------------------------------------
st.divider()
with st.expander("Excluir este simulado"):
    st.warning(
        "Excluir o simulado também apaga todas as correções de alunos associadas a ele. "
        "Essa ação não pode ser desfeita."
    )
    confirmar = st.checkbox("Confirmo que quero excluir este simulado e todo o seu histórico.", key=f"conf_{simulado_id}")
    if st.button("Excluir permanentemente", disabled=not confirmar, key=f"del_{simulado_id}"):
        delete_simulado(simulado_id)
        st.success("Simulado excluído.")
        st.rerun()
