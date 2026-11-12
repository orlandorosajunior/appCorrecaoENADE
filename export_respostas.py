"""
export_respostas.py
Exportacao detalhada: como CADA aluno respondeu a CADA questao, com o objeto de
conhecimento do Enade associado a cada questao (cadastrado na pagina Simulados e
Gabaritos, "Temas das questoes").

- montar_respostas_detalhadas(df)   -> DataFrame "longo" (1 linha = aluno x questao)
- gerar_excel_respostas(long_df)    -> bytes de um .xlsx com varias abas
"""

import io
import json

import pandas as pd

from db import get_simulado
from enade_referencia import OBJETOS_ADS_ESPECIFICO, OBJETOS_FORMACAO_GERAL

SEM_TEMA = "(objeto não cadastrado)"

COLUNAS = [
    "Simulado", "Turma", "Aluno", "Questão", "Objeto de conhecimento (Enade)", "Componente",
    "Gabarito", "Resposta do aluno", "Resultado",
]


def _componente(tema: str) -> str:
    if tema in OBJETOS_FORMACAO_GERAL:
        return "Formação Geral"
    if tema in OBJETOS_ADS_ESPECIFICO:
        return "Componente Específico"
    return "—" if tema == SEM_TEMA else "Outro"


def montar_respostas_detalhadas(df: pd.DataFrame) -> pd.DataFrame:
    """`df`: correcoes no formato de db.list_correcoes(). Retorna uma linha por aluno x questao
    objetiva, usando o gabarito e os temas de CADA simulado."""
    cache = {}
    linhas = []
    for row in df.sort_values(["simulado", "turma", "aluno"], na_position="last").itertuples():
        if row.simulado_id not in cache:
            cache[row.simulado_id] = get_simulado(int(row.simulado_id))
        sim = cache[row.simulado_id]
        gab = sim.get("gabarito_dict") or {}
        temas = sim.get("temas_questoes_dict") or {}
        try:
            resp = json.loads(row.respostas) if row.respostas else {}
        except (TypeError, ValueError):
            resp = {}
        for q in sorted(gab, key=int):
            marcada = resp.get(q)
            correta = gab[q]
            tema = temas.get(q) or SEM_TEMA
            if not marcada:
                resultado, marcada_txt = "Em branco", ""
            else:
                marcada_txt = marcada
                resultado = "Certo" if marcada == correta else "Errado"
            linhas.append({
                "Simulado": row.simulado, "Turma": row.turma or "", "Aluno": row.aluno, "Questão": int(q),
                "Objeto de conhecimento (Enade)": tema, "Componente": _componente(tema),
                "Gabarito": correta, "Resposta do aluno": marcada_txt, "Resultado": resultado,
                "_simulado_id": int(row.simulado_id),
            })
    return pd.DataFrame(linhas)


def _resumo_questoes(long_df: pd.DataFrame) -> pd.DataFrame:
    g = long_df.groupby(["Simulado", "Questão", "Objeto de conhecimento (Enade)", "Componente", "Gabarito"], sort=False)
    rows = []
    for (sim, q, obj, comp, gab), d in g:
        n = len(d)
        linha = {
            "Simulado": sim, "Questão": q, "Objeto de conhecimento (Enade)": obj, "Componente": comp,
            "Gabarito": gab, "Alunos": n, "Acertos": int((d["Resultado"] == "Certo").sum()),
            "% de acerto": round(100 * (d["Resultado"] == "Certo").sum() / n, 1),
        }
        for a in "ABCDE":
            linha[f"Marcaram {a}"] = int((d["Resposta do aluno"] == a).sum())
        linha["Em branco"] = int((d["Resultado"] == "Em branco").sum())
        rows.append(linha)
    return pd.DataFrame(rows)


def _resumo_objetos(long_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (sim, obj, comp), d in long_df.groupby(["Simulado", "Objeto de conhecimento (Enade)", "Componente"], sort=False):
        rows.append({
            "Simulado": sim, "Objeto de conhecimento (Enade)": obj, "Componente": comp,
            "Questões": d["Questão"].nunique(), "Respostas": len(d),
            "Acertos": int((d["Resultado"] == "Certo").sum()),
            "% de acerto": round(100 * (d["Resultado"] == "Certo").sum() / len(d), 1),
        })
    return pd.DataFrame(rows).sort_values(["Simulado", "% de acerto"])


def gerar_excel_respostas(long_df: pd.DataFrame) -> bytes:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    verde = PatternFill("solid", fgColor="C6EFCE")
    vermelho = PatternFill("solid", fgColor="FFC7CE")
    cinza = PatternFill("solid", fgColor="E7E6E6")
    cab = PatternFill("solid", fgColor="4C72B0")

    buffer = io.BytesIO()
    publico = long_df[COLUNAS]
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        publico.to_excel(writer, index=False, sheet_name="Respostas por questão")
        _resumo_questoes(long_df).to_excel(writer, index=False, sheet_name="Resumo por questão")
        _resumo_objetos(long_df).to_excel(writer, index=False, sheet_name="Resumo por objeto")

        usados = set()
        for sim_id, d in long_df.groupby("_simulado_id", sort=False):
            nome_sim = d["Simulado"].iloc[0]
            aba = f"Matriz {nome_sim}"[:28]
            base, k = aba, 2
            while aba in usados:
                aba, k = f"{base[:25]} {k}", k + 1
            usados.add(aba)
            questoes = sorted(d["Questão"].unique())
            info = d.drop_duplicates("Questão").set_index("Questão")
            alunos = d[["Aluno", "Turma"]].drop_duplicates().itertuples(index=False)
            ws = writer.book.create_sheet(aba)
            ws.cell(1, 1, "Objeto de conhecimento →")
            ws.cell(2, 1, "Gabarito →")
            ws.cell(3, 1, "Aluno")
            ws.cell(3, 2, "Turma")
            for j, q in enumerate(questoes, start=3):
                ws.cell(1, j, info.loc[q, "Objeto de conhecimento (Enade)"]).alignment = Alignment(
                    text_rotation=90, vertical="bottom", wrap_text=True)
                ws.cell(2, j, info.loc[q, "Gabarito"]).alignment = Alignment(horizontal="center")
                c = ws.cell(3, j, f"Q{q}")
                c.alignment = Alignment(horizontal="center")
            for c in ws[3]:
                if c.value:
                    c.font = Font(bold=True, color="FFFFFF")
                    c.fill = cab
            ws.row_dimensions[1].height = 170
            por_aluno = {(a, t): g.set_index("Questão") for (a, t), g in d.groupby(["Aluno", "Turma"], sort=False)}
            for i, (aluno, turma) in enumerate(alunos, start=4):
                ws.cell(i, 1, aluno)
                ws.cell(i, 2, turma)
                g = por_aluno[(aluno, turma)]
                for j, q in enumerate(questoes, start=3):
                    if q not in g.index:
                        continue
                    res = g.loc[q, "Resultado"]
                    cel = ws.cell(i, j, g.loc[q, "Resposta do aluno"] or "–")
                    cel.alignment = Alignment(horizontal="center")
                    cel.fill = verde if res == "Certo" else (vermelho if res == "Errado" else cinza)
            ws.column_dimensions["A"].width = 32
            ws.column_dimensions["B"].width = 16
            for j in range(3, 3 + len(questoes)):
                ws.column_dimensions[get_column_letter(j)].width = 5
            ws.freeze_panes = "C4"

        for nome in ("Respostas por questão", "Resumo por questão", "Resumo por objeto"):
            ws = writer.sheets[nome]
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = cab
            for col in ws.columns:
                largura = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, largura + 2), 60)
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
    return buffer.getvalue()
