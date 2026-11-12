"""
Pagina: Exportar - baixa os dados das correcoes filtrados por simulado,
turma e/ou aluno, em CSV ou Excel, alem de um boletim (aluno x simulado)
por turma.
"""

import io
import json

import pandas as pd
import streamlit as st

from auth import exigir_login

from db import get_simulado, init_db, list_correcoes, list_simulados, list_turmas
from export_respostas import COLUNAS as COLUNAS_RESPOSTAS, gerar_excel_respostas, montar_respostas_detalhadas
from pdf_reports import SECOES_RELATORIO_GERAL, gerar_pdf_relatorio_geral, gerar_pdf_turma


def _historico_do_aluno(row):
    """Evolucao do aluno em todos os simulados em que ele tem correcao (ordem cronologica)."""
    if pd.notna(row.get("aluno_id")):
        dfa = list_correcoes(aluno_id=int(row["aluno_id"]))
    else:
        dfa = list_correcoes(aluno=row["aluno"], turma=row["turma"])
        dfa = dfa[dfa["aluno"] == row["aluno"]]
    dfa = dfa.sort_values("data")
    # um ponto por simulado (a correcao mais recente de cada)
    dfa = dfa.drop_duplicates(subset="simulado_id", keep="last").sort_values("data")
    saida = []
    for _, r in dfa.iterrows():
        if pd.isna(r["nota_1000"]):
            continue
        disc = float(r["discursiva_pontos_1000"]) if pd.notna(r["discursiva_pontos_1000"]) else 0.0
        saida.append({
            "simulado_id": int(r["simulado_id"]),
            "simulado": r["simulado"],
            "objetivas_1000": max(float(r["nota_1000"]) - disc, 0.0),
            "discursiva_1000": disc,
            "nota_1000": float(r["nota_1000"]),
        })
    return saida

st.set_page_config(page_title="Exportar", layout="wide")

exigir_login()
init_db()

st.title("Exportar dados")
st.caption("Baixe os dados das correções filtrados por simulado, turma e/ou aluno — em CSV ou Excel.")

simulados_df = list_simulados()
turmas_df = list_turmas()

col1, col2, col3 = st.columns(3)

opcoes_simulado = {"Todos": None}
opcoes_simulado.update({f"#{row.id} — {row.nome}": row.id for row in simulados_df.itertuples()})
escolha_simulado = col1.selectbox("Simulado", list(opcoes_simulado.keys()))
filtro_simulado_id = opcoes_simulado[escolha_simulado]

opcoes_turma = {"Todas": None}
opcoes_turma.update({row.nome: row.id for row in turmas_df.itertuples()})
escolha_turma = col2.selectbox("Turma", list(opcoes_turma.keys()))
filtro_turma_id = opcoes_turma[escolha_turma]

filtro_aluno = col3.text_input("Aluno contém (opcional)")

df = list_correcoes(simulado_id=filtro_simulado_id, turma_id=filtro_turma_id, aluno=filtro_aluno or None)

if len(df) == 0:
    st.info("Nenhuma correção encontrada com esses filtros.")
    st.stop()

st.caption(f"{len(df)} correção(ões) encontrada(s) com esses filtros.")

# ---------------------------------------------------------------------------
# Dados detalhados
# ---------------------------------------------------------------------------
st.subheader("Dados detalhados")

view = df[[
    "simulado", "aluno", "turma", "acertos", "n_questoes", "nota", "nota_1000",
    "discursiva_pontos", "discursiva_pontos_max", "tempo_prova_minutos", "data",
]].rename(
    columns={
        "simulado": "Simulado",
        "aluno": "Aluno",
        "turma": "Turma",
        "acertos": "Acertos",
        "n_questoes": "Questões",
        "nota": "Nota objetiva (%)",
        "nota_1000": "Nota (0-1000)",
        "discursiva_pontos": "Discursiva",
        "discursiva_pontos_max": "Discursiva (máx)",
        "tempo_prova_minutos": "Tempo (min)",
        "data": "Data",
    }
)
st.dataframe(view, width='stretch', hide_index=True)

col_csv, col_xlsx = st.columns(2)

csv_bytes = view.to_csv(index=False).encode("utf-8")
col_csv.download_button("Baixar CSV", csv_bytes, "correcoes_exportadas.csv", "text/csv")

buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    view.to_excel(writer, index=False, sheet_name="Correções")
col_xlsx.download_button(
    "Baixar Excel",
    buffer.getvalue(),
    "correcoes_exportadas.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# ---------------------------------------------------------------------------
# Respostas por aluno e por questão (com objeto de conhecimento do Enade)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Respostas de cada aluno por questão")
st.caption(
    "Segundo relatório, com uma linha por aluno e por questão: a alternativa marcada, o gabarito, "
    "o resultado (certo/errado/em branco) e o **objeto de conhecimento do Enade** associado à "
    "questão (cadastrado em Simulados e Gabaritos → Temas das questões). Segue os filtros acima. "
    "O Excel traz também a matriz aluno x questão colorida, e resumos por questão e por objeto."
)
with st.spinner("Montando respostas detalhadas..."):
    detalhe = montar_respostas_detalhadas(df)
if len(detalhe) == 0:
    st.info("Os simulados filtrados ainda não têm gabarito cadastrado.")
else:
    sem_tema = int((detalhe["Objeto de conhecimento (Enade)"] == "(objeto não cadastrado)").sum())
    if sem_tema:
        st.warning(
            f"{sem_tema} linha(s) estão sem objeto de conhecimento — cadastre os temas das questões em "
            "Simulados e Gabaritos para preenchê-los."
        )
    st.dataframe(detalhe[COLUNAS_RESPOSTAS].head(200), width='stretch', hide_index=True)
    if len(detalhe) > 200:
        st.caption(f"Mostrando as 200 primeiras de {len(detalhe)} linhas; o arquivo baixado tem todas.")
    col_rcsv, col_rxlsx = st.columns(2)
    col_rcsv.download_button(
        "Baixar respostas por questão (CSV)",
        detalhe[COLUNAS_RESPOSTAS].to_csv(index=False, sep=";").encode("utf-8-sig"),
        "respostas_por_questao.csv", "text/csv", key="resp_csv",
    )
    col_rxlsx.download_button(
        "Baixar respostas por questão (Excel)",
        gerar_excel_respostas(detalhe),
        "respostas_por_questao.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="resp_xlsx",
    )

# ---------------------------------------------------------------------------
# Boletim por turma (aluno x simulado)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Boletim por turma (aluno x simulado)")

if filtro_turma_id is None:
    st.info("Escolha uma turma específica no filtro acima para gerar o boletim.")
else:
    df_boletim = list_correcoes(turma_id=filtro_turma_id)
    if len(df_boletim) == 0:
        st.info("Nenhuma correção para esta turma ainda.")
    else:
        pivot = df_boletim.pivot_table(index="aluno", columns="simulado", values="nota_1000", aggfunc="first")
        pivot["Média"] = pivot.mean(axis=1, numeric_only=True).round(1)
        pivot = pivot.round(1).sort_values("Média", ascending=False)
        st.dataframe(pivot, width='stretch')

        col_bcsv, col_bxlsx = st.columns(2)
        csv_boletim = pivot.reset_index().rename(columns={"aluno": "Aluno"}).to_csv(index=False).encode("utf-8")
        col_bcsv.download_button(
            "Baixar boletim em CSV", csv_boletim, f"boletim_{escolha_turma}.csv", "text/csv", key="boletim_csv"
        )

        buffer2 = io.BytesIO()
        with pd.ExcelWriter(buffer2, engine="openpyxl") as writer:
            pivot.reset_index().rename(columns={"aluno": "Aluno"}).to_excel(
                writer, index=False, sheet_name="Boletim"
            )
        col_bxlsx.download_button(
            "Baixar boletim em Excel",
            buffer2.getvalue(),
            f"boletim_{escolha_turma}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="boletim_xlsx",
        )

# ---------------------------------------------------------------------------
# Feedback em PDF, aluno a aluno (para imprimir e entregar)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Feedback em PDF (um relatório por aluno)")
st.caption(
    "Gera um PDF com uma página de resultado por aluno de uma turma, num simulado específico — "
    "com a nota, um gráfico mostrando onde a nota dele fica na distribuição da turma, sugestão "
    "dos temas mais errados (se você cadastrou os temas das questões em Simulados e Gabaritos), "
    "o feedback da discursiva e a comparação resposta x gabarito. Pronto para imprimir e entregar."
)

if filtro_simulado_id is None or filtro_turma_id is None:
    st.info("Escolha um simulado E uma turma específicos nos filtros acima para gerar o PDF.")
else:
    df_pdf = list_correcoes(simulado_id=filtro_simulado_id, turma_id=filtro_turma_id)
    if len(df_pdf) == 0:
        st.info("Nenhuma correção encontrada para esse simulado e essa turma.")
    else:
        sem_discursiva = int(df_pdf["discursiva_pontos"].isna().sum())
        if sem_discursiva:
            st.warning(
                f"{sem_discursiva} de {len(df_pdf)} aluno(s) ainda não têm a questão discursiva "
                "avaliada — o PDF vai mostrar \"ainda não avaliada\" para eles. Avalie antes (em "
                "Corrigir Prova ou Recorrigir) se quiser o feedback completo."
            )

        if st.button(f"Gerar PDF com {len(df_pdf)} aluno(s)", type="primary"):
            simulado_completo = get_simulado(filtro_simulado_id)
            alunos_data = []
            for _, row in df_pdf.sort_values("aluno").iterrows():
                discursiva_avaliacao = json.loads(row["discursiva_avaliacao"]) if pd.notna(row["discursiva_avaliacao"]) else None
                alunos_data.append(
                    {
                        "aluno": row["aluno"],
                        "acertos": row["acertos"],
                        "n_questoes": row["n_questoes"],
                        "nota": row["nota"],
                        "nota_1000": row["nota_1000"],
                        "respostas": json.loads(row["respostas"]) if row["respostas"] else {},
                        "discursiva_pontos": row["discursiva_pontos"] if pd.notna(row["discursiva_pontos"]) else None,
                        "discursiva_pontos_max": row["discursiva_pontos_max"] if pd.notna(row["discursiva_pontos_max"]) else None,
                        "discursiva_avaliacao": discursiva_avaliacao,
                        "tempo_prova_minutos": row["tempo_prova_minutos"] if pd.notna(row["tempo_prova_minutos"]) else None,
                        "historico": _historico_do_aluno(row),
                    }
                )
            with st.spinner(f"Gerando PDF de {len(alunos_data)} aluno(s)..."):
                pdf_bytes = gerar_pdf_turma(escolha_turma, simulado_completo, alunos_data)
            st.success("PDF gerado.")
            st.download_button(
                "Baixar PDF de feedback da turma",
                pdf_bytes,
                f"feedback_{escolha_turma}_{simulado_completo['nome']}.pdf".replace(" ", "_"),
                "application/pdf",
            )

# ---------------------------------------------------------------------------
# Relatório Geral em PDF (visão geral, não por aluno)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Relatório Geral (PDF)")
st.caption(
    "Gera um PDF de visão geral com os itens do Dashboard, para o filtro escolhido acima. "
    "Marque abaixo só as seções que quer incluir no PDF."
)

st.markdown("**Seções a incluir:**")
col_marcar1, col_marcar2 = st.columns(2)
if col_marcar1.button("Marcar todas"):
    for chave, _ in SECOES_RELATORIO_GERAL:
        st.session_state[f"secao_pdf_{chave}"] = True
if col_marcar2.button("Desmarcar todas"):
    for chave, _ in SECOES_RELATORIO_GERAL:
        st.session_state[f"secao_pdf_{chave}"] = False

secoes_selecionadas = {}
cols_secoes = st.columns(2)
for i, (chave, rotulo) in enumerate(SECOES_RELATORIO_GERAL):
    with cols_secoes[i % 2]:
        secoes_selecionadas[chave] = st.checkbox(rotulo, value=True, key=f"secao_pdf_{chave}")

st.caption(
    "\"Desempenho por questão objetiva\" e \"Desempenho por objeto de conhecimento\" só entram "
    "no PDF com um simulado específico selecionado no filtro (precisam do gabarito dele); o mesmo vale para dificuldade/discriminação, distratores, confiabilidade e Formação Geral x Específico. A "
    "\"Evolução individual\" ignora o filtro de simulado (usa todos os simulados da turma/aluno filtrados)."
)

top_n_relatorio = st.slider("Quantos melhores/piores mostrar no ranking do relatório", 3, 10, 5)

col_r1, col_r2 = st.columns(2)
corte_risco = col_r1.number_input(
    "Alunos em risco: nota de corte (0-1000)", 0, 1000, 600, step=50,
    help="Entram na lista os alunos cuja última nota está abaixo deste valor.",
)
queda_risco = col_r2.number_input(
    "Alunos em risco: queda mínima entre simulados (pontos)", 10, 500, 50, step=10,
    help="Também entram os alunos que caíram pelo menos isto em relação ao simulado anterior.",
)

nenhuma_secao_marcada = not any(secoes_selecionadas.values())
if nenhuma_secao_marcada:
    st.info("Marque pelo menos uma seção acima para gerar o relatório.")

if st.button("Gerar Relatório Geral em PDF", type="primary", disabled=nenhuma_secao_marcada):
    simulado_para_relatorio = get_simulado(filtro_simulado_id) if filtro_simulado_id else None
    descricao_filtro = (
        f"Simulado: {escolha_simulado} | Turma: {escolha_turma}"
        + (f" | Aluno contém: \"{filtro_aluno}\"" if filtro_aluno else "")
        + f" | Gerado em {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}"
    )
    with st.spinner("Gerando relatório..."):
        pdf_geral_bytes = gerar_pdf_relatorio_geral(
            descricao_filtro, df, simulado=simulado_para_relatorio,
            top_n_ranking=top_n_relatorio, secoes=secoes_selecionadas,
            df_evolucao=list_correcoes(turma_id=filtro_turma_id, aluno=filtro_aluno or None),
            corte_risco=float(corte_risco), queda_risco=float(queda_risco),
        )
    st.success("Relatório gerado.")
    st.download_button(
        "Baixar Relatório Geral em PDF",
        pdf_geral_bytes,
        "relatorio_geral.pdf",
        "application/pdf",
    )
