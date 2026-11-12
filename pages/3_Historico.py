"""
Pagina: historico de correcoes - filtros por simulado/turma/aluno,
estatisticas (media geral, media por turma, acerto por questao) e exportacao.
"""

import json
import os
import uuid

import pandas as pd
import streamlit as st

from auth import exigir_login

from config import load_config
from db import (
    delete_correcao, get_correcao, get_simulado, init_db, list_correcoes, list_simulados,
    update_correcao, update_discursiva,
)
from datetime import time as dtime

from scoring import calcular_nota_1000, calcular_tempo_prova_minutos
from ui_common import corrigir_discursivas_em_lote_ui, discursiva_grading_ui

st.set_page_config(page_title="Histórico", layout="wide")

exigir_login()
init_db()

st.title("Histórico de Correções")

simulados_df = list_simulados()

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)

opcoes_simulado = {"Todos": None}
opcoes_simulado.update({f"#{row.id} — {row.nome}": row.id for row in simulados_df.itertuples()})
escolha_simulado = col1.selectbox("Simulado", list(opcoes_simulado.keys()))
filtro_simulado_id = opcoes_simulado[escolha_simulado]

filtro_turma = col2.text_input("Turma contém")
filtro_aluno = col3.text_input("Aluno contém")

df = list_correcoes(simulado_id=filtro_simulado_id, turma=filtro_turma or None, aluno=filtro_aluno or None)

if len(df) == 0:
    st.info("Nenhuma correção encontrada com esses filtros.")
    st.stop()

# ---------------------------------------------------------------------------
# Estatísticas
# ---------------------------------------------------------------------------
st.subheader("Resumo")
col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("Correções", len(df))
col_b.metric("Nota média (0-1000)", f"{df['nota_1000'].dropna().mean():.1f}" if df["nota_1000"].notna().any() else "—")
col_c.metric("Nota média (objetiva %)", f"{df['nota'].mean():.1f}%")

disc_validas = df.dropna(subset=["discursiva_pontos", "discursiva_pontos_max"])
if len(disc_validas):
    percentuais = 100 * disc_validas["discursiva_pontos"] / disc_validas["discursiva_pontos_max"]
    col_d.metric("Discursiva — aproveitamento médio", f"{percentuais.mean():.0f}%")
    disc_1000_validas = df["discursiva_pontos_1000"].dropna()
    if len(disc_1000_validas):
        col_e.metric("Discursiva — pts médios na nota", f"{disc_1000_validas.mean():.1f}")
    else:
        col_e.metric("Discursiva — pts médios na nota", "—")
else:
    col_d.metric("Discursiva — aproveitamento médio", "—")
    col_e.metric("Discursiva — pts médios na nota", "—")

st.caption(
    "\"Aproveitamento médio\" é o desempenho bruto na discursiva (0-100%, comparável entre "
    "simulados mesmo que o peso configurado mude). \"Pts médios na nota\" é quanto isso "
    "representou, em pontos de 1000, com o peso da discursiva vigente no momento de cada correção."
)

with st.expander("Média por turma (nota 0-1000)"):
    media_turma = df.groupby("turma", dropna=False)["nota_1000"].mean().sort_values(ascending=False)
    st.bar_chart(media_turma)

if filtro_simulado_id is not None:
    simulado = get_simulado(filtro_simulado_id)
    gabarito = simulado["gabarito_dict"]
    if gabarito:
        with st.expander("Percentual de acerto por questão (neste simulado)"):
            acertos_por_questao = {q: 0 for q in gabarito}
            for respostas_json in df["respostas"]:
                respostas = json.loads(respostas_json)
                for q, correta in gabarito.items():
                    if respostas.get(q) == correta:
                        acertos_por_questao[q] += 1
            total = len(df)
            serie = pd.Series(
                {int(q): 100 * acertos_por_questao[q] / total for q in sorted(gabarito, key=int)}
            )
            serie.index.name = "Questão"
            st.bar_chart(serie)
            piores = serie.sort_values().head(5)
            st.caption(
                "Questões com menor % de acerto: "
                + ", ".join(f"Q{q} ({v:.0f}%)" for q, v in piores.items())
            )

# ---------------------------------------------------------------------------
# Tabela
# ---------------------------------------------------------------------------
st.subheader("Correções")

df_tabela = df.copy()
df_tabela["discursiva_percentual"] = (
    100 * df_tabela["discursiva_pontos"] / df_tabela["discursiva_pontos_max"]
).round(0)

view = df_tabela[["id", "simulado", "aluno", "turma", "acertos", "n_questoes", "nota", "nota_1000",
                   "discursiva_pontos", "discursiva_pontos_max", "discursiva_percentual",
                   "discursiva_pontos_1000", "tempo_prova_minutos", "data"]].rename(
    columns={
        "id": "ID",
        "simulado": "Simulado",
        "aluno": "Aluno",
        "turma": "Turma",
        "acertos": "Acertos",
        "n_questoes": "Questões",
        "nota": "Nota objetiva (%)",
        "nota_1000": "Nota (0-1000)",
        "discursiva_pontos": "Discursiva (bruto)",
        "discursiva_pontos_max": "Discursiva (máx bruto)",
        "discursiva_percentual": "Discursiva (%)",
        "discursiva_pontos_1000": "Discursiva (pts na nota)",
        "tempo_prova_minutos": "Tempo (min)",
        "data": "Data",
    }
)
st.dataframe(view, width='stretch', hide_index=True)
st.caption(
    "\"Discursiva (bruto)\" é a nota na escala em que ela foi avaliada (ex.: 7 de 10 pela "
    "rubrica). \"Discursiva (pts na nota)\" é a conversão dessa nota para o peso configurado em "
    "Configurações — é o valor que efetivamente entra na \"Nota (0-1000)\"."
)

csv = view.to_csv(index=False).encode("utf-8")
st.download_button("Baixar histórico filtrado em CSV", csv, "historico_correcoes.csv", "text/csv")

# ---------------------------------------------------------------------------
# Horário de início e término em lote
# ---------------------------------------------------------------------------
st.subheader("Horário de início e término em lote")
st.caption(
    "Atribui o mesmo horário de início e término a todas as correções listadas nos filtros "
    "acima (por exemplo, escolha um simulado e/ou turma no topo da página). O tempo de prova "
    "de cada uma é recalculado. Depois, ajustes individuais continuam possíveis em Recorrigir."
)
with st.expander("Atribuir horário a todas as correções filtradas"):
    col_h1, col_h2 = st.columns(2)
    hora_ini_lote = col_h1.time_input("Início", value=dtime(8, 0), step=60, key="hist_lote_hora_ini")
    hora_fim_lote = col_h2.time_input("Término", value=dtime(10, 0), step=60, key="hist_lote_hora_fim")
    so_sem_horario = st.checkbox(
        "Aplicar apenas às correções que ainda não têm horário", value=True, key="hist_lote_so_sem"
    )
    alvo = df[df["hora_inicio"].isna() | (df["hora_inicio"] == "")] if so_sem_horario else df
    st.write(
        f"**{len(alvo)}** de {len(df)} correção(ões) serão atualizadas "
        f"({hora_ini_lote.strftime('%H:%M')} às {hora_fim_lote.strftime('%H:%M')} = "
        f"{calcular_tempo_prova_minutos(hora_ini_lote, hora_fim_lote):.0f} min)."
    )
    if filtro_simulado_id is None and not filtro_turma and not filtro_aluno:
        st.warning("Nenhum filtro aplicado: isto atingirá as correções de TODOS os simulados.")
    confirmar_horario = st.checkbox("Confirmo a atribuição em lote.", key="hist_lote_confirma")
    if st.button("Aplicar horário", disabled=not confirmar_horario or len(alvo) == 0, key="hist_lote_aplicar"):
        minutos = calcular_tempo_prova_minutos(hora_ini_lote, hora_fim_lote)
        for cid in alvo["id"]:
            update_correcao(
                int(cid),
                hora_inicio=hora_ini_lote.isoformat(),
                hora_fim=hora_fim_lote.isoformat(),
                tempo_prova_minutos=minutos,
            )
        st.success(f"Horário aplicado a {len(alvo)} correção(ões).")
        st.rerun()

# ---------------------------------------------------------------------------
# Correção em lote das discursivas cadastradas (com foto anexada)
# ---------------------------------------------------------------------------
st.subheader("Correção em lote das discursivas")
corrigir_discursivas_em_lote_ui(df, key_prefix="hist")

# ---------------------------------------------------------------------------
# Ver / avaliar (ou reavaliar) a resposta discursiva de uma correção
# ---------------------------------------------------------------------------
st.subheader("Questão discursiva")
st.caption(
    "Avalie agora a discursiva de uma correção que ainda não tem nota nela (por exemplo, "
    "salva em lote sem a discursiva), ou reveja/corrija uma já avaliada."
)

cfg = load_config()
opcoes_todas = {f"#{row.id} — {row.aluno} ({row.turma}) — {row.simulado}": row.id for row in df.itertuples()}
escolha_avaliar = st.selectbox("Correção", list(opcoes_todas.keys()), key="avaliar_discursiva_select")
correcao_id_avaliar = opcoes_todas[escolha_avaliar]
correcao_atual = get_correcao(correcao_id_avaliar)
simulado_da_correcao = get_simulado(correcao_atual["simulado_id"])

if correcao_atual["discursiva_pontos"] is not None:
    st.info(
        f"Esta correção já tem nota na discursiva: "
        f"{correcao_atual['discursiva_pontos']:.1f}/{correcao_atual['discursiva_pontos_max']:.0f}. "
        "Avaliar de novo abaixo substitui essa nota."
    )
elif correcao_atual["discursiva_imagem_path"]:
    st.info("Esta correção tem uma foto anexada, mas ainda não foi avaliada.")
else:
    st.info("Esta correção ainda não tem nenhuma foto da discursiva anexada.")

with st.expander("Avaliar / reavaliar a discursiva desta correção", expanded=False):
    avaliacao_disc = discursiva_grading_ui(
        simulado_da_correcao,
        key_prefix=f"historico_disc_{correcao_id_avaliar}",
        cfg=cfg,
        imagem_existente_path=correcao_atual["discursiva_imagem_path"],
    )

    pode_salvar_disc = avaliacao_disc["pontos"] is not None
    if st.button("Salvar avaliação da discursiva", disabled=not pode_salvar_disc, key=f"salvar_disc_{correcao_id_avaliar}"):
        if avaliacao_disc["usa_imagem_existente"]:
            caminho_final = correcao_atual["discursiva_imagem_path"]
        elif avaliacao_disc["imagem_bytes"] is not None:
            os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "discursivas"), exist_ok=True)
            caminho_final = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data", "discursivas", f"{uuid.uuid4().hex}.jpg"
            )
            with open(caminho_final, "wb") as f:
                f.write(avaliacao_disc["imagem_bytes"])
        else:
            caminho_final = correcao_atual["discursiva_imagem_path"]

        nova_nota = calcular_nota_1000(
            correcao_atual["acertos"], correcao_atual["n_questoes"],
            avaliacao_disc["pontos"], avaliacao_disc["pontos_max"],
            peso_discursiva_pontos=cfg["peso_discursiva_pontos"],
        )
        update_discursiva(
            correcao_id_avaliar,
            discursiva_pontos=avaliacao_disc["pontos"],
            discursiva_pontos_max=avaliacao_disc["pontos_max"],
            discursiva_avaliacao=avaliacao_disc["avaliacao"],
            discursiva_imagem_path=caminho_final,
            nota_1000=nova_nota["nota_1000"],
            discursiva_pontos_1000=nova_nota["pontos_discursiva_1000"],
        )
        st.success(
            f"Discursiva salva: {avaliacao_disc['pontos']:.1f}/{avaliacao_disc['pontos_max']:.0f} · "
            f"Nova nota (0-1000): {nova_nota['nota_1000']:.1f}"
        )
        st.rerun()

# ---------------------------------------------------------------------------
# Excluir uma correção
# ---------------------------------------------------------------------------
with st.expander("Excluir uma correção"):
    opcoes_correcao = {
        f"#{row.id} — {row.aluno} ({row.turma}) — {row.simulado}": row.id for row in df.itertuples()
    }
    escolha_correcao = st.selectbox("Correção", list(opcoes_correcao.keys()), key="del_correcao_select")
    correcao_id = opcoes_correcao[escolha_correcao]
    confirmar = st.checkbox("Confirmo que quero excluir esta correção.", key="del_correcao_confirm")
    if st.button("Excluir correção", disabled=not confirmar):
        delete_correcao(correcao_id)
        st.success("Correção excluída.")
        st.rerun()