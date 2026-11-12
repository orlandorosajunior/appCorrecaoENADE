"""
stats_utils.py
Indicadores estatisticos e graficos usados na pagina de Dashboard:
media, desvio padrao, mediana, histograma com curva normal ("gaussiana")
sobreposta, e dispersao tempo de prova x nota com coeficiente de correlacao.
"""

import matplotlib

matplotlib.use("Agg")  # backend sem interface grafica (necessario no Streamlit)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def resumo_estatistico(valores: pd.Series) -> dict:
    """
    Retorna media, desvio padrao (amostral), mediana e n a partir de uma
    serie numerica (ja sem NaN). Com menos de 2 valores, desvio padrao vem
    como None (nao ha variancia amostral definida).
    """
    valores = valores.dropna()
    n = len(valores)
    if n == 0:
        return {"n": 0, "media": None, "desvio_padrao": None, "mediana": None, "minimo": None, "maximo": None}
    return {
        "n": n,
        "media": round(float(valores.mean()), 1),
        "desvio_padrao": round(float(valores.std(ddof=1)), 1) if n > 1 else None,
        "mediana": round(float(valores.median()), 1),
        "minimo": round(float(valores.min()), 1),
        "maximo": round(float(valores.max()), 1),
    }


def grafico_histograma_gaussiana(valores: pd.Series, titulo: str, xlabel: str = "Nota"):
    """
    Desenha um histograma dos valores com a curva normal (gaussiana) de
    mesma media/desvio padrão sobreposta, para visualizar o quanto a
    distribuição real se aproxima de uma distribuição normal.
    Retorna a figura do matplotlib (ou None se não houver dados suficientes).
    """
    valores = valores.dropna()
    if len(valores) < 2:
        return None

    media = valores.mean()
    desvio = valores.std(ddof=1)

    fig, ax = plt.subplots(figsize=(7, 4))
    n_bins = min(max(len(valores) // 2, 5), 20)
    ax.hist(valores, bins=n_bins, density=True, alpha=0.6, color="#4C72B0", edgecolor="white")

    if desvio > 0:
        x = np.linspace(valores.min(), valores.max(), 200)
        pdf = (1 / (desvio * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - media) / desvio) ** 2)
        ax.plot(x, pdf, color="#C44E52", linewidth=2, label=f"Normal (μ={media:.1f}, σ={desvio:.1f})")
        ax.legend()

    ax.set_title(titulo)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Densidade")
    fig.tight_layout()
    return fig


def grafico_dispersao_tempo_nota(tempos: pd.Series, notas: pd.Series, titulo: str,
                                  xlabel: str = "Tempo de prova (min)", ylabel: str = "Nota"):
    """
    Desenha um gráfico de dispersão tempo de prova x nota, com o
    coeficiente de correlação de Pearson no título. Retorna (figura,
    coeficiente_correlacao) ou (None, None) se não houver dados suficientes
    (pelo menos 3 pares completos, para o coeficiente ter algum sentido).
    """
    df = pd.DataFrame({"tempo": tempos, "nota": notas}).dropna()
    if len(df) < 3:
        return None, None

    coef = float(df["tempo"].corr(df["nota"]))

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(df["tempo"], df["nota"], alpha=0.7, color="#4C72B0", edgecolor="white")

    if df["tempo"].std() > 0:
        coef_lin = np.polyfit(df["tempo"], df["nota"], 1)
        x_linha = np.linspace(df["tempo"].min(), df["tempo"].max(), 50)
        ax.plot(x_linha, np.polyval(coef_lin, x_linha), color="#C44E52", linewidth=2)

    ax.set_title(f"{titulo} (correlação de Pearson: {coef:.2f})")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    return fig, coef


def grafico_barras_comparativo(labels, valores, titulo: str, ylabel: str = "Nota (0-1000)"):
    """
    Barras simples comparando um valor (ex.: média) entre grupos (ex.: turmas).
    Retorna a figura, ou None se não houver nenhum valor.
    """
    pares = [(l, v) for l, v in zip(labels, valores) if v is not None and not pd.isna(v)]
    if not pares:
        return None
    pares.sort(key=lambda p: p[1], reverse=True)
    labels_ord, valores_ord = zip(*pares)

    fig, ax = plt.subplots(figsize=(7, 4))
    cores = plt.cm.Blues(np.linspace(0.9, 0.4, len(labels_ord)))
    barras = ax.bar(labels_ord, valores_ord, color=cores, edgecolor="white")
    ax.bar_label(barras, fmt="%.0f", padding=3)
    ax.set_title(titulo)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    return fig


def grafico_boxplot_por_grupo(df: pd.DataFrame, coluna_grupo: str, coluna_valor: str, titulo: str,
                               ylabel: str = "Nota (0-1000)"):
    """
    Boxplot comparando a distribuição de `coluna_valor` entre os grupos de
    `coluna_grupo` (ex.: nota_1000 por turma) — mostra mediana, quartis e
    dispersão de cada grupo lado a lado. Retorna None se não houver ao
    menos 2 grupos com dados.
    """
    grupos = {}
    for nome, sub in df.dropna(subset=[coluna_valor]).groupby(coluna_grupo, dropna=False):
        if len(sub) > 0:
            grupos[str(nome)] = sub[coluna_valor].values

    if len(grupos) < 2:
        return None

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.boxplot(grupos.values(), tick_labels=list(grupos.keys()), patch_artist=True,
               boxprops=dict(facecolor="#4C72B0", alpha=0.6),
               medianprops=dict(color="#C44E52", linewidth=2))
    ax.set_title(titulo)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    return fig


def grafico_desempenho_por_tema(percentuais: dict, titulo: str, xlabel: str = "% de acerto"):
    """
    Barras horizontais com o percentual de acerto por tema/objeto de
    conhecimento, ordenadas da PIOR pra melhor (o que mais precisa de
    atenção fica no topo). Coloridas por faixa (vermelho <50%, laranja
    50-75%, verde >75%), igual ao gráfico por questão. `percentuais` é um
    dict {tema: percentual}. Retorna None se vazio.
    """
    if not percentuais:
        return None

    itens = sorted(percentuais.items(), key=lambda x: x[1])
    temas = [t for t, _ in itens]
    valores = [v for _, v in itens]

    def _cor(v):
        if v < 50:
            return "#C44E52"
        if v < 75:
            return "#DD8452"
        return "#55A868"

    cores = [_cor(v) for v in valores]
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * len(itens))))
    y_pos = list(range(len(itens)))
    ax.barh(y_pos, valores, color=cores, edgecolor="white")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(temas, fontsize=7.5)
    ax.set_xlabel(xlabel)
    ax.set_xlim(0, 100)
    ax.set_title(titulo)
    ax.invert_yaxis()  # pior fica no topo
    fig.tight_layout()
    return fig


def grafico_percentual_por_questao(percentuais: pd.Series, titulo: str, ylabel: str = "% de acerto"):
    """
    Barras com o percentual de acerto de cada questão objetiva, na ORDEM
    das questões (não ordenado por valor) — útil para acompanhar o
    desempenho ao longo da prova. Coloridas por faixa (vermelho <50%,
    laranja 50-75%, verde >75%). `percentuais` deve ter o número da
    questão como índice. Retorna None se vazio.
    """
    if len(percentuais) == 0:
        return None

    def _cor(v):
        if v < 50:
            return "#C44E52"
        if v < 75:
            return "#DD8452"
        return "#55A868"

    cores = [_cor(v) for v in percentuais.values]
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.bar(percentuais.index.astype(str), percentuais.values, color=cores, edgecolor="white")
    ax.set_title(titulo)
    ax.set_xlabel("Questão")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", labelsize=7, rotation=90)
    fig.tight_layout()
    return fig


def grafico_pizza_status(contagens: dict, titulo: str):
    """
    Pizza mostrando a proporção de respostas Certas/Erradas/Em branco
    (ou qualquer outro dicionário {rotulo: contagem}). Retorna None se
    todas as contagens forem zero.
    """
    rotulos = [k for k, v in contagens.items() if v > 0]
    valores = [v for v in contagens.values() if v > 0]
    if not valores:
        return None

    cores_por_rotulo = {"Certo": "#55A868", "Errado": "#C44E52", "Em branco": "#8C8C8C"}
    cores = [cores_por_rotulo.get(r, "#4C72B0") for r in rotulos]

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(valores, labels=rotulos, autopct="%1.0f%%", colors=cores, startangle=90,
           wedgeprops=dict(edgecolor="white"))
    ax.set_title(titulo)
    fig.tight_layout()
    return fig


def grafico_gaussiana_com_destaque(valores: pd.Series, valor_aluno: float, titulo: str,
                                    xlabel: str = "Nota (0-1000)", figsize=(6.5, 3.8)):
    """
    Histograma + curva normal da turma, com a nota de UM aluno marcada com
    uma linha vertical e um ponto sobre a curva — para o aluno ver onde ele
    está em relação à distribuição da turma. Usado no feedback em PDF.
    Retorna None se não houver dados suficientes (mínimo 2 notas da turma)
    ou se `valor_aluno` for None.
    """
    valores = valores.dropna()
    if len(valores) < 2 or valor_aluno is None:
        return None

    media = valores.mean()
    desvio = valores.std(ddof=1)

    fig, ax = plt.subplots(figsize=figsize)
    n_bins = min(max(len(valores) // 2, 5), 20)
    ax.hist(valores, bins=n_bins, density=True, alpha=0.35, color="#4C72B0", edgecolor="white")

    limite_min = min(valores.min(), valor_aluno) - 20
    limite_max = max(valores.max(), valor_aluno) + 20
    if desvio > 0:
        x = np.linspace(limite_min, limite_max, 200)
        pdf = (1 / (desvio * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - media) / desvio) ** 2)
        ax.plot(x, pdf, color="#4C72B0", linewidth=2, label=f"Turma (μ={media:.0f}, σ={desvio:.0f})")
        y_aluno = (1 / (desvio * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((valor_aluno - media) / desvio) ** 2)
    else:
        y_aluno = ax.get_ylim()[1] * 0.5

    ax.axvline(valor_aluno, color="#C44E52", linewidth=2, linestyle="--")
    ax.scatter([valor_aluno], [y_aluno], color="#C44E52", s=90, zorder=5, label=f"Você: {valor_aluno:.0f}")

    ax.set_title(titulo)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Densidade")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def grafico_ranking_extremos(nomes, valores, titulo: str, top_n: int = 5, ylabel: str = "Nota (0-1000)"):
    """
    Barras horizontais destacando os `top_n` melhores (verde) e os `top_n`
    piores (vermelho) valores, ordenados. Se houver poucos alunos (2*top_n
    ou menos), mostra todos em vez de dividir em dois grupos.
    Retorna None se não houver nenhum valor válido.
    """
    pares = [(str(n), v) for n, v in zip(nomes, valores) if v is not None and not pd.isna(v)]
    if not pares:
        return None
    pares.sort(key=lambda p: p[1], reverse=True)

    if len(pares) <= top_n * 2:
        selecionados = pares
        meio = (len(pares) + 1) // 2
        cores = ["#55A868"] * meio + ["#C44E52"] * (len(pares) - meio)
    else:
        melhores = pares[:top_n]
        piores = pares[-top_n:]
        selecionados = melhores + piores
        cores = ["#55A868"] * len(melhores) + ["#C44E52"] * len(piores)

    nomes_sel, valores_sel = zip(*selecionados)
    fig, ax = plt.subplots(figsize=(7, max(3, 0.4 * len(selecionados))))
    y_pos = np.arange(len(selecionados))[::-1]
    ax.barh(y_pos, valores_sel, color=cores, edgecolor="white")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(nomes_sel, fontsize=8)
    ax.set_xlabel(ylabel)
    ax.set_title(titulo)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Evolucao individual anonima (cada aluno = um ponto, sem nome)
# ---------------------------------------------------------------------------

def tabela_evolucao_alunos(df: pd.DataFrame) -> pd.DataFrame:
    """
    A partir de correcoes (formato de db.list_correcoes), monta uma tabela larga
    com uma linha por aluno e uma coluna por simulado (nota 0-1000; a correcao
    mais recente de cada aluno em cada simulado). Simulados ordenados pela data
    da primeira correcao. Mantem apenas alunos com 2+ simulados.
    Colunas de retorno: os nomes dos simulados (na ordem cronologica). O indice
    e uma chave interna do aluno - nunca exibida nos graficos.
    """
    d = df.dropna(subset=["nota_1000"]).copy()
    if len(d) == 0:
        return pd.DataFrame()
    if "aluno_id" in d.columns:
        chave = d["aluno_id"].astype("Int64").astype(str)
        sem_id = d["aluno_id"].isna()
        chave[sem_id] = "n:" + d["aluno"].astype(str)[sem_id] + "|" + d["turma"].astype(str)[sem_id]
    else:
        chave = "n:" + d["aluno"].astype(str) + "|" + d["turma"].astype(str)
    d["_chave"] = chave
    d = d.sort_values("data").drop_duplicates(subset=["_chave", "simulado_id"], keep="last")
    ordem = d.groupby("simulado_id")["data"].min().sort_values().index.tolist()
    nomes = d.drop_duplicates("simulado_id").set_index("simulado_id")["simulado"].to_dict()
    larga = d.pivot(index="_chave", columns="simulado_id", values="nota_1000")[ordem]
    larga = larga[larga.notna().sum(axis=1) >= 2]
    larga.columns = [nomes[c] for c in ordem]
    return larga


def resumo_evolucao(larga: pd.DataFrame) -> dict:
    """Compara, para cada aluno, a nota no primeiro e no ultimo simulado em que participou."""
    if larga.empty:
        return {}
    primeira = larga.apply(lambda r: r.dropna().iloc[0], axis=1)
    ultima = larga.apply(lambda r: r.dropna().iloc[-1], axis=1)
    delta = ultima - primeira
    return {
        "primeira": primeira, "ultima": ultima, "delta": delta,
        "n": len(delta),
        "evoluiu": int((delta > 0).sum()), "regrediu": int((delta < 0).sum()),
        "estavel": int((delta == 0).sum()),
        "delta_medio": float(delta.mean()), "delta_mediano": float(delta.median()),
    }


def grafico_evolucao_pontos(larga: pd.DataFrame, titulo: str = "Nota de cada aluno ao longo dos simulados",
                            figsize=(7.5, 4.0)):
    """Um ponto por aluno em cada simulado (sem nomes), ligados por linhas finas, com a media."""
    if larga.empty or larga.shape[1] < 2:
        return None
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(figsize=figsize)
    xs = np.arange(larga.shape[1])
    for _, linha in larga.iterrows():
        vals = linha.values.astype(float)
        mask = ~np.isnan(vals)
        ax.plot(xs[mask], vals[mask], color="#9AA5B1", linewidth=0.6, alpha=0.5, zorder=1)
    for i, col in enumerate(larga.columns):
        v = larga[col].dropna()
        jitter = rng.uniform(-0.12, 0.12, len(v))
        ax.scatter(np.full(len(v), i) + jitter, v, s=22, color="#4C72B0", alpha=0.8,
                   edgecolor="white", linewidth=0.5, zorder=2)
    medias = larga.mean()
    ax.plot(xs, medias.values, color="#C44E52", marker="D", linewidth=2, zorder=3, label="Média dos alunos")
    for x, m in zip(xs, medias.values):
        ax.annotate(f"{m:.0f}", (x, m), textcoords="offset points", xytext=(14, -3), fontsize=8,
                    color="#C44E52", fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels([("\n".join(__import__("textwrap").wrap(str(c), 14)[:3])) for c in larga.columns], fontsize=8)
    ax.set_ylim(0, 1050)
    ax.set_ylabel("Nota (0-1000)")
    ax.set_title(titulo, fontsize=10)
    ax.legend(fontsize=8, loc="lower right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def grafico_evolucao_dispersao(res: dict, titulo: str = "Primeiro x último simulado de cada aluno",
                               figsize=(5.2, 4.6)):
    """Dispersao: x = nota no primeiro simulado, y = nota no ultimo. Acima da diagonal = evoluiu."""
    if not res:
        return None
    x, y, d = res["primeira"].values, res["ultima"].values, res["delta"].values
    cores = np.where(d > 0, "#2E8B57", np.where(d < 0, "#C44E52", "#7F7F7F"))
    fig, ax = plt.subplots(figsize=figsize)
    lo = max(0, min(x.min(), y.min()) - 30)
    hi = min(1050, max(x.max(), y.max()) + 30)
    ax.plot([lo, hi], [lo, hi], color="#555555", linestyle="--", linewidth=1)
    ax.fill_between([lo, hi], [lo, hi], hi, color="#2E8B57", alpha=0.06)
    ax.fill_between([lo, hi], lo, [lo, hi], color="#C44E52", alpha=0.06)
    ax.scatter(x, y, c=cores, s=38, edgecolor="white", linewidth=0.6, zorder=3)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Nota no primeiro simulado")
    ax.set_ylabel("Nota no último simulado")
    ax.set_title(titulo, fontsize=10)
    ax.text(lo + (hi - lo) * 0.03, hi - (hi - lo) * 0.06, "evoluíram", color="#2E8B57", fontsize=8.5, fontweight="bold")
    ax.text(hi - (hi - lo) * 0.03, lo + (hi - lo) * 0.04, "regrediram", color="#C44E52", fontsize=8.5,
            fontweight="bold", ha="right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Psicometria simples (classica) por questao e por prova
# ---------------------------------------------------------------------------
import json as _json

ALTERNATIVAS = ["A", "B", "C", "D", "E"]


def _respostas_de(row_json) -> dict:
    if isinstance(row_json, dict):
        return row_json
    try:
        return _json.loads(row_json) if row_json else {}
    except (TypeError, ValueError):
        return {}


def matriz_acertos(df: pd.DataFrame, gabarito: dict) -> pd.DataFrame:
    """Linhas = correcoes, colunas = questoes (int); valores 1 (acertou) / 0."""
    questoes = sorted(int(q) for q in gabarito)
    linhas = []
    for rj in df["respostas"]:
        r = _respostas_de(rj)
        linhas.append({q: int(r.get(str(q)) == gabarito[str(q)]) for q in questoes})
    return pd.DataFrame(linhas, columns=questoes)


def dificuldade_discriminacao(M: pd.DataFrame) -> pd.DataFrame:
    """Por questao: indice de dificuldade (% de acerto) e discriminacao (correlacao
    ponto-bisserial entre acertar a questao e o total nas DEMAIS questoes)."""
    total = M.sum(axis=1)
    linhas = []
    for q in M.columns:
        resto = total - M[q]
        if M[q].std() == 0 or resto.std() == 0 or len(M) < 5:
            r = np.nan
        else:
            r = float(np.corrcoef(M[q], resto)[0, 1])
        linhas.append({"questao": int(q), "acerto_pct": 100 * float(M[q].mean()), "discriminacao": r})
    return pd.DataFrame(linhas)


def classificar_discriminacao(r) -> str:
    if r is None or (isinstance(r, float) and np.isnan(r)):
        return "sem dados"
    if r < 0:
        return "negativa — revisar/anular"
    if r < 0.20:
        return "baixa — revisar"
    if r < 0.30:
        return "razoável"
    return "boa"


def alfa_kr20(M: pd.DataFrame):
    """Confiabilidade (KR-20 / alfa de Cronbach para itens 0/1). None se nao calculavel."""
    k = M.shape[1]
    if k < 2 or len(M) < 3:
        return None
    var_total = M.sum(axis=1).var(ddof=1)
    if not var_total or np.isnan(var_total):
        return None
    soma_var_itens = M.var(ddof=1).sum()
    return float(k / (k - 1) * (1 - soma_var_itens / var_total))


def interpretar_alfa(a) -> str:
    if a is None:
        return "não calculável"
    if a >= 0.9:
        return "excelente"
    if a >= 0.8:
        return "boa"
    if a >= 0.7:
        return "aceitável"
    if a >= 0.6:
        return "questionável"
    return "baixa"


def tabela_distratores(df: pd.DataFrame, gabarito: dict) -> pd.DataFrame:
    """% de alunos que marcou cada alternativa (e em branco) por questao. Indice = questao."""
    questoes = sorted(int(q) for q in gabarito)
    contagem = {q: {a: 0 for a in ALTERNATIVAS + ["Branco"]} for q in questoes}
    for rj in df["respostas"]:
        r = _respostas_de(rj)
        for q in questoes:
            m = r.get(str(q))
            contagem[q][m if m in ALTERNATIVAS else "Branco"] += 1
    n = max(len(df), 1)
    return pd.DataFrame({q: {k: 100 * v / n for k, v in c.items()} for q, c in contagem.items()}).T


def grafico_dificuldade_discriminacao(tab: pd.DataFrame, titulo="Dificuldade x discriminação das questões",
                                       figsize=(6.5, 4.2)):
    t = tab.dropna(subset=["discriminacao"])
    if t.empty:
        return None
    fig, ax = plt.subplots(figsize=figsize)
    cores = ["#C44E52" if r < 0.2 else ("#DD8452" if r < 0.3 else "#2E8B57") for r in t["discriminacao"]]
    ax.scatter(t["acerto_pct"], t["discriminacao"], c=cores, s=40, zorder=3, edgecolor="white")
    for _, row in t.iterrows():
        ax.annotate(str(int(row["questao"])), (row["acerto_pct"], row["discriminacao"]),
                    textcoords="offset points", xytext=(4, 3), fontsize=7)
    ax.axhline(0.2, color="#888", linestyle="--", linewidth=0.8)
    ax.axhline(0, color="#C44E52", linewidth=0.8)
    ax.set_xlabel("% de acerto (dificuldade: quanto menor, mais difícil)")
    ax.set_ylabel("Discriminação (correlação)")
    ax.set_title(titulo, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def grafico_distratores(dist: pd.DataFrame, gabarito: dict, titulo="Alternativas marcadas por questão (%)",
                        figsize=(5.6, 8.6)):
    if dist.empty:
        return None
    cols = ALTERNATIVAS + ["Branco"]
    dados = dist[cols].values
    fig, ax = plt.subplots(figsize=figsize)
    ax.imshow(dados, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, fontsize=8)
    ax.set_yticks(range(len(dist)))
    ax.set_yticklabels([f"Q{q}" for q in dist.index], fontsize=7)
    ax.xaxis.tick_top()
    for i, q in enumerate(dist.index):
        for j, c in enumerate(cols):
            v = dados[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6.5,
                    color="white" if v > 55 else "#222")
        correta = gabarito.get(str(q))
        if correta in ALTERNATIVAS:
            j = ALTERNATIVAS.index(correta)
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="#2E8B57", linewidth=1.8))
    ax.set_title(titulo + "\n(contorno verde = alternativa correta)", fontsize=9, pad=24)
    fig.tight_layout()
    return fig


def distratores_dominantes(dist: pd.DataFrame, gabarito: dict, limite_pct: float = 30.0, top: int = 8):
    """Questoes em que uma alternativa ERRADA foi marcada por >= limite_pct dos alunos."""
    achados = []
    for q in dist.index:
        correta = gabarito.get(str(q))
        for a in ALTERNATIVAS:
            if a != correta and dist.loc[q, a] >= limite_pct:
                achados.append((int(q), a, float(dist.loc[q, a]), float(dist.loc[q, correta]) if correta in ALTERNATIVAS else 0.0))
    return sorted(achados, key=lambda x: -x[2])[:top]


# ---------------------------------------------------------------------------
# Alunos em risco
# ---------------------------------------------------------------------------

def alunos_em_risco(df: pd.DataFrame, corte: float = 600.0, queda: float = 50.0) -> pd.DataFrame:
    """Alunos cuja ultima nota (0-1000) esta abaixo de `corte` OU caiu pelo menos
    `queda` pontos em relacao ao simulado anterior. Colunas: aluno, turma, ultima,
    anterior, variacao, motivo."""
    d = df.dropna(subset=["nota_1000"]).copy()
    if d.empty:
        return pd.DataFrame(columns=["aluno", "turma", "ultima", "anterior", "variacao", "motivo"])
    if "aluno_id" in d.columns:
        chave = d["aluno_id"].astype("Int64").astype(str)
        sem = d["aluno_id"].isna()
        chave[sem] = "n:" + d["aluno"].astype(str)[sem] + "|" + d["turma"].astype(str)[sem]
    else:
        chave = "n:" + d["aluno"].astype(str) + "|" + d["turma"].astype(str)
    d["_chave"] = chave
    d = d.sort_values("data").drop_duplicates(subset=["_chave", "simulado_id"], keep="last")
    saida = []
    for _, g in d.groupby("_chave"):
        g = g.sort_values("data")
        ultima = float(g["nota_1000"].iloc[-1])
        anterior = float(g["nota_1000"].iloc[-2]) if len(g) >= 2 else None
        variacao = ultima - anterior if anterior is not None else None
        motivos = []
        if ultima < corte:
            motivos.append(f"nota abaixo de {corte:.0f}")
        if variacao is not None and variacao <= -queda:
            motivos.append(f"queda de {abs(variacao):.0f} pts")
        if motivos:
            saida.append({"aluno": g["aluno"].iloc[-1], "turma": g["turma"].iloc[-1], "ultima": ultima,
                          "anterior": anterior, "variacao": variacao, "motivo": "; ".join(motivos)})
    out = pd.DataFrame(saida, columns=["aluno", "turma", "ultima", "anterior", "variacao", "motivo"])
    return out.sort_values("ultima").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Formacao geral x componente especifico
# ---------------------------------------------------------------------------

def desempenho_por_bloco(df: pd.DataFrame, gabarito: dict, temas_questoes: dict) -> pd.DataFrame:
    """Para cada correcao, % de acerto nas questoes de Formacao Geral e do componente
    Especifico, classificadas pelo tema cadastrado (listas oficiais das Portarias).
    Colunas: turma, fg_pct, esp_pct (NaN se o aluno nao tem questoes no bloco)."""
    from enade_referencia import OBJETOS_ADS_ESPECIFICO, OBJETOS_FORMACAO_GERAL
    fg_q = [int(q) for q, t in temas_questoes.items() if t in OBJETOS_FORMACAO_GERAL and q in gabarito]
    esp_q = [int(q) for q, t in temas_questoes.items() if t in OBJETOS_ADS_ESPECIFICO and q in gabarito]
    linhas = []
    for _, row in df.iterrows():
        r = _respostas_de(row["respostas"])
        def pct(qs):
            return 100 * sum(r.get(str(q)) == gabarito[str(q)] for q in qs) / len(qs) if qs else np.nan
        linhas.append({"turma": row.get("turma"), "fg_pct": pct(fg_q), "esp_pct": pct(esp_q)})
    out = pd.DataFrame(linhas)
    out.attrs["n_fg"], out.attrs["n_esp"] = len(fg_q), len(esp_q)
    return out


def grafico_blocos(dfb: pd.DataFrame, titulo="Acerto: Formação Geral x Componente Específico", figsize=(6.5, 3.6)):
    if dfb.empty or (dfb["fg_pct"].isna().all() and dfb["esp_pct"].isna().all()):
        return None
    turmas = [t for t in dfb["turma"].dropna().unique()]
    grupos = ["Geral"] + (turmas if len(turmas) >= 2 else [])
    fg, esp = [dfb["fg_pct"].mean()], [dfb["esp_pct"].mean()]
    for t in grupos[1:]:
        fg.append(dfb[dfb["turma"] == t]["fg_pct"].mean())
        esp.append(dfb[dfb["turma"] == t]["esp_pct"].mean())
    x = np.arange(len(grupos))
    fig, ax = plt.subplots(figsize=figsize)
    b1 = ax.bar(x - 0.18, fg, 0.36, label="Formação Geral", color="#4C72B0")
    b2 = ax.bar(x + 0.18, esp, 0.36, label="Específico (ADS)", color="#DD8452")
    for bars in (b1, b2):
        for b in bars:
            if not np.isnan(b.get_height()):
                ax.annotate(f"{b.get_height():.0f}%", (b.get_x() + b.get_width() / 2, b.get_height()),
                            ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(grupos, fontsize=8)
    ax.set_ylim(0, 110)
    ax.set_ylabel("% de acerto")
    ax.set_title(titulo, fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Objetivas x discursiva
# ---------------------------------------------------------------------------

def grafico_objetivas_discursiva(obj_pct: pd.Series, disc_pct: pd.Series, titulo="Objetivas x discursiva",
                                  figsize=(5.2, 4.2)):
    """Dispersao % de acerto nas objetivas x aproveitamento na discursiva, com reta e Pearson.
    Retorna (fig, r) ou (None, None)."""
    d = pd.concat([obj_pct, disc_pct], axis=1).dropna()
    if len(d) < 3:
        return None, None
    x, y = d.iloc[:, 0].values.astype(float), d.iloc[:, 1].values.astype(float)
    r = float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else float("nan")
    fig, ax = plt.subplots(figsize=figsize)
    ax.scatter(x, y, s=28, color="#4C72B0", alpha=0.8, edgecolor="white")
    if x.std() > 0:
        a, b = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 50)
        ax.plot(xs, a * xs + b, color="#C44E52", linewidth=1.5)
    ax.set_xlabel("Acerto nas objetivas (%)")
    ax.set_ylabel("Aproveitamento na discursiva (%)")
    ax.set_title(titulo, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig, r


def interpretar_correlacao(r) -> str:
    if r is None or np.isnan(r):
        return "não calculável"
    a = abs(r)
    forca = "muito fraca" if a < 0.2 else "fraca" if a < 0.4 else "moderada" if a < 0.6 else "forte" if a < 0.8 else "muito forte"
    return f"{forca} {'positiva' if r > 0 else 'negativa'}"


# ---------------------------------------------------------------------------
# Quartis e percentis
# ---------------------------------------------------------------------------

def quartis_percentis(valores: pd.Series) -> dict:
    v = valores.dropna()
    if len(v) == 0:
        return {}
    q = v.quantile([0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]).tolist()
    return dict(zip(["min", "p10", "q1", "mediana", "q3", "p90", "max"], q))


def percentil_do_valor(valores: pd.Series, valor: float):
    """Percentil (0-100) de `valor` na distribuicao (% da turma com nota menor, metade dos empates)."""
    v = valores.dropna()
    if len(v) == 0 or valor is None:
        return None
    return float(100 * ((v < valor).sum() + 0.5 * (v == valor).sum()) / len(v))


def grafico_histograma_quartis(valores: pd.Series, titulo="Distribuição das notas com quartis",
                                figsize=(6.5, 3.4)):
    v = valores.dropna()
    if len(v) < 4:
        return None
    qs = quartis_percentis(v)
    fig, ax = plt.subplots(figsize=figsize)
    ax.hist(v, bins=min(max(len(v) // 2, 5), 20), color="#4C72B0", alpha=0.4, edgecolor="white")
    for chave, rot, cor in [("q1", "Q1", "#DD8452"), ("mediana", "Mediana", "#C44E52"), ("q3", "Q3", "#DD8452")]:
        ax.axvline(qs[chave], color=cor, linestyle="--", linewidth=1.5)
        ax.text(qs[chave], ax.get_ylim()[1] * 0.96, f"{rot}\n{qs[chave]:.0f}", ha="center", va="top", fontsize=7.5, color=cor)
    ax.set_xlabel("Nota (0-1000)")
    ax.set_ylabel("Alunos")
    ax.set_title(titulo, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig