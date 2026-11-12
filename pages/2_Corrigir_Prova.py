"""
Pagina: corrigir provas.
Modo Individual: uma folha por vez, com avaliacao opcional da discursiva.
Modo Em lote: varias fotos de cartao de resposta de uma vez, associando
aluno/turma de cada uma; a discursiva pode ser anexada (para avaliar
depois, na pagina Historico) ou pulada neste momento.
"""

import io
import os
import uuid
from datetime import time as dtime

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from auth import exigir_login
from PIL import Image

from config import load_config
from db import (
    create_aluno,
    create_correcao,
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
from ai_grading import IAGradingError, identify_student
from ui_common import (
    seletor_ia_ui,
    annotate,
    answers_to_df,
    capture_image_ui,
    corrigir_discursivas_em_lote_ui,
    df_to_answers,
    discursiva_grading_ui,
    discursivas_pdf_lote_ui,
    editable_answers_table,
    run_omr,
)

st.set_page_config(page_title="Corrigir Prova", layout="wide")

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

st.title("Corrigir Prova")


def _jpeg_bytes(pil_img, largura_max=1000, recorte_topo=None):
    """JPEG leve da pagina (ou so do topo, onde ficam nome e CPF) para exibir/enviar a IA."""
    img = pil_img
    if recorte_topo:
        img = img.crop((0, 0, img.width, int(img.height * recorte_topo)))
    if img.width > largura_max:
        img = img.resize((largura_max, int(img.height * largura_max / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _salvar_imagem_discursiva(imagem_bytes):
    if imagem_bytes is None:
        return None
    os.makedirs(DISCURSIVAS_DIR, exist_ok=True)
    caminho = os.path.join(DISCURSIVAS_DIR, f"{uuid.uuid4().hex}.jpg")
    with open(caminho, "wb") as f:
        f.write(imagem_bytes)
    return caminho


# ---------------------------------------------------------------------------
# Pré-requisitos: simulado com gabarito e pelo menos uma turma
# ---------------------------------------------------------------------------
simulados_df = list_simulados()
com_gabarito = simulados_df[simulados_df["tem_gabarito"]] if len(simulados_df) else simulados_df

if len(com_gabarito) == 0:
    st.warning(
        "Nenhum simulado com gabarito definido ainda. Vá em **Simulados e Gabaritos** para "
        "cadastrar um simulado e definir o gabarito antes de corrigir provas."
    )
    st.stop()

turmas_df = list_turmas()
if len(turmas_df) == 0:
    st.warning(
        "Nenhuma turma cadastrada ainda. Vá em **Turmas e Alunos** para cadastrar pelo menos "
        "uma turma antes de corrigir provas."
    )
    st.stop()

opcoes_simulado = {f"#{row.id} — {row.nome}": row.id for row in com_gabarito.itertuples()}
escolha_simulado = st.selectbox("Simulado", list(opcoes_simulado.keys()))
simulado_id = opcoes_simulado[escolha_simulado]
simulado = get_simulado(simulado_id)
gabarito = {int(q): letra for q, letra in simulado["gabarito_dict"].items()}
tem_rubrica = bool((simulado.get("rubrica_discursiva") or "").strip())

modo = st.radio("Modo de correção", ["Individual", "Em lote"], horizontal=True)

with st.expander("Ajuste fino da leitura"):
    fill_threshold = st.slider(
        "Sensibilidade mínima de preenchimento", 0.10, 0.80, float(cfg["fill_threshold"]), step=0.05
    )
    relative_margin = st.slider(
        "Margem relativa (marca vs. demais bolhas)", 1.05, 2.0, float(cfg["relative_margin"]), step=0.05
    )

with st.expander("Discursivas em lote: um PDF único, uma página por aluno (nome pela IA)"):
    st.caption("Vale para o simulado selecionado acima.")
    discursivas_pdf_lote_ui(simulado_id, key_prefix="pdfdisc")

with st.expander("Correção em lote das discursivas já cadastradas (IA)"):
    st.caption("Vale para o simulado selecionado acima.")
    corrigir_discursivas_em_lote_ui(list_correcoes(simulado_id=simulado_id), key_prefix="corrigir")

st.divider()

# ===========================================================================
# MODO INDIVIDUAL
# ===========================================================================
if modo == "Individual":
    col_t, col_a = st.columns(2)

    opcoes_turma = {row.nome: row.id for row in turmas_df.itertuples()}
    nome_turma_escolhida = col_t.selectbox("Turma", list(opcoes_turma.keys()), key="turma_corrigir")
    turma_id = opcoes_turma[nome_turma_escolhida]

    alunos_df = list_alunos(turma_id=turma_id)
    opcoes_aluno = {row.nome: row.id for row in alunos_df.itertuples()}

    with col_a:
        if opcoes_aluno:
            nome_aluno_escolhido = st.selectbox("Aluno", list(opcoes_aluno.keys()), key=f"aluno_corrigir_{turma_id}")
            aluno_id = opcoes_aluno[nome_aluno_escolhido]
            aluno_nome = nome_aluno_escolhido
        else:
            st.info("Nenhum aluno cadastrado nesta turma ainda.")
            aluno_id = None
            aluno_nome = ""

    with st.expander("Cadastrar novo aluno nesta turma"):
        with st.form(f"novo_aluno_rapido_{turma_id}", clear_on_submit=True):
            nome_novo_aluno = st.text_input("Nome completo do novo aluno")
            cadastrar = st.form_submit_button("Cadastrar e selecionar")
            if cadastrar:
                if not nome_novo_aluno.strip():
                    st.error("Informe o nome do aluno.")
                else:
                    create_aluno(nome_novo_aluno, turma_id=turma_id)
                    st.session_state[f"aluno_corrigir_{turma_id}"] = nome_novo_aluno.strip()
                    st.success(f'Aluno "{nome_novo_aluno}" cadastrado e selecionado.')
                    st.rerun()

    aluno, turma = aluno_nome, nome_turma_escolhida

    with st.expander("Horário da prova (opcional)"):
        st.caption(
            "Preencha para o sistema calcular o tempo de duração da prova deste aluno e cruzar "
            "isso com a nota no Dashboard."
        )
        col_hi, col_hf = st.columns(2)
        usar_horario = st.checkbox("Registrar horário desta prova", key="usar_horario")
        hora_inicio_input = col_hi.time_input(
            "Início", value=dtime(8, 0), key="hora_inicio_input", disabled=not usar_horario, step=60
        )
        hora_fim_input = col_hf.time_input(
            "Término", value=dtime(10, 0), key="hora_fim_input", disabled=not usar_horario, step=60
        )

    st.divider()
    st.subheader("Questões objetivas (01 a 31)")
    image_bgr = capture_image_ui(key_prefix="corrigir")

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

        annotated = annotate(warped, template, CANVAS_W, CANVAS_H, answers, gabarito=gabarito)
        st.image(
            cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
            caption="Verde = acerto | Vermelho = erro | Laranja = resposta correta não marcada",
            width='stretch',
        )

        st.markdown("**Revise e corrija a leitura, se necessário, antes de salvar:**")
        df_detectado = answers_to_df(answers, N_QUESTIONS)
        edited_df = editable_answers_table(df_detectado, key=f"corrigir_editor_{simulado_id}")
        respostas_finais = df_to_answers(edited_df)

        linhas = []
        acertos = 0
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
        st.subheader("Questão discursiva (32)")
        avaliacao_disc = discursiva_grading_ui(simulado, key_prefix=f"individual_{simulado_id}", cfg=cfg)

        st.divider()
        st.subheader("Nota final")
        st.caption(
            "Conversão proporcional simples para a escala 0-1000 (não é o cálculo oficial por "
            "TRI usado pelo INEP — veja a explicação no README). A questão discursiva vale "
            f"{cfg['peso_discursiva_pontos']:.0f} dos 1000 pontos (ajustável em Configurações); "
            "o restante é dividido entre as questões objetivas."
        )
        resultado_nota = calcular_nota_1000(
            acertos, N_QUESTIONS, avaliacao_disc["pontos"], avaliacao_disc["pontos_max"],
            peso_discursiva_pontos=cfg["peso_discursiva_pontos"],
        )
        nota_1000 = resultado_nota["nota_1000"]
        if not resultado_nota["discursiva_avaliada"] and tem_rubrica:
            st.info(
                "A questão discursiva ainda não foi avaliada — a nota abaixo está considerando "
                "0 pontos nela. Você pode avaliar a discursiva depois, na página Histórico, e a "
                "nota será recalculada automaticamente."
            )
        st.metric("Nota (escala 0-1000)", f"{nota_1000:.1f}")

        hora_inicio_iso = hora_fim_iso = None
        tempo_prova_minutos = None
        if usar_horario and hora_inicio_input and hora_fim_input:
            hora_inicio_iso = hora_inicio_input.isoformat()
            hora_fim_iso = hora_fim_input.isoformat()
            tempo_prova_minutos = calcular_tempo_prova_minutos(hora_inicio_input, hora_fim_input)
            st.caption(f"Tempo de prova: {tempo_prova_minutos:.0f} minutos.")
        elif usar_horario:
            st.warning("Preencha os dois horários (início e término) para calcular o tempo de prova.")

        st.divider()
        pode_salvar = aluno_id is not None

        correcao_existente_id = None
        if aluno_id is not None:
            existentes = list_correcoes(simulado_id=simulado_id, aluno_id=aluno_id)
            if len(existentes):
                correcao_existente_id = int(existentes.iloc[0]["id"])
                st.warning(
                    f"Este aluno já tem uma correção salva para este simulado (#{correcao_existente_id}, "
                    f"{existentes.iloc[0]['data'][:16].replace('T', ' ')}). Salvar agora vai "
                    "**atualizar** essa correção, não criar uma nova."
                )

        if not pode_salvar:
            st.info("Selecione (ou cadastre) um aluno acima para poder salvar a correção.")

        rotulo_botao = "Atualizar correção existente" if correcao_existente_id else "Salvar correção no histórico"
        if st.button(rotulo_botao, disabled=not pode_salvar, type="primary"):
            caminho_imagem_disc = _salvar_imagem_discursiva(avaliacao_disc["imagem_bytes"])
            campos_correcao = dict(
                aluno=aluno,
                turma=turma,
                respostas={str(q): letra for q, letra in respostas_finais.items()},
                acertos=acertos,
                n_questoes=N_QUESTIONS,
                nota=nota,
                discursiva_pontos=avaliacao_disc["pontos"],
                discursiva_pontos_max=avaliacao_disc["pontos_max"],
                discursiva_avaliacao=avaliacao_disc["avaliacao"],
                discursiva_imagem_path=caminho_imagem_disc,
                aluno_id=aluno_id,
                turma_id=turma_id,
                hora_inicio=hora_inicio_iso,
                hora_fim=hora_fim_iso,
                tempo_prova_minutos=tempo_prova_minutos,
                nota_1000=nota_1000,
                discursiva_pontos_1000=resultado_nota["pontos_discursiva_1000"],
            )
            if correcao_existente_id:
                update_correcao(correcao_existente_id, **campos_correcao)
            else:
                create_correcao(simulado_id=simulado_id, **campos_correcao)
            verbo = "atualizada" if correcao_existente_id else "salva"
            msg = (
                f"Correção de {aluno} {verbo}! Nota objetiva: {acertos}/{N_QUESTIONS} ({nota:.1f}%) "
                f"· Nota 0-1000: {nota_1000:.1f}"
            )
            if avaliacao_disc["pontos"] is not None:
                msg += f" · Discursiva: {avaliacao_disc['pontos']:.1f}/{avaliacao_disc['pontos_max']:.0f}"
            st.success(msg)
    else:
        st.info("Envie uma imagem, um PDF ou tire uma foto da folha do aluno para começar.")

# ===========================================================================
# MODO EM LOTE
# ===========================================================================
else:
    st.subheader("Correção em lote — questões objetivas")
    st.caption(
        "Envie várias fotos do cartão de respostas de uma vez (uma foto por aluno). O sistema "
        "lê cada uma automaticamente — depois é só associar o aluno e a turma de cada foto e "
        "revisar antes de salvar. Aceita imagens (jpg/png) e PDFs — em PDF, cada página "
        "é tratada como o cartão de um aluno (serve tanto para vários PDFs de uma página quanto "
        "para um único PDF escaneado com todos os cartões). Para câmera, use o modo Individual."
    )

    turma_padrao_nome = st.selectbox(
        "Turma padrão deste lote (pode trocar individualmente em cada foto)",
        [row.nome for row in turmas_df.itertuples()],
        key="lote_turma_padrao",
    )
    opcoes_turma_lote = {row.nome: row.id for row in turmas_df.itertuples()}
    turma_padrao_id = opcoes_turma_lote[turma_padrao_nome]

    arquivos = st.file_uploader(
        "Fotos ou PDFs dos cartões de resposta",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        key="lote_upload",
    )

    if arquivos:
        assinatura = tuple((f.name, f.size) for f in arquivos)
        if st.session_state.get("lote_assinatura") != assinatura:
            st.session_state["lote_assinatura"] = assinatura
            with st.spinner(f"Processando {len(arquivos)} arquivo(s)..."):
                resultados = []
                paginas = []  # (rotulo, PIL.Image)
                for f in arquivos:
                    if f.name.lower().endswith(".pdf"):
                        try:
                            import fitz
                            doc = fitz.open(stream=f.getvalue(), filetype="pdf")
                            n_pag = len(doc)
                            for pn in range(n_pag):
                                pix = doc[pn].get_pixmap(matrix=fitz.Matrix(3, 3))
                                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                                rotulo = f"{f.name} — pág. {pn + 1}" if n_pag > 1 else f.name
                                paginas.append((rotulo, img))
                            doc.close()
                        except Exception as e:
                            st.error(f"Não consegui ler o PDF {f.name}: {e}")
                    else:
                        paginas.append((f.name, Image.open(f).convert("RGB")))
                for rotulo, pil_img in paginas:
                    image_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                    warped, answers, fills, corners_found = run_omr(
                        image_bgr, template, CANVAS_W, CANVAS_H, fill_threshold, relative_margin
                    )
                    annotated = annotate(warped, template, CANVAS_W, CANVAS_H, answers, gabarito=gabarito)
                    acertos = sum(1 for q, correta in gabarito.items() if answers.get(q) == correta)
                    resultados.append(
                        {
                            "nome_arquivo": rotulo,
                            "pagina_jpg": _jpeg_bytes(pil_img),
                            "cabecalho_jpg": _jpeg_bytes(pil_img, recorte_topo=0.32),
                            "annotated": annotated,
                            "answers": answers,
                            "acertos": acertos,
                            "corners_found": corners_found,
                        }
                    )
                st.session_state["lote_resultados"] = resultados
                st.session_state["lote_ident"] = {}
            st.success(f"{len(st.session_state['lote_resultados'])} cartão(ões) processado(s). Revise e associe cada aluno abaixo.")

        resultados = st.session_state.get("lote_resultados", [])

        st.divider()
        st.subheader(f"Revisão ({len(resultados)} foto(s))")

        # ------------------------------------------------------------------
        # Identificacao automatica dos alunos pela IA (le nome/CPF no cabecalho)
        # ------------------------------------------------------------------
        st.session_state.setdefault("lote_ident", {})
        with st.expander("Identificar os alunos automaticamente com IA"):
            st.caption(
                "A IA lê o nome (e o CPF) escritos no topo de cada cartão e escolhe, na lista de alunos "
                "cadastrados, o mais parecido. Ela só preenche a turma e o aluno de cada cartão — você "
                "continua podendo conferir e trocar um a um abaixo. Em caso de dúvida a IA deixa em branco."
            )
            ia_ident = seletor_ia_ui(cfg, "lote_ident")
            buscar_todas = st.checkbox(
                "Buscar em todas as turmas (em vez de só na turma padrão)", value=False, key="lote_ident_todas"
            )
            so_vazios = st.checkbox("Só cartões ainda sem aluno definido", value=True, key="lote_ident_so_vazios")
            if st.button("Identificar alunos", type="primary", disabled=not ia_ident["api_key"], key="lote_ident_btn"):
                if buscar_todas:
                    cand_df = list_alunos()
                    mapa_cand = {f"{r.nome} ({r.turma})": (r.id, r.turma_id, r.turma) for r in cand_df.itertuples()}
                else:
                    cand_df = list_alunos(turma_id=turma_padrao_id)
                    mapa_cand = {r.nome: (r.id, r.turma_id, turma_padrao_nome) for r in cand_df.itertuples()}
                barra_id = st.progress(0.0, text="Identificando...")
                n_ok = n_pulados = n_sem_match = n_erros = 0
                for i_id, it_id in enumerate(resultados):
                    barra_id.progress(i_id / max(len(resultados), 1), text=f"Cartão {i_id + 1}/{len(resultados)}...")
                    atual = st.session_state.get(f"lote_aluno_{i_id}", "— selecionar —")
                    if so_vazios and atual not in (None, "— selecionar —"):
                        n_pulados += 1
                        continue
                    try:
                        res_id = identify_student(it_id["cabecalho_jpg"], list(mapa_cand.keys()), ia_ident)
                    except IAGradingError as e:
                        st.session_state["lote_ident"][i_id] = {"erro": str(e)}
                        n_erros += 1
                        continue
                    st.session_state["lote_ident"][i_id] = res_id
                    if res_id["aluno_sugerido"]:
                        _aid, _tid, _tnome = mapa_cand[res_id["aluno_sugerido"]]
                        nome_aluno = next(r.nome for r in list_alunos(turma_id=_tid).itertuples() if r.id == _aid)
                        st.session_state[f"lote_turma_{i_id}"] = _tnome
                        st.session_state[f"lote_aluno_{i_id}"] = nome_aluno
                        n_ok += 1
                    else:
                        n_sem_match += 1
                barra_id.progress(1.0, text="Concluído.")
                resumo_id = [f"{n_ok} associado(s) agora"]
                if n_pulados:
                    resumo_id.append(f"{n_pulados} ignorado(s) por já terem aluno definido")
                if n_sem_match:
                    resumo_id.append(f"{n_sem_match} sem correspondência na lista")
                if n_erros:
                    resumo_id.append(f"{n_erros} com erro de IA")
                msg_id = " · ".join(resumo_id) + "."
                if n_pulados and not n_ok:
                    st.warning(
                        msg_id + " Para identificar de novo, desmarque \"Só cartões ainda sem aluno definido\" "
                        "acima e clique outra vez (isso sobrescreve as escolhas atuais)."
                    )
                else:
                    st.success(msg_id + " Confira abaixo — os que ficaram sem aluno exigem seleção manual.")

        # tabela de diagnostico da ultima identificacao (o que a IA leu em cada cartao)
        _ident_all = st.session_state.get("lote_ident", {})
        if _ident_all:
            _linhas = []
            for _i, _r in sorted(_ident_all.items()):
                if "erro" in _r:
                    _linhas.append({"Cartão": _i + 1, "Nome lido pela IA": "", "CPF lido": "", "Aluno sugerido": "",
                                    "Confiança": "", "Erro": _r["erro"][:200]})
                else:
                    _linhas.append({"Cartão": _i + 1, "Nome lido pela IA": _r["nome_lido"], "CPF lido": _r["cpf_lido"],
                                    "Aluno sugerido": _r["aluno_sugerido"] or "(nenhum)", "Confiança": _r["confianca"],
                                    "Erro": ""})
            with st.expander("O que a IA leu em cada cartão (diagnóstico da última identificação)"):
                st.dataframe(pd.DataFrame(_linhas), width='stretch', hide_index=True)

        abrir_todos = st.checkbox("Mostrar todos os cartões abertos", value=False, key="lote_abrir_todos")

        itens_para_salvar = []
        for i, item in enumerate(resultados):
            nota_previa = 100 * item["acertos"] / N_QUESTIONS
            _al = st.session_state.get(f"lote_aluno_{i}")
            _rot_aluno = _al if _al and _al != "— selecionar —" else "sem aluno"
            with st.expander(
                f"{i + 1}. {item['nome_arquivo']} — {_rot_aluno} — {item['acertos']}/{N_QUESTIONS} ({nota_previa:.0f}%)",
                expanded=abrir_todos,
            ):
                if not item["corners_found"]:
                    st.warning("Não detectei a moldura da tabela nesta foto — confira a leitura com atenção.")

                col_img, col_dados = st.columns([2, 1])
                with col_img:
                    aba_pag, aba_leitura = st.tabs(["Documento original", "Leitura das marcações"])
                    with aba_pag:
                        st.image(item["pagina_jpg"], width='stretch')
                    with aba_leitura:
                        st.image(cv2.cvtColor(item["annotated"], cv2.COLOR_BGR2RGB), width='stretch')

                ident = st.session_state.get("lote_ident", {}).get(i)
                if ident:
                    if "erro" in ident:
                        col_dados.error(f"Identificação por IA falhou: {ident['erro']}")
                    else:
                        txt = f"IA leu: \"{ident['nome_lido'] or '—'}\""
                        if ident["cpf_lido"]:
                            txt += f" · CPF {ident['cpf_lido']}"
                        txt += f" · confiança {ident['confianca']}"
                        if ident["aluno_sugerido"]:
                            col_dados.info(txt)
                        else:
                            col_dados.warning(txt + " — nenhum aluno da lista combinou; selecione manualmente.")

                turma_nome_item = col_dados.selectbox(
                    "Turma", list(opcoes_turma_lote.keys()),
                    index=list(opcoes_turma_lote.keys()).index(turma_padrao_nome),
                    key=f"lote_turma_{i}",
                )
                turma_id_item = opcoes_turma_lote[turma_nome_item]

                alunos_item_df = list_alunos(turma_id=turma_id_item)
                opcoes_aluno_item = {row.nome: row.id for row in alunos_item_df.itertuples()}
                aluno_escolhido = col_dados.selectbox(
                    "Aluno cadastrado",
                    ["— selecionar —"] + list(opcoes_aluno_item.keys()),
                    key=f"lote_aluno_{i}",
                )
                novo_aluno_nome = col_dados.text_input(
                    "Ou cadastrar novo aluno nesta turma", key=f"lote_novo_aluno_{i}"
                )

                with st.expander("Revisar leitura desta prova (se necessário)"):
                    df_item = answers_to_df(item["answers"], N_QUESTIONS)
                    edited_item = editable_answers_table(df_item, key=f"lote_editor_{i}")
                    respostas_item = df_to_answers(edited_item)
                    acertos_revisados = sum(
                        1 for q, correta in gabarito.items() if respostas_item.get(q) == correta
                    )
                    if acertos_revisados != item["acertos"]:
                        st.caption(f"Após revisão: {acertos_revisados}/{N_QUESTIONS} acertos.")
                    respostas_finais_item = respostas_item
                    acertos_finais_item = acertos_revisados

                incluir_discursiva = st.checkbox(
                    "Anexar foto da resposta discursiva (avalia depois, na página Histórico)",
                    key=f"lote_disc_check_{i}",
                )
                imagem_disc_bytes_item = None
                if incluir_discursiva:
                    disc_file = st.file_uploader(
                        "Foto da resposta discursiva",
                        type=["jpg", "jpeg", "png"],
                        key=f"lote_disc_upload_{i}",
                    )
                    if disc_file:
                        pil_disc = Image.open(disc_file).convert("RGB")
                        disc_bgr = cv2.cvtColor(np.array(pil_disc), cv2.COLOR_RGB2BGR)
                        ok, buf = cv2.imencode(".jpg", disc_bgr)
                        imagem_disc_bytes_item = buf.tobytes() if ok else None

                itens_para_salvar.append(
                    {
                        "turma_id": turma_id_item,
                        "turma_nome": turma_nome_item,
                        "aluno_id": opcoes_aluno_item.get(aluno_escolhido),
                        "aluno_nome_existente": aluno_escolhido if aluno_escolhido != "— selecionar —" else None,
                        "novo_aluno_nome": novo_aluno_nome.strip(),
                        "respostas": respostas_finais_item,
                        "acertos": acertos_finais_item,
                        "imagem_discursiva_bytes": imagem_disc_bytes_item,
                    }
                )

        st.divider()
        prontos = [
            it for it in itens_para_salvar if it["aluno_id"] is not None or it["novo_aluno_nome"]
        ]
        st.caption(f"{len(prontos)} de {len(itens_para_salvar)} foto(s) com aluno definido.")

        if st.button(
            f"Salvar {len(prontos)} correção(ões) no histórico", disabled=len(prontos) == 0, type="primary"
        ):
            salvos = 0
            atualizados = 0
            for it in itens_para_salvar:
                aluno_id_final = it["aluno_id"]
                aluno_nome_final = it["aluno_nome_existente"]
                if aluno_id_final is None and it["novo_aluno_nome"]:
                    aluno_id_final = create_aluno(it["novo_aluno_nome"], turma_id=it["turma_id"])
                    aluno_nome_final = it["novo_aluno_nome"]
                if aluno_id_final is None:
                    continue  # sem aluno definido, pula

                caminho_imagem_disc = _salvar_imagem_discursiva(it["imagem_discursiva_bytes"])
                resultado_nota = calcular_nota_1000(
                    it["acertos"], N_QUESTIONS, None, None,
                    peso_discursiva_pontos=cfg["peso_discursiva_pontos"],
                )
                nota_pct = 100 * it["acertos"] / N_QUESTIONS

                campos_correcao_lote = dict(
                    aluno=aluno_nome_final,
                    turma=it["turma_nome"],
                    respostas={str(q): letra for q, letra in it["respostas"].items()},
                    acertos=it["acertos"],
                    n_questoes=N_QUESTIONS,
                    nota=nota_pct,
                    discursiva_imagem_path=caminho_imagem_disc,
                    aluno_id=aluno_id_final,
                    turma_id=it["turma_id"],
                    nota_1000=resultado_nota["nota_1000"],
                    discursiva_pontos_1000=resultado_nota["pontos_discursiva_1000"],
                )

                existentes_lote = list_correcoes(simulado_id=simulado_id, aluno_id=aluno_id_final)
                if len(existentes_lote):
                    update_correcao(int(existentes_lote.iloc[0]["id"]), **campos_correcao_lote)
                    atualizados += 1
                else:
                    create_correcao(simulado_id=simulado_id, **campos_correcao_lote)
                    salvos += 1

            partes_msg = []
            if salvos:
                partes_msg.append(f"{salvos} correção(ões) nova(s) salva(s)")
            if atualizados:
                partes_msg.append(f"{atualizados} correção(ões) existente(s) atualizada(s) (aluno já tinha registro neste simulado)")
            st.success(" · ".join(partes_msg) + " no histórico.")
            del st.session_state["lote_assinatura"]
            del st.session_state["lote_resultados"]
            st.rerun()
    else:
        st.info("Envie duas ou mais fotos de cartões de resposta para começar.")
