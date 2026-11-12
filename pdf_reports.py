"""
pdf_reports.py
Gera os PDFs exportaveis do app: o feedback por aluno (gerar_pdf_turma) e
o relatorio geral (gerar_pdf_relatorio_geral). Ambos saem com um timbre
generico configuravel (logo no cabecalho, logo +
endereco + linha vermelha no rodape de cada pagina).

O feedback por aluno traz, por pagina:
- nota final (0-1000) e nota objetiva
- grafico da distribuicao de notas da turma com a nota do aluno destacada
- sugestao de temas/objetos de aprendizagem a revisar, a partir das
  questoes que o aluno errou (se o simulado tiver temas cadastrados)
- feedback da questao discursiva (resumo/justificativas da IA, ou
  observacoes manuais)
- tabela comparando a resposta do aluno com o gabarito, questao a questao
"""

import io
import json
import os

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from stats_utils import (
    alfa_kr20, alunos_em_risco, classificar_discriminacao, desempenho_por_bloco,
    dificuldade_discriminacao, distratores_dominantes, grafico_blocos,
    grafico_dificuldade_discriminacao, grafico_distratores, grafico_histograma_quartis,
    grafico_objetivas_discursiva, interpretar_alfa, interpretar_correlacao, matriz_acertos,
    percentil_do_valor, quartis_percentis, tabela_distratores,
    grafico_evolucao_dispersao,
    grafico_evolucao_pontos,
    resumo_evolucao,
    tabela_evolucao_alunos,
    grafico_barras_comparativo,
    grafico_boxplot_por_grupo,
    grafico_desempenho_por_tema,
    grafico_dispersao_tempo_nota,
    grafico_gaussiana_com_destaque,
    grafico_histograma_gaussiana,
    grafico_percentual_por_questao,
    grafico_pizza_status,
    grafico_ranking_extremos,
    resumo_estatistico,
)

# ---------------------------------------------------------------------------
# Timbre (logos + rodape) - versao GENERICA. Para usar o timbre da sua
# instituicao:
#   1. substitua assets/logo_cabecalho.png (proporcao ~3,9:1) e
#      assets/logo_rodape.png (proporcao ~2,3:1) pelos logos dela;
#   2. edite os textos de _RODAPE_LINHAS logo abaixo;
#   3. se quiser, troque a cor da linha em _LINHA_DESTAQUE["cor"] (RGB 0-1).
# Coordenadas em pontos, pagina A4, no sistema do reportlab (origem no canto
# inferior esquerdo, eixo Y crescendo para cima).
# ---------------------------------------------------------------------------
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_LOGO_CABECALHO = os.path.join(_ASSETS_DIR, "logo_cabecalho.png")
_LOGO_RODAPE = os.path.join(_ASSETS_DIR, "logo_rodape.png")

_CABECALHO_RECT = dict(x=173.88, y=749.49, largura=247.60, altura=63.40)
_RODAPE_LOGO_RECT = dict(x=95.65, y=48.94, largura=117.15, altura=50.45)
_LINHA_DESTAQUE = dict(x=85.15, y=105.54, largura=425.30, altura=1.65, cor=(31 / 255, 58 / 255, 95 / 255))
_RODAPE_TEXTO_X = 252.77
_COR_CINZA_ESCURO = (89 / 255, 89 / 255, 89 / 255)
_COR_CINZA_CLARO = (128 / 255, 128 / 255, 128 / 255)
_RODAPE_LINHAS = [
    # (texto, y_reportlab, negrito, cor)
    ("Nome da Instituição", 88.62, True, _COR_CINZA_ESCURO),
    ("Endereço, nº – Bairro – Cidade/UF", 76.60, False, _COR_CINZA_ESCURO),
    ("CEP: 00000-000", 64.60, False, _COR_CINZA_ESCURO),
    ("Tel.: (00) 0000-0000", 64.60, False, _COR_CINZA_CLARO),
    ("e-mail: contato@instituicao.edu.br", 52.60, False, _COR_CINZA_CLARO),
    ("www.instituicao.edu.br", 40.60, False, _COR_CINZA_CLARO),
]
_RODAPE_TEL_X = 340.15  # "Tel.:" fica na mesma linha do CEP, mais à direita

# Margens de conteudo que deixam espaco livre para o timbre nao ser coberto
# pelo texto/graficos do relatorio.
MARGEM_SUPERIOR_COM_TIMBRE = 3.4 * cm
MARGEM_INFERIOR_COM_TIMBRE = 4.2 * cm

# Secoes disponiveis no Relatorio Geral, na ordem em que aparecem no PDF.
# Usado pela pagina Exportar para montar a lista de checkboxes de selecao;
# gerar_pdf_relatorio_geral() aceita um dict {chave: bool} usando essas
# mesmas chaves para decidir o que incluir.
SECOES_RELATORIO_GERAL = [
    ("visao_geral", "Visão geral (média, mediana, desvio padrão, distribuição das notas)"),
    ("comparativo_turmas", "Comparativo entre turmas"),
    ("ranking", "Ranking de melhores e piores alunos"),
    ("discursiva", "Questão discursiva"),
    ("desempenho_questoes", "Desempenho por questão objetiva"),
    ("desempenho_temas", "Desempenho por objeto de conhecimento"),
    ("tempo_nota", "Tempo de prova x nota"),
    ("evolucao_alunos", "Evolução individual dos alunos ao longo dos simulados (pontos anônimos)"),
    ("dificuldade_discriminacao", "Dificuldade e discriminação por questão (exige simulado específico)"),
    ("distratores", "Análise dos distratores — alternativas mais marcadas (exige simulado específico)"),
    ("confiabilidade", "Confiabilidade da prova — alfa de Cronbach / KR-20 (exige simulado específico)"),
    ("alunos_risco", "Alunos em risco (nota abaixo do corte ou em queda)"),
    ("blocos_fg_esp", "Formação Geral x Componente Específico (exige simulado com temas cadastrados)"),
    ("objetiva_discursiva", "Objetivas x discursiva (correlação)"),
    ("quartis_percentis", "Quartis e percentis das notas"),
]


def _desenhar_timbre(canv, doc):
    """Callback usado em doc.build(onFirstPage=..., onLaterPages=...) para
    desenhar o timbre institucional em toda pagina do PDF."""
    canv.saveState()

    if os.path.exists(_LOGO_CABECALHO):
        canv.drawImage(
            _LOGO_CABECALHO, _CABECALHO_RECT["x"], _CABECALHO_RECT["y"],
            width=_CABECALHO_RECT["largura"], height=_CABECALHO_RECT["altura"],
            mask="auto", preserveAspectRatio=True,
        )

    if os.path.exists(_LOGO_RODAPE):
        canv.drawImage(
            _LOGO_RODAPE, _RODAPE_LOGO_RECT["x"], _RODAPE_LOGO_RECT["y"],
            width=_RODAPE_LOGO_RECT["largura"], height=_RODAPE_LOGO_RECT["altura"],
            mask="auto", preserveAspectRatio=True,
        )

    canv.setFillColorRGB(*_LINHA_DESTAQUE["cor"])
    canv.rect(
        _LINHA_DESTAQUE["x"], _LINHA_DESTAQUE["y"],
        _LINHA_DESTAQUE["largura"], _LINHA_DESTAQUE["altura"],
        fill=1, stroke=0,
    )

    for texto, y, negrito, cor in _RODAPE_LINHAS:
        canv.setFont("Helvetica-Bold" if negrito else "Helvetica", 8)
        canv.setFillColorRGB(*cor)
        x = _RODAPE_TEL_X if texto.startswith("Tel.:") else _RODAPE_TEXTO_X
        canv.drawString(x, y, texto)

    canv.restoreState()


def _figura_para_imagem(fig, largura=11 * cm):
    """Converte uma figura matplotlib num Image do reportlab (via PNG em memoria)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    altura = largura * (fig.get_size_inches()[1] / fig.get_size_inches()[0])
    return Image(buf, width=largura, height=altura)


def _aluno_acertos_texto(aluno: dict) -> str:
    acertos = aluno.get("acertos")
    n_questoes = aluno.get("n_questoes")
    nota = aluno.get("nota")
    if acertos is None or n_questoes is None:
        return "—"
    texto = f"{acertos}/{n_questoes}"
    if nota is not None:
        texto += f" ({nota:.1f}%)"
    return texto


def _sugestao_temas(respostas: dict, gabarito: dict, temas_questoes: dict, top_n: int = 3):
    """Conta erros por tema e retorna uma lista dos `top_n` temas mais errados,
    como [(tema, n_erros), ...]. Ignora questoes sem tema cadastrado."""
    if not temas_questoes:
        return []
    contagem = {}
    for q, correta in gabarito.items():
        tema = temas_questoes.get(q)
        if not tema:
            continue
        marcada = respostas.get(q)
        if marcada != correta:
            contagem[tema] = contagem.get(tema, 0) + 1
    if not contagem:
        return []
    return sorted(contagem.items(), key=lambda x: x[1], reverse=True)[:top_n]


def _feedback_discursiva_texto(discursiva_avaliacao: dict, discursiva_pontos, discursiva_pontos_max) -> list:
    """Monta os paragrafos de feedback da discursiva a partir do que foi salvo."""
    if discursiva_pontos is None:
        return ["Questão discursiva ainda não avaliada."]

    linhas = [f"Nota: {discursiva_pontos:.1f} / {discursiva_pontos_max:.0f}"]
    if not discursiva_avaliacao:
        return linhas

    sugestao = discursiva_avaliacao.get("sugestao_ia")
    if not sugestao and isinstance(discursiva_avaliacao.get("item_a"), dict):
        sugestao = discursiva_avaliacao  # registro salvo pela versao antiga do lote
    if sugestao:
        if sugestao.get("resumo"):
            linhas.append(sugestao["resumo"])
        for chave, rotulo in [
            ("item_a", "Item a"), ("item_b", "Item b"),
            ("item_c", "Item c"), ("bonus_integracao", "Bônus"),
        ]:
            item = sugestao.get(chave)
            if item and item.get("justificativa"):
                linhas.append(f"{rotulo}: {item['justificativa']}")
    elif discursiva_avaliacao.get("observacoes"):
        linhas.append(discursiva_avaliacao["observacoes"])

    return linhas


def _tabela_respostas(respostas: dict, gabarito: dict, n_questoes: int):
    """Monta a tabela Questão / Sua resposta / Gabarito / Status, em duas colunas lado a lado
    para caber melhor na página."""
    dados_completos = []
    for q in range(1, n_questoes + 1):
        marcada = respostas.get(str(q)) or "-"
        correta = gabarito.get(str(q)) or "-"
        status = "Certo" if marcada == correta else ("Em branco" if marcada == "-" else "Errado")
        dados_completos.append([str(q), marcada, correta, status])

    meio = (len(dados_completos) + 1) // 2
    coluna_esquerda = dados_completos[:meio]
    coluna_direita = dados_completos[meio:]

    cabecalho = ["Q", "Sua", "Gab.", "Status"]
    tabela_esquerda = [cabecalho] + coluna_esquerda
    tabela_direita = [cabecalho] + coluna_direita

    def _estilo_tabela(dados):
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4C72B0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("LEADING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]
        for i, linha in enumerate(dados[1:], start=1):
            if linha[3] == "Errado":
                estilo.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#C44E52")))
            elif linha[3] == "Certo":
                estilo.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#55A868")))
        return TableStyle(estilo)

    t_esq = Table(tabela_esquerda, colWidths=[1 * cm, 1.3 * cm, 1.3 * cm, 1.8 * cm])
    t_esq.setStyle(_estilo_tabela(tabela_esquerda))
    t_dir = Table(tabela_direita, colWidths=[1 * cm, 1.3 * cm, 1.3 * cm, 1.8 * cm])
    t_dir.setStyle(_estilo_tabela(tabela_direita))

    container = Table([[t_esq, t_dir]], colWidths=[7.5 * cm, 7.5 * cm])
    container.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return container


def _grafico_evolucao_aluno(historico: list, simulado_atual_id=None, figsize=(4.6, 3.0)):
    """Barras empilhadas (objetivas + discursiva, escala 0-1000) por simulado do aluno.
    `historico`: lista ordenada de {"simulado_id", "simulado", "objetivas_1000",
    "discursiva_1000", "nota_1000"}. Retorna a figura (ou None se vazio)."""
    if not historico:
        return None
    nomes = []
    for h in historico:
        n = str(h["simulado"])
        import textwrap
        linhas_n = textwrap.wrap(n, width=12 if len(historico) <= 4 else 9)
        if len(linhas_n) > 3:
            linhas_n = linhas_n[:3]
            linhas_n[-1] = linhas_n[-1][:-1] + "…"
        nomes.append("\n".join(linhas_n))
    obj = [h["objetivas_1000"] or 0.0 for h in historico]
    dis = [h["discursiva_1000"] or 0.0 for h in historico]
    tot = [h["nota_1000"] or (o + d) for h, o, d in zip(historico, obj, dis)]
    x = list(range(len(historico)))

    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(x, obj, color="#4C72B0", label="Objetivas", width=0.55)
    ax.bar(x, dis, bottom=obj, color="#DD8452", label="Discursiva", width=0.55)
    ax.plot(x, tot, color="#333333", marker="o", linewidth=1.2, markersize=4)
    for xi, t in zip(x, tot):
        ax.annotate(f"{t:.0f}", (xi, t), textcoords="offset points", xytext=(0, 5),
                    ha="center", fontsize=8, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(nomes, fontsize=7)
    for lbl, h in zip(ax.get_xticklabels(), historico):
        if simulado_atual_id is not None and h.get("simulado_id") == simulado_atual_id:
            lbl.set_fontweight("bold")
    ax.set_ylim(0, 1150)
    ax.set_ylabel("Nota (0-1000)", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(fontsize=7, loc="upper left", ncol=2, frameon=False, bbox_to_anchor=(0, 1.12))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


class _MarcaInicio(Flowable):
    """Invisivel: anota em qual pagina do PDF comeca o relatorio de um aluno."""

    def __init__(self, doc, registro):
        super().__init__()
        self._doc, self._reg = doc, registro

    def wrap(self, aw, ah):
        self._reg["inicio"] = self._doc.page
        return 0, 0

    def draw(self):
        pass


class _PreencherAtePar(Flowable):
    """Invisivel: se o relatorio do aluno ocupou um numero IMPAR de paginas, preenche o resto da
    pagina atual; o Spacer que vem logo depois cai entao numa pagina nova (em branco), de modo que
    cada aluno ocupe sempre um numero par de paginas (frente e verso na impressao)."""

    def __init__(self, doc, registro):
        super().__init__()
        self._doc, self._reg = doc, registro

    def wrap(self, aw, ah):
        usadas = self._doc.page - self._reg.get("inicio", self._doc.page) + 1
        return (aw, ah) if usadas % 2 == 1 else (0, 0)

    def draw(self):
        pass


def gerar_pdf_turma(turma_nome: str, simulado: dict, alunos_data: list) -> bytes:
    """
    Gera um PDF com um relatório de feedback por aluno (sempre um número PAR de páginas por aluno: 2 páginas, a segunda em branco se não houver
    conteúdo, para facilitar a impressão frente e verso).

    `alunos_data`: lista de dicts, um por aluno, cada um com:
        {"aluno": str, "acertos": int, "n_questoes": int, "nota": float,
         "nota_1000": float, "respostas": dict, "discursiva_pontos": float|None,
         "discursiva_pontos_max": float|None, "discursiva_avaliacao": dict|None,
         "tempo_prova_minutos": float|None,
         "historico": list|None}   # opcional: evolucao do aluno em todos os simulados

    `simulado`: dict de get_simulado() (usa gabarito_dict e temas_questoes_dict).

    Retorna os bytes do PDF pronto para download.
    """
    gabarito = simulado.get("gabarito_dict") or {}
    temas_questoes = simulado.get("temas_questoes_dict") or {}
    n_questoes = simulado.get("n_questoes") or 31

    notas_turma = [a["nota_1000"] for a in alunos_data if a.get("nota_1000") is not None]
    serie_notas_turma = pd.Series(notas_turma)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=MARGEM_SUPERIOR_COM_TIMBRE, bottomMargin=MARGEM_INFERIOR_COM_TIMBRE,
    )
    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("TituloRelatorio", parent=styles["Heading1"], fontSize=14, spaceAfter=2)
    estilo_subtitulo = ParagraphStyle("Subtitulo", parent=styles["Normal"], fontSize=9.5, textColor=colors.grey)
    estilo_secao = ParagraphStyle("Secao", parent=styles["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2)
    estilo_corpo = ParagraphStyle("Corpo", parent=styles["Normal"], fontSize=9, leading=11.5)
    estilo_nota = ParagraphStyle("Nota", parent=styles["Heading1"], fontSize=22, textColor=colors.HexColor("#4C72B0"), spaceAfter=1)

    story = []

    for i, aluno in enumerate(alunos_data):
        _reg_pag = {}
        story.append(_MarcaInicio(doc, _reg_pag))
        story.append(Paragraph(f"Resultado — {simulado.get('nome', '')}", estilo_titulo))
        story.append(Paragraph(f"{aluno['aluno']} — Turma {turma_nome}", estilo_subtitulo))
        story.append(Spacer(1, 4))

        nota_1000 = aluno.get("nota_1000")
        story.append(Paragraph(f"{nota_1000:.0f} / 1000" if nota_1000 is not None else "—", estilo_nota))
        linha_resumo = f"Questões objetivas: {_aluno_acertos_texto(aluno)}"
        if aluno.get("tempo_prova_minutos"):
            linha_resumo += f"  ·  Tempo de prova: {aluno['tempo_prova_minutos']:.0f} min"
        pctl = percentil_do_valor(serie_notas_turma, nota_1000) if len(serie_notas_turma) >= 3 else None
        if pctl is not None:
            linha_resumo += f"  ·  Percentil {pctl:.0f} na turma"
        story.append(Paragraph(linha_resumo, estilo_corpo))

        # gaussiana com destaque (e, ao lado, a evolucao do aluno em todos os simulados)
        historico = aluno.get("historico") or []
        fig_g = fig_ev = None
        if nota_1000 is not None:
            fig_g = grafico_gaussiana_com_destaque(
                serie_notas_turma, nota_1000, "Sua nota em relação à turma",
                figsize=(4.6, 3.0) if len(historico) >= 2 else (6.5, 3.0),
            )
        if len(historico) >= 2:
            fig_ev = _grafico_evolucao_aluno(historico, simulado.get("id"))

        if fig_g is not None and fig_ev is not None:
            story.append(Spacer(1, 4))
            tab = Table([[_figura_para_imagem(fig_g, largura=7.2 * cm),
                          _figura_para_imagem(fig_ev, largura=7.2 * cm)]],
                        colWidths=[8.7 * cm, 8.7 * cm])
            tab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(tab)
            story.append(Paragraph(
                "À esquerda: sua nota na turma. À direita: sua evolução nos simulados (objetivas + "
                "discursiva; o simulado deste relatório está em negrito).",
                ParagraphStyle("LegendaGraf", parent=estilo_corpo, fontSize=7.5, textColor=colors.grey)))
        elif fig_g is not None:
            story.append(Spacer(1, 4))
            story.append(_figura_para_imagem(fig_g))
        elif fig_ev is not None:
            story.append(_figura_para_imagem(fig_ev, largura=11 * cm))
        for f_ in (fig_g, fig_ev):
            if f_ is not None:
                plt.close(f_)

        # sugestao de temas a revisar
        respostas = aluno.get("respostas") or {}
        temas_errados = _sugestao_temas(respostas, gabarito, temas_questoes)
        if temas_errados:
            story.append(Paragraph("Temas a revisar", estilo_secao))
            for tema, n_erros in temas_errados:
                story.append(Paragraph(f"• {tema} — {n_erros} questão(ões) errada(s)", estilo_corpo))
        elif temas_questoes:
            story.append(Paragraph("Temas a revisar", estilo_secao))
            story.append(Paragraph("Nenhum erro nas questões com tema cadastrado — bom trabalho!", estilo_corpo))

        # feedback da discursiva
        story.append(Paragraph("Questão discursiva (32)", estilo_secao))
        for linha in _feedback_discursiva_texto(
            aluno.get("discursiva_avaliacao"), aluno.get("discursiva_pontos"), aluno.get("discursiva_pontos_max")
        ):
            story.append(Paragraph(linha, estilo_corpo))

        # tabela de respostas
        story.append(Paragraph("Suas respostas x gabarito", estilo_secao))
        story.append(_tabela_respostas(respostas, gabarito, n_questoes))

        # garante numero PAR de paginas por aluno (impressao frente e verso)
        story.append(_PreencherAtePar(doc, _reg_pag))
        story.append(Spacer(1, 1))

        if i < len(alunos_data) - 1:
            story.append(PageBreak())

    doc.build(story, onFirstPage=_desenhar_timbre, onLaterPages=_desenhar_timbre)
    buffer.seek(0)
    return buffer.getvalue()


def _tabela_simples(cabecalho: list, linhas: list, col_widths=None):
    """Monta uma tabela reportlab simples com cabeçalho azul, usada nas tabelas
    resumidas do relatório geral (comparativo entre turmas, etc.)."""
    dados = [cabecalho] + [[str(v) for v in linha] for linha in linhas]
    t = Table(dados, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4C72B0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return t


def gerar_pdf_relatorio_geral(descricao_filtro: str, df: pd.DataFrame, simulado: dict = None,
                               top_n_ranking: int = 5, secoes: dict = None,
                               df_evolucao: pd.DataFrame = None,
                               corte_risco: float = 600.0, queda_risco: float = 50.0) -> bytes:
    """
    Gera um PDF de visão geral (não é por aluno) cobrindo os itens do
    Dashboard: distribuição geral das notas, comparativo entre turmas,
    ranking de melhores/piores, desempenho na questão discursiva,
    desempenho por questão objetiva, desempenho por objeto de
    conhecimento, e a correlação entre tempo de prova e nota.

    `df`: DataFrame já filtrado, no mesmo formato de db.list_correcoes().
    `simulado`: dict de get_simulado() do simulado filtrado, ou None se o
    filtro for "todos os simulados" (as seções que dependem do gabarito
    ficam de fora nesse caso).
    `secoes`: dict opcional {chave: bool} controlando quais seções entram
    no PDF (chaves em SECOES_RELATORIO_GERAL). Se None, inclui todas —
    mantém compatibilidade com quem já chamava esta função sem esse
    parâmetro.

    `df_evolucao`: correções (formato de list_correcoes) usadas só na seção de evolução
    individual — normalmente as mesmas do filtro de turma/aluno, mas SEM filtrar o simulado
    (a evolução precisa de 2+ simulados). Se None, usa `df`.

    Retorna os bytes do PDF pronto para download.
    """
    def _incluir(chave: str) -> bool:
        return secoes is None or secoes.get(chave, True)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=MARGEM_SUPERIOR_COM_TIMBRE, bottomMargin=MARGEM_INFERIOR_COM_TIMBRE,
    )
    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("TituloGeral", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
    estilo_subtitulo = ParagraphStyle(
        "SubtituloGeral", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=10
    )
    estilo_secao = ParagraphStyle(
        "SecaoGeral", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6,
        keepWithNext=1,
        textColor=colors.HexColor("#4C72B0"),
    )
    estilo_corpo = ParagraphStyle("CorpoGeral", parent=styles["Normal"], fontSize=9.5, leading=13)

    story = [Paragraph("Relatório Geral de Resultados", estilo_titulo), Paragraph(descricao_filtro, estilo_subtitulo)]

    if len(df) == 0:
        story.append(Paragraph("Nenhuma correção encontrada com esse filtro.", estilo_corpo))
        doc.build(story, onFirstPage=_desenhar_timbre, onLaterPages=_desenhar_timbre)
        buffer.seek(0)
        return buffer.getvalue()

    def _add_fig(fig, largura=15 * cm):
        if fig is not None:
            story.append(_figura_para_imagem(fig, largura=largura))
            plt.close(fig)
            story.append(Spacer(1, 6))

    algo_adicionado = False

    def _iniciar_secao(titulo: str, quebra: bool = True):
        """Adiciona o cabeçalho de uma seção, com quebra de página antes
        (exceto se for a primeira seção do relatório)."""
        nonlocal algo_adicionado
        if algo_adicionado and quebra:
            story.append(PageBreak())
        story.append(Paragraph(titulo, estilo_secao))
        algo_adicionado = True

    # -----------------------------------------------------------------
    # 1. Visão geral
    # -----------------------------------------------------------------
    if _incluir("visao_geral"):
        _iniciar_secao("Visão geral")
        resumo = resumo_estatistico(df["nota_1000"])
        story.append(
            Paragraph(
                f"Correções: {resumo['n']} &nbsp;·&nbsp; Nota média: {resumo['media']} &nbsp;·&nbsp; "
                f"Mediana: {resumo['mediana']} &nbsp;·&nbsp; Desvio padrão: {resumo['desvio_padrao']}",
                estilo_corpo,
            )
        )
        _add_fig(grafico_histograma_gaussiana(df["nota_1000"], "Distribuição das notas (0-1000)", xlabel="Nota (0-1000)"))

    # -----------------------------------------------------------------
    # 2. Comparativo entre turmas
    # -----------------------------------------------------------------
    if _incluir("comparativo_turmas") and df["turma"].nunique(dropna=True) >= 2:
        _iniciar_secao("Comparativo entre turmas")
        linhas_turma = []
        for turma_nome, grupo in df.groupby("turma", dropna=False):
            s = resumo_estatistico(grupo["nota_1000"])
            linhas_turma.append((turma_nome or "—", s["n"], s["media"], s["mediana"], s["desvio_padrao"]))
        story.append(_tabela_simples(["Turma", "N", "Média", "Mediana", "Desvio"], linhas_turma))
        story.append(Spacer(1, 6))
        _add_fig(grafico_barras_comparativo([l[0] for l in linhas_turma], [l[2] for l in linhas_turma], "Média por turma"))
        _add_fig(grafico_boxplot_por_grupo(df, "turma", "nota_1000", "Distribuição por turma"))

    # -----------------------------------------------------------------
    # 3. Ranking
    # -----------------------------------------------------------------
    if _incluir("ranking"):
        _iniciar_secao("Ranking — melhores e piores alunos")
        por_aluno = df.groupby("aluno", dropna=True)["nota_1000"].mean().dropna()
        fig_ranking = grafico_ranking_extremos(
            por_aluno.index.tolist(), por_aluno.values.tolist(), "Melhores e piores alunos", top_n=top_n_ranking
        )
        if fig_ranking is not None:
            _add_fig(fig_ranking)
        else:
            story.append(Paragraph("Sem dados suficientes para o ranking.", estilo_corpo))

    # -----------------------------------------------------------------
    # 4. Questão discursiva
    # -----------------------------------------------------------------
    if _incluir("discursiva"):
        _iniciar_secao("Questão discursiva")
        df_disc = df.dropna(subset=["discursiva_pontos", "discursiva_pontos_max"]).copy()
        if len(df_disc):
            df_disc["discursiva_percentual"] = 100 * df_disc["discursiva_pontos"] / df_disc["discursiva_pontos_max"]
            resumo_disc = resumo_estatistico(df_disc["discursiva_percentual"])
            story.append(
                Paragraph(
                    f"Avaliadas: {resumo_disc['n']} de {len(df)} &nbsp;·&nbsp; "
                    f"Aproveitamento médio: {resumo_disc['media']}% &nbsp;·&nbsp; "
                    f"Mediana: {resumo_disc['mediana']}% &nbsp;·&nbsp; "
                    f"Desvio padrão: {resumo_disc['desvio_padrao']} p.p.",
                    estilo_corpo,
                )
            )
            _add_fig(
                grafico_histograma_gaussiana(
                    df_disc["discursiva_percentual"], "Aproveitamento na discursiva (%)", xlabel="Aproveitamento (%)"
                )
            )
            if df_disc["turma"].nunique(dropna=True) >= 2:
                linhas_turma_disc = []
                for turma_nome, grupo in df_disc.groupby("turma", dropna=False):
                    s = resumo_estatistico(grupo["discursiva_percentual"])
                    linhas_turma_disc.append((turma_nome or "—", s["media"]))
                _add_fig(
                    grafico_barras_comparativo(
                        [l[0] for l in linhas_turma_disc], [l[1] for l in linhas_turma_disc],
                        "Aproveitamento médio na discursiva, por turma", ylabel="Aproveitamento (%)",
                    )
                )
        else:
            story.append(Paragraph("Nenhuma correção com a discursiva avaliada, nesse filtro.", estilo_corpo))

    # -----------------------------------------------------------------
    # 5a/5b. Desempenho por questão e por objeto de conhecimento
    #        (exigem simulado especifico com gabarito) — calculo
    #        compartilhado, exibicao independente por secao.
    # -----------------------------------------------------------------
    precisa_calculo_questoes = _incluir("desempenho_questoes") or _incluir("desempenho_temas")
    if precisa_calculo_questoes:
        if simulado is not None and simulado.get("gabarito_dict"):
            gabarito = simulado["gabarito_dict"]
            temas_questoes = simulado.get("temas_questoes_dict") or {}
            certos = errados = brancos = 0
            acertos_por_questao = {q: 0 for q in gabarito}
            acertos_por_tema = {}
            total_por_tema = {}
            for respostas_json in df["respostas"]:
                respostas = json.loads(respostas_json) if respostas_json else {}
                for q, correta in gabarito.items():
                    marcada = respostas.get(q)
                    tema = temas_questoes.get(q)
                    if tema:
                        total_por_tema[tema] = total_por_tema.get(tema, 0) + 1
                    if marcada == correta:
                        certos += 1
                        acertos_por_questao[q] += 1
                        if tema:
                            acertos_por_tema[tema] = acertos_por_tema.get(tema, 0) + 1
                    elif not marcada:
                        brancos += 1
                    else:
                        errados += 1

            if _incluir("desempenho_questoes"):
                _iniciar_secao("Desempenho por questão")
                _add_fig(
                    grafico_pizza_status(
                        {"Certo": certos, "Errado": errados, "Em branco": brancos}, "Desempenho geral nas questões"
                    ),
                    largura=9 * cm,
                )
                total = len(df)
                serie = pd.Series({int(q): 100 * acertos_por_questao[q] / total for q in sorted(gabarito, key=int)})
                _add_fig(grafico_percentual_por_questao(serie, "Percentual de acerto por questão"))
                piores = serie.sort_values().head(5)
                story.append(
                    Paragraph(
                        "Questões com menor % de acerto: " + ", ".join(f"Q{q} ({v:.0f}%)" for q, v in piores.items()),
                        estilo_corpo,
                    )
                )

            if _incluir("desempenho_temas"):
                _iniciar_secao("Desempenho por objeto de conhecimento")
                if total_por_tema:
                    percentuais_tema = {
                        tema: 100 * acertos_por_tema.get(tema, 0) / tot for tema, tot in total_por_tema.items()
                    }
                    story.append(
                        Paragraph(
                            "Calculado a partir dos temas associados a cada questão (página Simulados e Gabaritos).",
                            estilo_corpo,
                        )
                    )
                    _add_fig(grafico_desempenho_por_tema(percentuais_tema, "Percentual de acerto por objeto de conhecimento"))
                    piores_temas = sorted(percentuais_tema.items(), key=lambda x: x[1])[:5]
                    story.append(
                        Paragraph(
                            "Objetos de conhecimento que mais precisam de atenção: "
                            + ", ".join(f"{tema} ({v:.0f}%)" for tema, v in piores_temas),
                            estilo_corpo,
                        )
                    )
                else:
                    story.append(
                        Paragraph(
                            "Nenhum tema/objeto de conhecimento associado às questões deste simulado ainda. "
                            "Cadastre-os na página Simulados e Gabaritos (seção \"Temas das questões\") para "
                            "habilitar esta análise.",
                            estilo_corpo,
                        )
                    )
        else:
            if _incluir("desempenho_questoes"):
                _iniciar_secao("Desempenho por questão")
                story.append(
                    Paragraph(
                        "Escolha um simulado específico no filtro (em vez de \"Todos\") para incluir o "
                        "desempenho por questão neste relatório.",
                        estilo_corpo,
                    )
                )
            if _incluir("desempenho_temas"):
                _iniciar_secao("Desempenho por objeto de conhecimento")
                story.append(
                    Paragraph(
                        "Escolha um simulado específico no filtro (em vez de \"Todos\") para incluir esta análise.",
                        estilo_corpo,
                    )
                )

    # -----------------------------------------------------------------
    # 6. Tempo x Nota
    # -----------------------------------------------------------------
    if _incluir("tempo_nota"):
        df_tempo = df.dropna(subset=["tempo_prova_minutos", "nota_1000"])
        if len(df_tempo) >= 3:
            _iniciar_secao("Tempo de prova x nota")
            fig_tempo, coef = grafico_dispersao_tempo_nota(
                df_tempo["tempo_prova_minutos"], df_tempo["nota_1000"], "Tempo de prova x Nota"
            )
            _add_fig(fig_tempo)
            story.append(Paragraph(f"Coeficiente de correlação de Pearson: {coef:.2f}", estilo_corpo))

    # -----------------------------------------------------------------
    # 8. Quartis e percentis
    # -----------------------------------------------------------------
    if _incluir("quartis_percentis"):
        _iniciar_secao("Quartis e percentis das notas")
        qs = quartis_percentis(df["nota_1000"])
        if qs:
            story.append(_tabela_simples(
                ["Mín.", "P10", "Q1 (P25)", "Mediana", "Q3 (P75)", "P90", "Máx."],
                [tuple(f"{qs[k]:.0f}" for k in ["min", "p10", "q1", "mediana", "q3", "p90", "max"])]))
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                f"25% dos alunos tiraram até {qs['q1']:.0f}; metade, até {qs['mediana']:.0f}; "
                f"75%, até {qs['q3']:.0f}. Amplitude interquartil: {qs['q3'] - qs['q1']:.0f} pontos.", estilo_corpo))
            _add_fig(grafico_histograma_quartis(df["nota_1000"]))
        else:
            story.append(Paragraph("Sem notas para calcular.", estilo_corpo))

    # -----------------------------------------------------------------
    # 9. Objetivas x discursiva
    # -----------------------------------------------------------------
    if _incluir("objetiva_discursiva"):
        _iniciar_secao("Objetivas x discursiva", quebra=False)
        dd = df.dropna(subset=["nota", "discursiva_pontos", "discursiva_pontos_max"])
        fig_od, r_od = grafico_objetivas_discursiva(dd["nota"], 100 * dd["discursiva_pontos"] / dd["discursiva_pontos_max"])
        if fig_od is not None:
            story.append(Paragraph(
                f"Correlação de Pearson entre o acerto nas objetivas e o aproveitamento na discursiva: "
                f"{r_od:.2f} ({interpretar_correlacao(r_od)}), com {len(dd)} alunos.", estilo_corpo))
            _add_fig(fig_od, largura=10 * cm)
        else:
            story.append(Paragraph("São necessárias pelo menos 3 correções com a discursiva avaliada.", estilo_corpo))

    # -----------------------------------------------------------------
    # 10. Alunos em risco
    # -----------------------------------------------------------------
    if _incluir("alunos_risco"):
        _iniciar_secao("Alunos em risco")
        risco = alunos_em_risco(df_evolucao if df_evolucao is not None else df, corte_risco, queda_risco)
        story.append(Paragraph(
            f"Critérios: última nota abaixo de {corte_risco:.0f} ou queda de {queda_risco:.0f} pontos (ou mais) em "
            f"relação ao simulado anterior. {len(risco)} aluno(s) identificado(s).", estilo_corpo))
        if len(risco):
            story.append(Spacer(1, 4))
            story.append(_tabela_simples(
                ["Aluno", "Turma", "Última", "Anterior", "Variação", "Motivo"],
                [(str(r.aluno), str(r.turma or "—"), f"{r.ultima:.0f}",
                  "—" if pd.isna(r.anterior) else f"{r.anterior:.0f}",
                  "—" if pd.isna(r.variacao) else f"{r.variacao:+.0f}", r.motivo)
                 for r in risco.itertuples()][:40]))
            if len(risco) > 40:
                story.append(Paragraph(f"(mostrando os 40 de menor nota, de {len(risco)})", estilo_corpo))

    # -----------------------------------------------------------------
    # 11-14. Analises por questao (exigem simulado especifico com gabarito)
    # -----------------------------------------------------------------
    pede_psico = any(_incluir(k) for k in ("dificuldade_discriminacao", "distratores", "confiabilidade", "blocos_fg_esp"))
    gab = simulado.get("gabarito_dict") if simulado else None
    if pede_psico and not gab:
        for chave, titulo in [("dificuldade_discriminacao", "Dificuldade e discriminação por questão"),
                              ("distratores", "Análise dos distratores"),
                              ("confiabilidade", "Confiabilidade da prova"),
                              ("blocos_fg_esp", "Formação Geral x Componente Específico")]:
            if _incluir(chave):
                _iniciar_secao(titulo, quebra=(chave != "confiabilidade"))
                story.append(Paragraph(
                    "Escolha um simulado específico no filtro (em vez de \"Todos\") para incluir esta análise.",
                    estilo_corpo))
    elif pede_psico:
        M = matriz_acertos(df, gab)
        if _incluir("dificuldade_discriminacao"):
            _iniciar_secao("Dificuldade e discriminação por questão")
            tab = dificuldade_discriminacao(M)
            story.append(Paragraph(
                "Dificuldade = % de acerto. Discriminação = correlação entre acertar a questão e o total nas demais "
                "(≥ 0,30 boa; 0,20–0,29 razoável; < 0,20 baixa; negativa = bons alunos erram mais que os fracos — "
                "revisar gabarito/enunciado ou considerar anulação). Requer ao menos 5 alunos.", estilo_corpo))
            fig_dd = grafico_dificuldade_discriminacao(tab)
            if fig_dd is not None:
                story.append(Spacer(1, 4))
                _add_fig(fig_dd, largura=13 * cm)
                alvo = tab.dropna(subset=["discriminacao"]).sort_values("discriminacao").head(8)
                story.append(_tabela_simples(
                    ["Questão", "% acerto", "Discriminação", "Classificação"],
                    [(f"Q{int(r.questao)}", f"{r.acerto_pct:.0f}%", f"{r.discriminacao:.2f}",
                      classificar_discriminacao(r.discriminacao)) for r in alvo.itertuples()]))
                story.append(Paragraph("Questões com menor discriminação (as 8 piores).", estilo_corpo))
            else:
                story.append(Paragraph("Dados insuficientes (poucos alunos ou sem variação nas respostas).", estilo_corpo))

        if _incluir("distratores"):
            _iniciar_secao("Análise dos distratores")
            dist = tabela_distratores(df, gab)
            achados = distratores_dominantes(dist, gab)
            if achados:
                story.append(Paragraph(
                    "Alternativas erradas marcadas por 30% ou mais dos alunos (indício de concepção equivocada comum):",
                    estilo_corpo))
                story.append(_tabela_simples(
                    ["Questão", "Distrator", "% que marcou", "% que acertou"],
                    [(f"Q{q}", a, f"{p:.0f}%", f"{c:.0f}%") for q, a, p, c in achados]))
            else:
                story.append(Paragraph("Nenhum distrator concentrou 30% ou mais das respostas.", estilo_corpo))
            story.append(Spacer(1, 4))
            _add_fig(grafico_distratores(dist, gab), largura=11 * cm)

        if _incluir("confiabilidade"):
            _iniciar_secao("Confiabilidade da prova", quebra=False)
            alfa = alfa_kr20(M)
            if alfa is None:
                story.append(Paragraph("Dados insuficientes para calcular (poucos alunos ou sem variação no total).", estilo_corpo))
            else:
                story.append(Paragraph(
                    f"Alfa de Cronbach (KR-20 para itens certo/errado): <b>{alfa:.2f}</b> — {interpretar_alfa(alfa)}. "
                    "Valores acima de 0,70 costumam ser considerados aceitáveis para simulados; com poucos alunos a "
                    "estimativa é instável.", estilo_corpo))

        if _incluir("blocos_fg_esp"):
            _iniciar_secao("Formação Geral x Componente Específico", quebra=False)
            dfb = desempenho_por_bloco(df, gab, simulado.get("temas_questoes_dict") or {})
            if dfb.attrs.get("n_fg", 0) == 0 and dfb.attrs.get("n_esp", 0) == 0:
                story.append(Paragraph(
                    "Nenhuma questão com tema das listas oficiais cadastrado neste simulado (página Simulados e Gabaritos).",
                    estilo_corpo))
            else:
                story.append(Paragraph(
                    f"Questões de Formação Geral: {dfb.attrs['n_fg']} · Componente Específico: {dfb.attrs['n_esp']} "
                    "(classificadas pelo tema cadastrado em cada questão). Média de acerto: "
                    f"Formação Geral {dfb['fg_pct'].mean():.0f}% · Específico {dfb['esp_pct'].mean():.0f}%.", estilo_corpo))
                _add_fig(grafico_blocos(dfb), largura=13 * cm)

    # -----------------------------------------------------------------
    # 7. Evolucao individual (pontos anonimos)
    # -----------------------------------------------------------------
    if _incluir("evolucao_alunos"):
        _iniciar_secao("Evolução individual dos alunos")
        larga = tabela_evolucao_alunos(df_evolucao if df_evolucao is not None else df)
        if larga.empty or larga.shape[1] < 2:
            story.append(
                Paragraph(
                    "Para mostrar a evolução é preciso que pelo menos um aluno tenha corrigido 2 ou mais "
                    "simulados (considerando a turma/aluno filtrados).", estilo_corpo))
        else:
            res = resumo_evolucao(larga)
            story.append(Paragraph(
                f"Alunos com 2+ simulados: {res['n']} &nbsp;·&nbsp; evoluíram: {res['evoluiu']} "
                f"({100 * res['evoluiu'] / res['n']:.0f}%) &nbsp;·&nbsp; regrediram: {res['regrediu']} "
                f"({100 * res['regrediu'] / res['n']:.0f}%) &nbsp;·&nbsp; estáveis: {res['estavel']}<br/>"
                f"Variação média entre o primeiro e o último simulado: {res['delta_medio']:+.0f} pontos "
                f"(mediana {res['delta_mediano']:+.0f}). Cada ponto é um aluno, sem identificação.",
                estilo_corpo))
            story.append(Spacer(1, 4))
            _add_fig(grafico_evolucao_pontos(larga), largura=14 * cm)
            _add_fig(grafico_evolucao_dispersao(res), largura=9 * cm)

    if not algo_adicionado:
        story.append(Paragraph("Nenhuma seção selecionada para este relatório.", estilo_corpo))

    doc.build(story, onFirstPage=_desenhar_timbre, onLaterPages=_desenhar_timbre)
    buffer.seek(0)
    return buffer.getvalue()
