"""
Pagina: Dashboard - rendimento por turma e por aluno, com indicadores
estatisticos (media, desvio padrao, mediana, distribuicao/gaussiana) e
correlacao entre tempo de prova e nota.
"""

import json

import pandas as pd
import streamlit as st

from auth import exigir_login

from db import get_simulado, init_db, list_alunos, list_correcoes, list_simulados, list_turmas
from stats_utils import (
    grafico_barras_comparativo,
    grafico_boxplot_por_grupo,
    grafico_dispersao_tempo_nota,
    grafico_histograma_gaussiana,
    grafico_pizza_status,
    grafico_ranking_extremos,
    resumo_estatistico,
)
st.set_page_config(page_title="Dashboard", layout="wide")

exigir_login()
init_db()

st.title("Dashboard")
st.caption(
    "Indicadores calculados sobre a nota na escala 0-1000 (conversão proporcional simples — "
    "ver observação na página Corrigir Prova / README)."
)

df_todas = list_correcoes()
if len(df_todas) == 0:
    st.info("Nenhuma correção registrada ainda.")
    st.stop()

simulados_df = list_simulados()
turmas_df = list_turmas()

# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)
opcoes_simulado = {"Todos os simulados": None}
opcoes_simulado.update({f"#{row.id} — {row.nome}": row.id for row in simulados_df.itertuples()})
escolha_simulado = col1.selectbox("Simulado", list(opcoes_simulado.keys()))
filtro_simulado_id = opcoes_simulado[escolha_simulado]

opcoes_turma = {"Todas as turmas": None}
opcoes_turma.update({row.nome: row.id for row in turmas_df.itertuples()})
escolha_turma = col2.selectbox("Turma", list(opcoes_turma.keys()))
filtro_turma_id = opcoes_turma[escolha_turma]

df = list_correcoes(simulado_id=filtro_simulado_id, turma_id=filtro_turma_id)
if len(df) == 0:
    st.info("Nenhuma correção encontrada com esses filtros.")
    st.stop()

tab_turma, tab_aluno, tab_ranking, tab_discursiva, tab_questoes, tab_tempo = st.tabs(
    ["Por turma", "Por aluno", "Ranking", "Discursiva", "Questões", "Tempo x Nota"]
)

# ---------------------------------------------------------------------------
# Por turma
# ---------------------------------------------------------------------------
with tab_turma:
    st.subheader("Rendimento por turma")

    resumo_geral = resumo_estatistico(df["nota_1000"])
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Correções", resumo_geral["n"])
    col_b.metric("Média", resumo_geral["media"] if resumo_geral["media"] is not None else "—")
    col_c.metric("Mediana", resumo_geral["mediana"] if resumo_geral["mediana"] is not None else "—")
    col_d.metric("Desvio padrão", resumo_geral["desvio_padrao"] if resumo_geral["desvio_padrao"] is not None else "—")

    fig = grafico_histograma_gaussiana(df["nota_1000"], "Distribuição das notas (0-1000)", xlabel="Nota (0-1000)")
    if fig is not None:
        st.pyplot(fig)
    else:
        st.caption("Poucos dados para desenhar a distribuição (mínimo 2 correções com nota calculada).")

    st.markdown("**Comparativo entre turmas** (dentro do filtro de simulado escolhido acima):")
    linhas_turma = []
    for turma_nome, grupo in df.groupby("turma", dropna=False):
        s = resumo_estatistico(grupo["nota_1000"])
        linhas_turma.append(
            {
                "Turma": turma_nome or "—",
                "Correções": s["n"],
                "Média": s["media"],
                "Mediana": s["mediana"],
                "Desvio padrão": s["desvio_padrao"],
                "Mínimo": s["minimo"],
                "Máximo": s["maximo"],
            }
        )
    st.dataframe(
        pd.DataFrame(linhas_turma).sort_values("Média", ascending=False, na_position="last"),
        width='stretch',
        hide_index=True,
    )

    if df["turma"].nunique(dropna=True) >= 2:
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_barras = grafico_barras_comparativo(
                [l["Turma"] for l in linhas_turma],
                [l["Média"] for l in linhas_turma],
                "Média por turma",
            )
            if fig_barras is not None:
                st.pyplot(fig_barras)
        with col_g2:
            fig_box = grafico_boxplot_por_grupo(df, "turma", "nota_1000", "Distribuição por turma")
            if fig_box is not None:
                st.pyplot(fig_box)
    else:
        st.caption("Compare duas ou mais turmas (ajuste o filtro acima) para ver os gráficos comparativos.")

# ---------------------------------------------------------------------------
# Por aluno
# ---------------------------------------------------------------------------
with tab_aluno:
    st.subheader("Rendimento por aluno")

    alunos_com_correcao = sorted(df["aluno"].dropna().unique().tolist())
    if not alunos_com_correcao:
        st.info("Nenhum aluno com correção nesse filtro.")
    else:
        aluno_escolhido = st.selectbox("Aluno", alunos_com_correcao)
        df_aluno = df[df["aluno"] == aluno_escolhido].sort_values("data")

        s = resumo_estatistico(df_aluno["nota_1000"])
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Correções deste aluno", s["n"])
        col_b.metric("Média", s["media"] if s["media"] is not None else "—")
        col_c.metric(
            "Desvio padrão",
            s["desvio_padrao"] if s["desvio_padrao"] is not None else "— (só 1 correção)",
        )

        view_aluno = df_aluno[["simulado", "nota", "nota_1000", "acertos", "n_questoes", "tempo_prova_minutos", "data"]].rename(
            columns={
                "simulado": "Simulado",
                "nota": "Nota objetiva (%)",
                "nota_1000": "Nota (0-1000)",
                "acertos": "Acertos",
                "n_questoes": "Questões",
                "tempo_prova_minutos": "Tempo (min)",
                "data": "Data",
            }
        )
        st.dataframe(view_aluno, width='stretch', hide_index=True)

        if len(df_aluno) >= 2:
            st.line_chart(df_aluno.set_index("data")["nota_1000"], y_label="Nota (0-1000)")
        else:
            st.caption("Com apenas uma correção ainda não há evolução para mostrar em gráfico.")

# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
with tab_ranking:
    st.subheader("Melhores e piores alunos")
    st.caption(
        "Quando o filtro de simulado está em \"Todos\", usa a média de cada aluno entre todos os "
        "simulados que ele fez (dentro do filtro de turma escolhido)."
    )

    por_aluno = df.groupby("aluno", dropna=True)["nota_1000"].mean().dropna()
    if len(por_aluno) == 0:
        st.info("Nenhum aluno com nota calculada nesse filtro.")
    else:
        top_n = st.slider("Quantos melhores/piores mostrar", 3, 10, 5, key="ranking_top_n")
        fig_ranking = grafico_ranking_extremos(
            por_aluno.index.tolist(), por_aluno.values.tolist(), "Melhores e piores alunos", top_n=top_n
        )
        if fig_ranking is not None:
            st.pyplot(fig_ranking)

        with st.expander("Ver ranking completo"):
            ranking_completo = por_aluno.sort_values(ascending=False).round(1).reset_index()
            ranking_completo.columns = ["Aluno", "Nota (0-1000)"]
            ranking_completo.insert(0, "Posição", range(1, len(ranking_completo) + 1))
            st.dataframe(ranking_completo, width='stretch', hide_index=True)

# ---------------------------------------------------------------------------
# Discursiva
# ---------------------------------------------------------------------------
with tab_discursiva:
    st.subheader("Desempenho na questão discursiva (32)")

    df_disc = df.dropna(subset=["discursiva_pontos", "discursiva_pontos_max"]).copy()
    st.caption(
        f"{len(df_disc)} de {len(df)} correção(ões) do filtro atual têm a discursiva avaliada. "
        "Sem escolher um simulado específico no filtro do topo, os números abaixo somam todos os "
        "simulados aplicados (dentro da turma filtrada)."
    )

    if len(df_disc) == 0:
        st.info("Nenhuma correção com a discursiva avaliada, nesse filtro.")
    else:
        df_disc["discursiva_percentual"] = 100 * df_disc["discursiva_pontos"] / df_disc["discursiva_pontos_max"]

        resumo_disc = resumo_estatistico(df_disc["discursiva_percentual"])
        col_d1, col_d2, col_d3, col_d4 = st.columns(4)
        col_d1.metric("Avaliadas", resumo_disc["n"])
        col_d2.metric("Aproveitamento médio", f"{resumo_disc['media']:.0f}%" if resumo_disc["media"] is not None else "—")
        col_d3.metric("Mediana", f"{resumo_disc['mediana']:.0f}%" if resumo_disc["mediana"] is not None else "—")
        col_d4.metric(
            "Desvio padrão",
            f"{resumo_disc['desvio_padrao']:.0f} p.p." if resumo_disc["desvio_padrao"] is not None else "—",
        )

        if df_disc["discursiva_pontos_1000"].notna().any():
            media_pts_1000 = df_disc["discursiva_pontos_1000"].dropna().mean()
            st.caption(
                f"Em pontos de 1000 (com o peso configurado no momento de cada correção): "
                f"média de {media_pts_1000:.1f} pontos ganhos na discursiva."
            )

        fig_disc = grafico_histograma_gaussiana(
            df_disc["discursiva_percentual"], "Distribuição do aproveitamento na discursiva",
            xlabel="Aproveitamento (%)",
        )
        if fig_disc is not None:
            st.pyplot(fig_disc)
        else:
            st.caption("Poucos dados para desenhar a distribuição (mínimo 2 correções avaliadas).")

        if df_disc["turma"].nunique(dropna=True) >= 2:
            st.markdown("**Comparativo entre turmas**")
            linhas_turma_disc = []
            for turma_nome, grupo in df_disc.groupby("turma", dropna=False):
                s = resumo_estatistico(grupo["discursiva_percentual"])
                linhas_turma_disc.append(
                    {"Turma": turma_nome or "—", "Avaliadas": s["n"], "Média (%)": s["media"], "Mediana (%)": s["mediana"]}
                )
            st.dataframe(
                pd.DataFrame(linhas_turma_disc).sort_values("Média (%)", ascending=False, na_position="last"),
                width='stretch',
                hide_index=True,
            )
            fig_barras_disc = grafico_barras_comparativo(
                [l["Turma"] for l in linhas_turma_disc],
                [l["Média (%)"] for l in linhas_turma_disc],
                "Aproveitamento médio na discursiva, por turma",
                ylabel="Aproveitamento (%)",
            )
            if fig_barras_disc is not None:
                st.pyplot(fig_barras_disc)

        st.markdown("**Por aluno**")
        alunos_disc = sorted(df_disc["aluno"].dropna().unique().tolist())
        if alunos_disc:
            aluno_disc_escolhido = st.selectbox("Aluno", alunos_disc, key="disc_aluno_select")
            df_aluno_disc = df_disc[df_disc["aluno"] == aluno_disc_escolhido].sort_values("data")
            view_aluno_disc = df_aluno_disc[
                ["simulado", "discursiva_pontos", "discursiva_pontos_max", "discursiva_percentual",
                 "discursiva_pontos_1000", "data"]
            ].rename(
                columns={
                    "simulado": "Simulado",
                    "discursiva_pontos": "Pontos (bruto)",
                    "discursiva_pontos_max": "Máximo (bruto)",
                    "discursiva_percentual": "Aproveitamento (%)",
                    "discursiva_pontos_1000": "Pts na nota (1000)",
                    "data": "Data",
                }
            )
            st.dataframe(view_aluno_disc, width='stretch', hide_index=True)
            if len(df_aluno_disc) >= 2:
                media_aluno = df_aluno_disc["discursiva_percentual"].mean()
                st.caption(f"Aproveitamento médio deste aluno na discursiva: {media_aluno:.0f}%.")

# ---------------------------------------------------------------------------
# Questões
# ---------------------------------------------------------------------------
with tab_questoes:
    st.subheader("Desempenho nas questões")

    if filtro_simulado_id is None:
        st.info("Escolha um simulado específico no filtro acima para ver o desempenho por questão.")
    else:
        simulado_sel = get_simulado(filtro_simulado_id)
        gabarito = simulado_sel["gabarito_dict"]
        if not gabarito:
            st.info("Este simulado ainda não tem gabarito definido.")
        else:
            certos = errados = brancos = 0
            acertos_por_questao = {q: 0 for q in gabarito}
            for respostas_json in df["respostas"]:
                respostas = json.loads(respostas_json)
                for q, correta in gabarito.items():
                    marcada = respostas.get(q)
                    if marcada == correta:
                        certos += 1
                        acertos_por_questao[q] += 1
                    elif marcada is None or marcada == "":
                        brancos += 1
                    else:
                        errados += 1

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                fig_pizza = grafico_pizza_status(
                    {"Certo": certos, "Errado": errados, "Em branco": brancos},
                    "Desempenho geral (todas as questões, todos os alunos)",
                )
                if fig_pizza is not None:
                    st.pyplot(fig_pizza)

            with col_p2:
                total = len(df)
                serie = pd.Series(
                    {int(q): 100 * acertos_por_questao[q] / total for q in sorted(gabarito, key=int)}
                )
                serie.index.name = "Questão"
                st.markdown("**Percentual de acerto por questão**")
                st.bar_chart(serie)
                piores = serie.sort_values().head(5)
                st.caption(
                    "Questões com menor % de acerto: "
                    + ", ".join(f"Q{q} ({v:.0f}%)" for q, v in piores.items())
                )

# ---------------------------------------------------------------------------
# Tempo x Nota
# ---------------------------------------------------------------------------
with tab_tempo:
    st.subheader("Correlação entre tempo de prova e nota")
    st.caption(
        "Só entram aqui as correções com horário de início e término preenchidos na tela de "
        "Corrigir Prova."
    )

    df_tempo = df.dropna(subset=["tempo_prova_minutos", "nota_1000"])
    if len(df_tempo) < 3:
        st.info(
            f"Só {len(df_tempo)} correção(ões) com horário registrado nesse filtro — são "
            "necessárias pelo menos 3 para calcular uma correlação com algum sentido."
        )
    else:
        fig2, coef = grafico_dispersao_tempo_nota(
            df_tempo["tempo_prova_minutos"], df_tempo["nota_1000"], "Tempo de prova x Nota"
        )
        st.pyplot(fig2)

        if coef > 0.3:
            interpretacao = "quem demorou mais tende a ter tirado nota mais alta."
        elif coef < -0.3:
            interpretacao = "quem demorou mais tende a ter tirado nota mais baixa."
        else:
            interpretacao = "não há uma relação clara entre tempo de prova e nota, neste filtro."
        st.caption(f"Coeficiente de correlação de Pearson: {coef:.2f} — {interpretacao}")

        col_a, col_b = st.columns(2)
        col_a.metric("Tempo médio de prova", f"{df_tempo['tempo_prova_minutos'].mean():.0f} min")
        col_b.metric("Correções com horário", len(df_tempo))
