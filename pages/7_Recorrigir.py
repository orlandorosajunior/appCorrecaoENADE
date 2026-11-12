"""
Pagina: Recorrigir - editar TODOS os campos de uma correcao ja salva:
aluno/turma, horario de inicio/fim, respostas das questoes objetivas, e a
questao discursiva (foto, transcricao da IA, justificativas por item e
pontuacao). Pensada tambem para reler o feedback que a IA deu ao aluno
antes de repassar isso pra ele.
"""

import os
from datetime import time as dtime

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from auth import exigir_login

from config import load_config
from db import (
    create_aluno,
    get_correcao,
    get_simulado,
    init_db,
    list_alunos,
    list_correcoes,
    list_simulados,
    list_turmas,
    update_correcao,
)
from omr_utils import load_template
from scoring import calcular_nota_1000, calcular_tempo_prova_minutos
from ui_common import (
    annotate,
    answers_to_df,
    capture_image_ui,
    df_to_answers,
    discursiva_grading_ui,
    editable_answers_table,
    preseed_discursiva_session,
    run_omr,
)

st.set_page_config(page_title="Recorrigir", layout="wide")

exigir_login()
init_db()

cfg = load_config()

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "template_gabarito.json")
DISCURSIVAS_DIR = os.path.join(BASE_DIR, "data", "discursivas")

template = load_template(TEMPLATE_PATH)
N_QUESTIONS = len(template["questions"])
CANVAS_W = 1200
CANVAS_H = round(CANVAS_W / template["ref_box_aspect_w_over_h"])

st.title("Recorrigir")
st.caption(
    "Reabra uma correção já salva para revisar ou corrigir qualquer campo: horário, respostas "
    "objetivas, e a questão discursiva (incluindo a transcrição e as justificativas que a IA "
    "deu, úteis para montar o feedback do aluno)."
)

# ---------------------------------------------------------------------------
# 1. Selecionar a correção
# ---------------------------------------------------------------------------
simulados_df = list_simulados()
if len(simulados_df) == 0:
    st.info("Nenhum simulado cadastrado ainda.")
    st.stop()

opcoes_simulado = {f"#{row.id} — {row.nome}": row.id for row in simulados_df.itertuples()}
escolha_simulado = st.selectbox("Simulado", list(opcoes_simulado.keys()), key="recorrigir_simulado")
simulado_id = opcoes_simulado[escolha_simulado]
simulado = get_simulado(simulado_id)
gabarito = {int(q): letra for q, letra in simulado["gabarito_dict"].items()} if simulado["gabarito_dict"] else {}

df_correcoes = list_correcoes(simulado_id=simulado_id)
if len(df_correcoes) == 0:
    st.info("Nenhuma correção salva ainda para este simulado.")
    st.stop()

opcoes_correcao = {
    f"#{row.id} — {row.aluno} ({row.turma}) — {row.data[:16].replace('T', ' ')}": row.id
    for row in df_correcoes.itertuples()
}
escolha_correcao = st.selectbox("Correção", list(opcoes_correcao.keys()), key="recorrigir_correcao_select")
correcao_id = opcoes_correcao[escolha_correcao]
correcao = get_correcao(correcao_id)

st.divider()

# ---------------------------------------------------------------------------
# 2. Aluno / turma
# ---------------------------------------------------------------------------
st.subheader("Aluno")
turmas_df = list_turmas()
opcoes_turma = {row.nome: row.id for row in turmas_df.itertuples()}
nomes_turma = list(opcoes_turma.keys())
turma_atual_nome = correcao["turma"] if correcao["turma"] in nomes_turma else (nomes_turma[0] if nomes_turma else None)

col_t, col_a = st.columns(2)
nome_turma_escolhida = col_t.selectbox(
    "Turma", nomes_turma, index=nomes_turma.index(turma_atual_nome) if turma_atual_nome in nomes_turma else 0,
    key=f"recorrigir_turma_{correcao_id}",
)
turma_id_escolhida = opcoes_turma[nome_turma_escolhida]

alunos_df = list_alunos(turma_id=turma_id_escolhida)

# Rotulos por aluno: se houver nomes repetidos nesta turma (homônimos, cadastro
# duplicado), o rotulo inclui o ID para não misturar um aluno com outro.
contagem_nomes = alunos_df["nome"].value_counts() if len(alunos_df) else {}


def _rotulo_aluno(row):
    if contagem_nomes.get(row.nome, 0) > 1:
        return f"{row.nome} (#{row.id})"
    return row.nome


opcoes_aluno = {_rotulo_aluno(row): row.id for row in alunos_df.itertuples()}
nomes_aluno = list(opcoes_aluno.keys())

# A selecao inicial usa o ALUNO_ID ja gravado na correcao (nao o nome) -
# assim, mesmo com homonimos na turma, o aluno certo continua pre-selecionado.
rotulo_atual = None
for row in alunos_df.itertuples():
    if row.id == correcao["aluno_id"]:
        rotulo_atual = _rotulo_aluno(row)
        break
if rotulo_atual is None and nomes_aluno:
    rotulo_atual = nomes_aluno[0]

with col_a:
    if nomes_aluno:
        nome_aluno_escolhido_rotulo = st.selectbox(
            "Aluno", nomes_aluno, index=nomes_aluno.index(rotulo_atual) if rotulo_atual in nomes_aluno else 0,
            key=f"recorrigir_aluno_{correcao_id}_{turma_id_escolhida}",
        )
        aluno_id_escolhido = opcoes_aluno[nome_aluno_escolhido_rotulo]
        # nome "limpo" (sem o sufixo "(#id)") para salvar no campo de texto da correcao
        nome_aluno_escolhido = nome_aluno_escolhido_rotulo.split(" (#")[0]
        if aluno_id_escolhido != correcao["aluno_id"]:
            st.warning(
                f"Você está prestes a reatribuir esta correção para um aluno diferente do "
                f"original (\"{correcao['aluno']}\"). Confirme que é isso mesmo antes de salvar."
            )
    else:
        st.warning("Nenhum aluno cadastrado nesta turma.")
        nome_aluno_escolhido = correcao["aluno"]
        aluno_id_escolhido = correcao["aluno_id"]

with st.expander("Cadastrar novo aluno nesta turma"):
    with st.form(f"recorrigir_novo_aluno_{correcao_id}", clear_on_submit=True):
        nome_novo = st.text_input("Nome completo")
        if st.form_submit_button("Cadastrar e selecionar"):
            if nome_novo.strip():
                create_aluno(nome_novo, turma_id=turma_id_escolhida)
                st.session_state[f"recorrigir_aluno_{correcao_id}_{turma_id_escolhida}"] = nome_novo.strip()
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# 3. Horário da prova
# ---------------------------------------------------------------------------
st.subheader("Horário da prova")


def _parse_hora(valor):
    if not valor:
        return None
    try:
        return dtime.fromisoformat(valor)
    except ValueError:
        return None


hora_inicio_salva = _parse_hora(correcao["hora_inicio"])
hora_fim_salva = _parse_hora(correcao["hora_fim"])

usar_horario = st.checkbox(
    "Esta correção tem horário registrado", value=hora_inicio_salva is not None, key=f"recorrigir_usar_horario_{correcao_id}"
)
col_hi, col_hf = st.columns(2)
hora_inicio_input = col_hi.time_input(
    "Início", value=hora_inicio_salva or dtime(8, 0), disabled=not usar_horario,
    key=f"recorrigir_hi_{correcao_id}", step=60,
)
hora_fim_input = col_hf.time_input(
    "Término", value=hora_fim_salva or dtime(10, 0), disabled=not usar_horario,
    key=f"recorrigir_hf_{correcao_id}", step=60,
)
if usar_horario:
    tempo_prova_minutos = calcular_tempo_prova_minutos(hora_inicio_input, hora_fim_input)
    st.caption(f"Tempo de prova: {tempo_prova_minutos:.0f} minutos.")
    hora_inicio_iso = hora_inicio_input.isoformat()
    hora_fim_iso = hora_fim_input.isoformat()
else:
    tempo_prova_minutos = None
    hora_inicio_iso = hora_fim_iso = None

st.divider()

# ---------------------------------------------------------------------------
# 4. Questões objetivas
# ---------------------------------------------------------------------------
st.subheader("Questões objetivas (01 a 31)")

with st.expander("Reprocessar a partir de uma nova foto (opcional)"):
    st.caption("Só use se quiser reler o cartão a partir de outra imagem. Sem isso, a tabela abaixo já vem preenchida com as respostas salvas.")
    with st.expander("Ajuste fino da leitura"):
        fill_threshold = st.slider(
            "Sensibilidade mínima de preenchimento", 0.10, 0.80, float(cfg["fill_threshold"]), step=0.05,
            key=f"recorrigir_ft_{correcao_id}",
        )
        relative_margin = st.slider(
            "Margem relativa (marca vs. demais bolhas)", 1.05, 2.0, float(cfg["relative_margin"]), step=0.05,
            key=f"recorrigir_rm_{correcao_id}",
        )
    nova_imagem = capture_image_ui(key_prefix=f"recorrigir_nova_foto_{correcao_id}")
    respostas_da_nova_foto = None
    if nova_imagem is not None:
        warped, answers_novas, fills, corners_found = run_omr(
            nova_imagem, template, CANVAS_W, CANVAS_H, fill_threshold, relative_margin
        )
        if not corners_found:
            st.warning("Não consegui detectar a moldura da tabela nesta foto — confira com atenção.")
        annotated = annotate(warped, template, CANVAS_W, CANVAS_H, answers_novas, gabarito=gabarito)
        st.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB), width='stretch')
        if st.button("Usar esta leitura na tabela abaixo", key=f"usar_nova_leitura_{correcao_id}"):
            st.session_state[f"recorrigir_respostas_override_{correcao_id}"] = answers_novas
            st.rerun()

respostas_iniciais = st.session_state.get(
    f"recorrigir_respostas_override_{correcao_id}",
    {int(q): letra for q, letra in correcao["respostas_dict"].items()},
)
df_respostas = answers_to_df(respostas_iniciais, N_QUESTIONS)
edited_df = editable_answers_table(df_respostas, key=f"recorrigir_editor_{correcao_id}")
respostas_finais = df_to_answers(edited_df)

acertos = 0
linhas = []
for q in range(1, N_QUESTIONS + 1):
    marcada = respostas_finais.get(q)
    correta = gabarito.get(q)
    if marcada == correta:
        status = "Certo"
        acertos += 1
    elif marcada is None:
        status = "Em branco"
    else:
        status = "Errado"
    linhas.append({"Questão": q, "Marcada": marcada or "-", "Gabarito": correta or "-", "Status": status})
st.dataframe(pd.DataFrame(linhas), width='stretch', hide_index=True)

nota = 100 * acertos / N_QUESTIONS
st.metric("Nota — questões objetivas", f"{acertos}/{N_QUESTIONS} ({nota:.1f}%)")

st.divider()

# ---------------------------------------------------------------------------
# 5. Questão discursiva (com o feedback já dado pela IA, se houver)
# ---------------------------------------------------------------------------
st.subheader("Questão discursiva (32)")
preseed_discursiva_session(f"recorrigir_disc_{correcao_id}", correcao["discursiva_avaliacao_dict"])
avaliacao_disc = discursiva_grading_ui(
    simulado,
    key_prefix=f"recorrigir_disc_{correcao_id}",
    cfg=cfg,
    imagem_existente_path=correcao["discursiva_imagem_path"],
)

st.divider()

# ---------------------------------------------------------------------------
# 6. Nota final e salvar
# ---------------------------------------------------------------------------
st.subheader("Nota final")
resultado_nota = calcular_nota_1000(
    acertos, N_QUESTIONS, avaliacao_disc["pontos"], avaliacao_disc["pontos_max"],
    peso_discursiva_pontos=cfg["peso_discursiva_pontos"],
)
nota_1000 = resultado_nota["nota_1000"]
st.metric("Nota (escala 0-1000)", f"{nota_1000:.1f}", delta=f"{nota_1000 - (correcao['nota_1000'] or 0):.1f} vs. valor salvo")

if st.button("Salvar alterações desta correção", type="primary"):
    caminho_imagem_disc = correcao["discursiva_imagem_path"]
    if avaliacao_disc["imagem_bytes"] is not None:
        os.makedirs(DISCURSIVAS_DIR, exist_ok=True)
        import uuid

        caminho_imagem_disc = os.path.join(DISCURSIVAS_DIR, f"{uuid.uuid4().hex}.jpg")
        with open(caminho_imagem_disc, "wb") as f:
            f.write(avaliacao_disc["imagem_bytes"])

    update_correcao(
        correcao_id,
        aluno=nome_aluno_escolhido,
        turma=nome_turma_escolhida,
        aluno_id=aluno_id_escolhido,
        turma_id=turma_id_escolhida,
        respostas={str(q): letra for q, letra in respostas_finais.items()},
        acertos=acertos,
        n_questoes=N_QUESTIONS,
        nota=nota,
        discursiva_pontos=avaliacao_disc["pontos"],
        discursiva_pontos_max=avaliacao_disc["pontos_max"],
        discursiva_avaliacao=avaliacao_disc["avaliacao"],
        discursiva_imagem_path=caminho_imagem_disc,
        hora_inicio=hora_inicio_iso,
        hora_fim=hora_fim_iso,
        tempo_prova_minutos=tempo_prova_minutos,
        nota_1000=nota_1000,
        discursiva_pontos_1000=resultado_nota["pontos_discursiva_1000"],
    )
    st.session_state.pop(f"recorrigir_respostas_override_{correcao_id}", None)
    st.success("Correção atualizada com sucesso.")
    st.rerun()
