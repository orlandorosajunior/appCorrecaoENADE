"""
Corretor de Gabarito - Simulado ENADE (ADS)
Pagina inicial. Use o menu a esquerda para navegar entre as paginas.
"""

import streamlit as st

from auth import exigir_login

from db import init_db, list_alunos, list_correcoes, list_simulados, list_turmas

st.set_page_config(page_title="Corretor de Gabarito ENADE", layout="wide")

exigir_login()

init_db()

st.title("Corretor de Gabarito — Simulado ENADE (ADS)")
st.caption(
    "Leitura óptica (OMR) do Cartão-Resposta oficial, com cadastro de simulados, gabaritos "
    "e histórico de correções por aluno e turma."
)

st.markdown(
    """
### Como usar

1. **Turmas e Alunos** — cadastre as turmas e os alunos (uma vez só) para depois só
   selecionar, em vez de redigitar nome/turma a cada correção.
2. **Simulados e Gabaritos** — cadastre um simulado e defina o gabarito oficial
   (preenchendo manualmente ou fotografando uma folha já preenchida com as respostas corretas).
3. **Corrigir Prova** — escolha o simulado, selecione (ou cadastre) o aluno, envie a
   foto/scan da folha preenchida, revise a leitura e salve a correção.
4. **Recorrigir** — reabra uma correção já salva para revisar ou corrigir qualquer campo
   (horário, respostas, discursiva) — útil também para reler o feedback que a IA deu ao aluno.
5. **Histórico** — consulte, filtre e exporte todas as correções já realizadas.
6. **Dashboard** — veja o rendimento por turma e por aluno, com média, mediana, desvio
   padrão, distribuição das notas, comparativos entre turmas e a correlação entre tempo
   de prova e nota.
7. **Exportar** — baixe os dados em CSV/Excel, filtrados por simulado, turma ou aluno,
   incluindo um boletim (aluno x simulado) por turma.
8. **Configurações** — salve sua chave de API do Gemini e os parâmetros padrão de
   leitura, para não precisar digitar tudo de novo a cada sessão.

Use o menu à esquerda para navegar entre as páginas.
"""
)

simulados = list_simulados()
correcoes = list_correcoes()
turmas = list_turmas()
alunos = list_alunos()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Simulados cadastrados", len(simulados))
col2.metric("Com gabarito definido", int(simulados["tem_gabarito"].sum()) if len(simulados) else 0)
col3.metric("Turmas", len(turmas))
col4.metric("Alunos", len(alunos))
col5.metric("Correções registradas", len(correcoes))

if len(simulados):
    st.subheader("Simulados cadastrados")
    view = simulados[["id", "nome", "n_questoes", "tem_gabarito", "data_criacao", "observacoes"]].rename(
        columns={
            "id": "ID",
            "nome": "Nome",
            "n_questoes": "Questões",
            "tem_gabarito": "Gabarito definido",
            "data_criacao": "Criado em",
            "observacoes": "Observações",
        }
    )
    st.dataframe(view, width='stretch', hide_index=True)
else:
    st.info("Nenhum simulado cadastrado ainda. Comece pela página **Simulados e Gabaritos**.")
