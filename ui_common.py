"""
ui_common.py
Componentes de interface reutilizados entre as paginas do app: captura de
imagem (upload/PDF/camera), execucao do pipeline OMR e a tabela editavel de
revisao das respostas detectadas (usada tanto para o gabarito oficial
quanto para as respostas de cada aluno).
"""

import io

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from omr_utils import alinhar_ao_template, read_answers_from_template, warp_to_canvas

ALTERNATIVES = ["A", "B", "C", "D", "E"]


def capture_image_ui(key_prefix: str):
    """Mostra os 3 modos de entrada (upload imagem / PDF / camera) e retorna a imagem BGR ou None."""
    input_mode = st.radio(
        "Fonte da imagem",
        ["Upload de imagem", "Upload de PDF", "Câmera"],
        horizontal=True,
        key=f"{key_prefix}_input_mode",
    )

    image_bgr = None

    if input_mode == "Upload de imagem":
        file = st.file_uploader(
            "Selecione uma imagem (jpg, png)",
            type=["jpg", "jpeg", "png"],
            key=f"{key_prefix}_upload_img",
        )
        if file:
            pil_img = Image.open(file).convert("RGB")
            image_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    elif input_mode == "Upload de PDF":
        file = st.file_uploader("Selecione um PDF", type=["pdf"], key=f"{key_prefix}_upload_pdf")
        if file:
            import fitz  # PyMuPDF

            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_num = 0
            if doc.page_count > 1:
                page_num = (
                    st.number_input(
                        "Página do cartão-resposta",
                        min_value=1,
                        max_value=doc.page_count,
                        value=1,
                        key=f"{key_prefix}_pdf_page",
                    )
                    - 1
                )
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            img_bytes = pix.tobytes("png")
            pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            image_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    elif input_mode == "Câmera":
        cam_file = st.camera_input("Tire uma foto do cartão-resposta", key=f"{key_prefix}_camera")
        if cam_file:
            pil_img = Image.open(cam_file).convert("RGB")
            image_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    return image_bgr


def run_omr(image_bgr, template, canvas_w, canvas_h, fill_threshold, relative_margin):
    """Corrige a perspectiva e le as marcacoes. Retorna (warped, answers, fills, corners_found)."""
    warped, corners_found = warp_to_canvas(image_bgr, canvas_w, canvas_h)
    warped, _ = alinhar_ao_template(warped, template["questions"], canvas_w, canvas_h)
    answers, fills = read_answers_from_template(
        warped,
        template["questions"],
        canvas_w,
        canvas_h,
        fill_threshold=fill_threshold,
        relative_margin=relative_margin,
    )
    return warped, answers, fills, corners_found


def annotate(warped, template, canvas_w, canvas_h, answers, gabarito=None):
    """
    Desenha um circulo em cada resposta detectada.
    Se `gabarito` (dict {q_num: letra}) for informado, colore verde/vermelho
    (acerto/erro) e marca em laranja a resposta correta nao assinalada.
    Sem gabarito, usa uma cor neutra (uso na tela de cadastro do gabarito).
    """
    annotated = warped.copy()
    radius_px = max(int(0.008 * canvas_w), 4)

    for q_str, alts in template["questions"].items():
        q_num = int(q_str)
        marked = answers.get(q_num)
        correct = gabarito.get(q_num) if gabarito else None

        for letra, (xf, yf) in alts.items():
            cx, cy = int(xf * canvas_w), int(yf * canvas_h)
            if letra == marked:
                if gabarito:
                    color = (0, 200, 0) if letra == correct else (0, 0, 255)
                else:
                    color = (0, 140, 255)
                cv2.circle(annotated, (cx, cy), radius_px + 4, color, 3)
            elif gabarito and letra == correct:
                cv2.circle(annotated, (cx, cy), radius_px + 4, (255, 165, 0), 2)

    return annotated


def answers_to_df(answers: dict, n_questions: int) -> pd.DataFrame:
    """Converte {q_num(int): letra|None} em DataFrame [Questão, Resposta] para exibir/editar."""
    rows = [{"Questão": q, "Resposta": answers.get(q) or ""} for q in range(1, n_questions + 1)]
    return pd.DataFrame(rows)


def df_to_answers(df: pd.DataFrame) -> dict:
    """Converte o DataFrame editado de volta em {q_num(int): letra|None}."""
    result = {}
    for _, row in df.iterrows():
        letra = str(row["Resposta"]).strip().upper()
        result[int(row["Questão"])] = letra if letra in ALTERNATIVES else None
    return result


def editable_answers_table(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Grade editável de questão/resposta (dropdown A-E), usada para revisar antes de salvar."""
    return st.data_editor(
        df,
        key=key,
        hide_index=True,
        width='stretch',
        num_rows="fixed",
        column_config={
            "Questão": st.column_config.NumberColumn(disabled=True),
            "Resposta": st.column_config.SelectboxColumn(options=["", *ALTERNATIVES]),
        },
    )



def seletor_ia_ui(cfg: dict, key_prefix: str, container=None) -> dict:
    """Escolha do provedor de IA (Gemini/Groq) e do modelo - SEM campo de chave.
    A chave vem de Configuracoes (ou de variavel de ambiente) e nunca e exibida.
    Retorna o dict `ia` para ai_grading ({"provedor","modelo","api_key"})."""
    from ai_grading import PROVEDORES, resolver_ia

    ct = container or st
    chaves = list(PROVEDORES)
    padrao = cfg.get("ia_provider", "gemini")
    col_p, col_m = ct.columns([1, 1])
    provedor = col_p.selectbox(
        "Provedor de IA", chaves, index=chaves.index(padrao) if padrao in chaves else 0,
        format_func=lambda k: PROVEDORES[k], key=f"{key_prefix}_ia_provedor",
    )
    modelo_cfg = cfg.get("groq_model") if provedor == "groq" else cfg.get("gemini_model")
    modelo = col_m.text_input(
        "Modelo", value=modelo_cfg or resolver_ia(cfg, provedor)["modelo"],
        key=f"{key_prefix}_ia_modelo_{provedor}",
    )
    ia = resolver_ia(cfg, provedor, modelo)
    if not ia["api_key"]:
        ct.warning(
            f"Nenhuma chave do {PROVEDORES[provedor]} cadastrada — cadastre na página **Configurações**."
        )
    return ia


def _sanear_pontos_sessao(key_prefix: str):
    """Corrige valores invalidos (ex.: dict) que ficaram no session_state das caixas de
    pontuacao por uma execucao anterior com erro - evita TypeError ao somar os itens."""
    for suf in ("pa", "pb", "pc", "pbonus"):
        k = f"{key_prefix}_{suf}"
        v = st.session_state.get(k)
        if isinstance(v, dict) or (k in st.session_state and not isinstance(v, (int, float))):
            novo = v.get("pontos", 0.0) if isinstance(v, dict) else 0.0
            try:
                st.session_state[k] = float(novo)
            except (TypeError, ValueError):
                st.session_state[k] = 0.0


def preseed_discursiva_session(key_prefix: str, avaliacao_existente: dict):
    """
    Pré-carrega o estado da sessão com uma avaliação da discursiva já salva
    (transcrição, pontos por item, justificativas da IA), para que apareça
    de cara na tela de recorreção — sem precisar clicar em "Avaliar com IA"
    de novo. Usado para dar feedback ao aluno com base no que a IA já
    escreveu antes. Só escreve se ainda não houver nada na sessão para essa
    chave (não sobrescreve edições em andamento).
    """
    _sanear_pontos_sessao(key_prefix)
    if not avaliacao_existente:
        return
    session_key = f"{key_prefix}_ia_result"
    if session_key in st.session_state:
        return

    sugestao = avaliacao_existente.get("sugestao_ia")
    if sugestao:
        st.session_state[session_key] = sugestao
        st.session_state[f"{key_prefix}_transcricao"] = avaliacao_existente.get(
            "transcricao_final", sugestao.get("transcricao", "")
        )

    def _pts(v):
        # aceita tanto o numero direto quanto {"pontos": x, "justificativa": ...}
        if isinstance(v, dict):
            v = v.get("pontos", 0.0)
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    if "item_a" in avaliacao_existente:
        if "sugestao_ia" not in avaliacao_existente and isinstance(avaliacao_existente["item_a"], dict):
            # registro salvo pela versao antiga da correcao em lote: o proprio dict e a sugestao
            st.session_state[session_key] = avaliacao_existente
            st.session_state[f"{key_prefix}_transcricao"] = avaliacao_existente.get("transcricao", "")
        st.session_state[f"{key_prefix}_pa"] = _pts(avaliacao_existente["item_a"])
        st.session_state[f"{key_prefix}_pb"] = _pts(avaliacao_existente["item_b"])
        st.session_state[f"{key_prefix}_pc"] = _pts(avaliacao_existente["item_c"])
        st.session_state[f"{key_prefix}_pbonus"] = _pts(avaliacao_existente["bonus_integracao"])
    elif "pontos_manuais" in avaliacao_existente:
        st.session_state[f"{key_prefix}_pontos_manual"] = avaliacao_existente["pontos_manuais"]


def discursiva_grading_ui(simulado: dict, key_prefix: str, cfg: dict, imagem_existente_path: str = None):
    """
    Bloco de interface completo para capturar e avaliar a questão discursiva
    (32) de UMA correção: foto, avaliação assistida por IA (Gemini) com
    transcrição editável quando o simulado tem rubrica, ou pontuação manual
    quando não tem. Usado tanto na correção individual/lote quanto na
    edição posterior de uma correção já salva (página Histórico).

    Se `imagem_existente_path` apontar para um arquivo já salvo (ex.: uma
    foto anexada durante uma correção em lote, ainda sem nota), essa foto é
    reaproveitada por padrão em vez de pedir um novo upload — com opção de
    trocar por uma foto nova.

    Retorna um dict:
        {"imagem_bytes": bytes|None,   # bytes de uma NOVA foto (None se reaproveitou a existente)
         "usa_imagem_existente": bool, # True = manter imagem_existente_path como está
         "pontos": float|None, "pontos_max": float|None, "avaliacao": dict|None}
    """
    import os

    from ai_grading import IAGradingError, grade_discursive, grade_discursive_from_text

    tem_rubrica = bool((simulado.get("rubrica_discursiva") or "").strip())
    resultado = {
        "imagem_bytes": None,
        "usa_imagem_existente": False,
        "pontos": None,
        "pontos_max": None,
        "avaliacao": None,
    }

    tem_foto_existente = bool(imagem_existente_path and os.path.exists(imagem_existente_path))

    def _obter_imagem():
        """Mostra a foto já anexada (com opção de trocar) ou pede uma nova. Retorna a imagem BGR ou None."""
        if tem_foto_existente:
            trocar = st.checkbox(
                "Substituir a foto já anexada por uma nova", key=f"{key_prefix}_trocar_foto"
            )
            if not trocar:
                pil_img = Image.open(imagem_existente_path).convert("RGB")
                bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                st.image(
                    cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
                    caption="Foto já anexada a esta correção",
                    width='stretch',
                )
                resultado["usa_imagem_existente"] = True
                return bgr
        return capture_image_ui(key_prefix=f"{key_prefix}_discursiva")

    if tem_rubrica:
        with st.expander("Ver rubrica desta questão"):
            st.markdown(simulado["rubrica_discursiva"])

        st.caption(
            "Você pode pedir uma avaliação sugerida por IA (Gemini ou Groq) com base "
            "na rubrica acima, ou avaliar manualmente. Em qualquer caso, a nota final é sempre "
            "definida por você."
        )

        ia = seletor_ia_ui(cfg, key_prefix)

        image_disc_bgr = _obter_imagem()

        session_key = f"{key_prefix}_ia_result"
        transcricao_key = f"{key_prefix}_transcricao"

        def _aplicar_sugestao(res):
            st.session_state[session_key] = res
            st.session_state[transcricao_key] = res.get("transcricao", "")
            st.session_state[f"{key_prefix}_pa"] = res["item_a"]["pontos"]
            st.session_state[f"{key_prefix}_pb"] = res["item_b"]["pontos"]
            st.session_state[f"{key_prefix}_pc"] = res["item_c"]["pontos"]
            st.session_state[f"{key_prefix}_pbonus"] = res["bonus_integracao"]["pontos"]

        # Resultado de uma avaliacao pedida no rerun anterior: aplicado ANTES de os widgets
        # (texto e pontos) serem criados, pois o Streamlit nao deixa alterar o valor de um
        # widget ja instanciado nesta execucao.
        _pendente = st.session_state.pop(f"{key_prefix}_pendente", None)
        if _pendente is not None:
            _aplicar_sugestao(_pendente["res"])
            st.success(_pendente["msg"])

        if image_disc_bgr is not None:
            if not resultado["usa_imagem_existente"]:
                st.image(
                    cv2.cvtColor(image_disc_bgr, cv2.COLOR_BGR2RGB),
                    caption="Resposta discursiva enviada",
                    width='stretch',
                )
            ok, buf = cv2.imencode(".jpg", image_disc_bgr)
            imagem_bytes_atual = buf.tobytes() if ok else None
            if not resultado["usa_imagem_existente"]:
                resultado["imagem_bytes"] = imagem_bytes_atual

            if st.button("Avaliar com IA", key=f"{key_prefix}_avaliar_ia"):
                if not ia["api_key"]:
                    st.error("Cadastre a chave de API na página Configurações para usar a avaliação por IA.")
                elif imagem_bytes_atual is None:
                    st.error("Não consegui ler a imagem.")
                else:
                    with st.spinner("Lendo a imagem e avaliando com a IA..."):
                        try:
                            res = grade_discursive(imagem_bytes_atual, simulado["rubrica_discursiva"], ia)
                            st.session_state[f"{key_prefix}_pendente"] = {
                                "res": res,
                                "msg": "Avaliação sugerida gerada — revise a transcrição e a pontuação abaixo.",
                            }
                            erro_ia = None
                        except IAGradingError as e:
                            erro_ia = e
                            st.error(f"Não foi possível obter a avaliação da IA: {e}")
                    if erro_ia is None:
                        st.rerun()

        sugestao = st.session_state.get(session_key)

        if sugestao is not None:
            st.markdown("**Transcrição da resposta (corrija o que a IA leu errado, se necessário):**")
            transcricao_editada = st.text_area(
                "Transcrição",
                value=st.session_state.get(transcricao_key, sugestao.get("transcricao", "")),
                height=150,
                key=transcricao_key,
                label_visibility="collapsed",
            )
            st.caption(
                "Se a transcrição acima estiver errada em algum ponto, corrija o texto e clique em "
                '"Reavaliar" para pedir uma nova sugestão de pontuação com base no texto corrigido '
                "(sem precisar reenviar a imagem)."
            )
            if st.button("Reavaliar com transcrição corrigida", key=f"{key_prefix}_reavaliar"):
                if not ia["api_key"]:
                    st.error("Cadastre a chave de API na página Configurações para reavaliar.")
                else:
                    with st.spinner("Reavaliando com o texto corrigido..."):
                        try:
                            res2 = grade_discursive_from_text(transcricao_editada, simulado["rubrica_discursiva"], ia)
                            st.session_state[f"{key_prefix}_pendente"] = {
                                "res": res2, "msg": "Pontuação atualizada com base no texto corrigido.",
                            }
                            erro_re = None
                        except IAGradingError as e:
                            erro_re = e
                            st.error(f"Não foi possível reavaliar: {e}")
                    if erro_re is None:
                        st.rerun()

            sugestao = st.session_state.get(session_key)
            if sugestao.get("resumo"):
                st.info(sugestao["resumo"])

        st.markdown("**Pontuação (revise/edite antes de salvar):**")
        _sanear_pontos_sessao(key_prefix)
        col1, col2, col3, col4 = st.columns(4)
        val_a = sugestao["item_a"]["pontos"] if sugestao else 0.0
        val_b = sugestao["item_b"]["pontos"] if sugestao else 0.0
        val_c = sugestao["item_c"]["pontos"] if sugestao else 0.0
        val_bonus = sugestao["bonus_integracao"]["pontos"] if sugestao else 0.0

        pontos_a = col1.number_input(
            "a) Funcional x não funcional", 0.0, 3.0, float(val_a), step=0.5, key=f"{key_prefix}_pa"
        )
        pontos_b = col2.number_input(
            "b) Estrutura de BD", 0.0, 3.0, float(val_b), step=0.5, key=f"{key_prefix}_pb"
        )
        pontos_c = col3.number_input(
            "c) Verificação e validação", 0.0, 3.0, float(val_c), step=0.5, key=f"{key_prefix}_pc"
        )
        pontos_bonus = col4.number_input(
            "Bônus integração", 0.0, 1.0, float(val_bonus), step=0.5, key=f"{key_prefix}_pbonus"
        )

        if sugestao:
            with st.expander("Justificativas sugeridas pela IA"):
                st.markdown(f"**a)** {sugestao['item_a']['justificativa']}")
                st.markdown(f"**b)** {sugestao['item_b']['justificativa']}")
                st.markdown(f"**c)** {sugestao['item_c']['justificativa']}")
                st.markdown(f"**Bônus:** {sugestao['bonus_integracao']['justificativa']}")

        resultado["pontos"] = pontos_a + pontos_b + pontos_c + pontos_bonus
        resultado["pontos_max"] = 10.0
        resultado["avaliacao"] = {
            "item_a": pontos_a,
            "item_b": pontos_b,
            "item_c": pontos_c,
            "bonus_integracao": pontos_bonus,
            "transcricao_final": st.session_state.get(transcricao_key, ""),
            "sugestao_ia": sugestao,
        }
        st.metric("Nota — questão discursiva (32)", f"{resultado['pontos']:.1f} / {resultado['pontos_max']:.0f}")

    else:
        st.caption(
            "Este simulado ainda não tem uma rubrica cadastrada para a questão 32 (defina uma em "
            "**Simulados e Gabaritos** para habilitar a avaliação assistida por IA). Por enquanto, "
            "fotografe a resposta e pontue manualmente."
        )

        image_disc_bgr = _obter_imagem()

        if image_disc_bgr is not None:
            if not resultado["usa_imagem_existente"]:
                st.image(
                    cv2.cvtColor(image_disc_bgr, cv2.COLOR_BGR2RGB),
                    caption="Resposta discursiva enviada",
                    width='stretch',
                )
                ok, buf = cv2.imencode(".jpg", image_disc_bgr)
                resultado["imagem_bytes"] = buf.tobytes() if ok else None

            resultado["pontos_max"] = st.number_input(
                "Nota máxima da questão discursiva",
                0.0,
                100.0,
                float(cfg["discursiva_nota_max_padrao"]),
                step=0.5,
                key=f"{key_prefix}_max_manual",
            )
            pontos_manuais = st.number_input(
                "Nota atribuída manualmente",
                0.0,
                100.0,
                0.0,
                step=0.5,
                key=f"{key_prefix}_pontos_manual",
            )
            resultado["pontos"] = min(pontos_manuais, resultado["pontos_max"])
            observacao_manual = st.text_area("Observações (opcional)", key=f"{key_prefix}_obs_manual", height=80)
            resultado["avaliacao"] = {"pontos_manuais": resultado["pontos"], "observacoes": observacao_manual}
            st.metric("Nota — questão discursiva (32)", f"{resultado['pontos']:.1f} / {resultado['pontos_max']:.0f}")

    return resultado


def corrigir_discursivas_em_lote_ui(df, key_prefix: str):
    """Configuracoes (chave, modelo) + botao que avalia com o Gemini, de uma vez,
    todas as correcoes de `df` (DataFrame de list_correcoes) que tem foto da
    discursiva anexada. Recalcula e salva a nota 0-1000 de cada uma."""
    import os
    from config import load_config
    from db import get_simulado, update_discursiva
    from scoring import calcular_nota_1000

    st.caption(
        "Avalia com a IA (Gemini ou Groq), de uma só vez, todas as correções que já têm foto da discursiva anexada. A nota 0-1000 de cada uma é recalculada "
        "automaticamente. Depois, revise individualmente no Histórico, se quiser ajustar."
    )

    cfg_lote = load_config()
    ia_lote = seletor_ia_ui(cfg_lote, f"lote_disc_{key_prefix}")
    reavaliar_ja_avaliadas = st.checkbox(
        "Incluir as já avaliadas (substitui a nota)", value=False, key=f"lote_disc_reavaliar_{key_prefix}"
    )

    _cache_simulados = {}


    def _rubrica_do_simulado(sim_id):
        if sim_id not in _cache_simulados:
            _cache_simulados[sim_id] = get_simulado(sim_id)
        return (_cache_simulados[sim_id].get("rubrica_discursiva") or "").strip()


    pendentes = []
    sem_rubrica = 0
    for row in df.itertuples():
        caminho = row.discursiva_imagem_path
        if not isinstance(caminho, str) or not caminho or not os.path.exists(caminho):
            continue
        ja_avaliada = pd.notna(row.discursiva_pontos)
        if ja_avaliada and not reavaliar_ja_avaliadas:
            continue
        if not _rubrica_do_simulado(row.simulado_id):
            sem_rubrica += 1
            continue
        pendentes.append(row)

    st.write(f"**{len(pendentes)}** correção(ões) com foto para avaliar nos filtros atuais.")
    if sem_rubrica:
        st.warning(
            f"{sem_rubrica} correção(ões) com foto foram ignoradas porque o simulado delas não tem "
            "rubrica da discursiva cadastrada."
        )

    if st.button(
        "Corrigir questões discursivas cadastradas",
        type="primary",
        disabled=not pendentes or not ia_lote["api_key"],
        key=f"btn_corrigir_discursivas_lote_{key_prefix}",
    ):
        from ai_grading import IAGradingError, grade_discursive

        barra = st.progress(0.0, text="Iniciando...")
        ok_lista, falhas = [], []
        for i, row in enumerate(pendentes):
            rotulo = f"#{row.id} {row.aluno}"
            barra.progress(i / len(pendentes), text=f"Avaliando {rotulo} ({i + 1}/{len(pendentes)})...")
            try:
                with open(row.discursiva_imagem_path, "rb") as f:
                    img_bytes = f.read()
                res = grade_discursive(img_bytes, _rubrica_do_simulado(row.simulado_id), ia_lote)
                nota = calcular_nota_1000(
                    int(row.acertos), int(row.n_questoes), res["total"], 10.0,
                    peso_discursiva_pontos=cfg_lote["peso_discursiva_pontos"],
                )
                update_discursiva(
                    row.id,
                    discursiva_pontos=res["total"],
                    discursiva_pontos_max=10.0,
                    discursiva_avaliacao={
                    "item_a": res["item_a"]["pontos"],
                    "item_b": res["item_b"]["pontos"],
                    "item_c": res["item_c"]["pontos"],
                    "bonus_integracao": res["bonus_integracao"]["pontos"],
                    "transcricao_final": res.get("transcricao", ""),
                    "sugestao_ia": res,
                },
                    discursiva_imagem_path=row.discursiva_imagem_path,
                    nota_1000=nota["nota_1000"],
                    discursiva_pontos_1000=nota["pontos_discursiva_1000"],
                )
                ok_lista.append((rotulo, res["total"], nota["nota_1000"]))
            except (IAGradingError, OSError) as e:
                falhas.append((rotulo, str(e)))
        barra.progress(1.0, text="Concluído.")
        st.session_state[f"lote_disc_resumo_{key_prefix}"] = {"ok": ok_lista, "falhas": falhas}
        st.rerun()

    resumo_lote = st.session_state.pop(f"lote_disc_resumo_{key_prefix}", None)
    if resumo_lote:
        if resumo_lote["ok"]:
            st.success(f"{len(resumo_lote['ok'])} discursiva(s) avaliada(s) e notas recalculadas.")
            st.dataframe(
                pd.DataFrame(resumo_lote["ok"], columns=["Correção", "Discursiva (0-10)", "Nota (0-1000)"]),
                width='stretch', hide_index=True,
            )
        if resumo_lote["falhas"]:
            st.error(
                f"{len(resumo_lote['falhas'])} falha(s). Rode o botão de novo para tentar apenas as "
                "que ficaram pendentes."
            )
            st.dataframe(pd.DataFrame(resumo_lote["falhas"], columns=["Correção", "Erro"]),
                         width='stretch', hide_index=True)



# ---------------------------------------------------------------------------
# Discursivas em lote a partir de um PDF unico (cada pagina = uma resposta)
# ---------------------------------------------------------------------------
def _avaliar_e_salvar_discursiva(correcao_id, caminho_imagem, rubrica, ia, cfg):
    """Avalia a imagem com a IA e grava pontos + nota 0-1000 da correcao. Devolve (total, nota)."""
    from ai_grading import grade_discursive
    from db import get_correcao, update_discursiva
    from scoring import calcular_nota_1000

    c = get_correcao(correcao_id)
    with open(caminho_imagem, "rb") as f:
        res = grade_discursive(f.read(), rubrica, ia)
    nota = calcular_nota_1000(
        int(c["acertos"]), int(c["n_questoes"]), res["total"], 10.0,
        peso_discursiva_pontos=cfg["peso_discursiva_pontos"],
    )
    update_discursiva(
        correcao_id,
        discursiva_pontos=res["total"],
        discursiva_pontos_max=10.0,
        discursiva_avaliacao={
            "item_a": res["item_a"]["pontos"], "item_b": res["item_b"]["pontos"],
            "item_c": res["item_c"]["pontos"], "bonus_integracao": res["bonus_integracao"]["pontos"],
            "transcricao_final": res.get("transcricao", ""), "sugestao_ia": res,
        },
        discursiva_imagem_path=caminho_imagem,
        nota_1000=nota["nota_1000"],
        discursiva_pontos_1000=nota["pontos_discursiva_1000"],
    )
    return res["total"], nota["nota_1000"]


def _salvar_so_imagem_discursiva(correcao_id, caminho_imagem):
    from db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE correcoes SET discursiva_imagem_path = ? WHERE id = ?", (caminho_imagem, correcao_id))


def discursivas_pdf_lote_ui(simulado_id: int, key_prefix: str = "pdfdisc"):
    """Um PDF/imagens com varias respostas discursivas (uma pagina por aluno): a IA le o nome
    em cada pagina, o usuario confere e o sistema anexa cada pagina a correcao do aluno
    (e, opcionalmente, ja avalia com a IA)."""
    import os
    import uuid

    from ai_grading import IAGradingError, identify_student
    from config import load_config
    from db import get_simulado, list_correcoes

    cfg = load_config()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    destino = os.path.join(base_dir, "data", "discursivas")
    kp = key_prefix

    st.caption(
        "Envie um único PDF em que **cada página é a resposta discursiva de um aluno**. A IA lê o nome escrito "
        "na página e associa à correção do aluno neste simulado. Você confere (vendo a página ao lado) e só então "
        "anexa. Só aparecem como opção os alunos que já têm correção (cartão) neste simulado."
    )
    arquivo = st.file_uploader("PDF (ou imagens) com as discursivas", type=["pdf", "jpg", "jpeg", "png"],
                               accept_multiple_files=True, key=f"{kp}_arquivo")
    if not arquivo:
        st.session_state.pop(f"{kp}_paginas", None)
        return

    assinatura = tuple((a.name, a.size) for a in arquivo)
    if st.session_state.get(f"{kp}_assin") != assinatura:
        paginas = []
        for a in arquivo:
            dados = a.getvalue()
            if a.name.lower().endswith(".pdf"):
                import fitz
                doc = fitz.open(stream=dados, filetype="pdf")
                for pn in range(len(doc)):
                    pix = doc[pn].get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    paginas.append((f"{a.name} · p.{pn + 1}", img))
            else:
                paginas.append((a.name, Image.open(io.BytesIO(dados)).convert("RGB")))

        def _jpg(img, larg=1600, topo=None):
            if topo:
                img = img.crop((0, 0, img.width, int(img.height * topo)))
            if img.width > larg:
                img = img.resize((larg, int(img.height * larg / img.width)))
            b = io.BytesIO()
            img.save(b, format="JPEG", quality=88)
            return b.getvalue()

        st.session_state[f"{kp}_paginas"] = [
            {"rotulo": r, "jpg": _jpg(im), "topo": _jpg(im, 1100, 0.45)} for r, im in paginas
        ]
        st.session_state[f"{kp}_assin"] = assinatura
        st.session_state[f"{kp}_ident"] = {}
        for k in [k for k in st.session_state if k.startswith(f"{kp}_sel_")]:
            del st.session_state[k]
    paginas = st.session_state[f"{kp}_paginas"]
    st.write(f"**{len(paginas)}** página(s) carregada(s).")

    corr_df = list_correcoes(simulado_id=simulado_id)
    if len(corr_df) == 0:
        st.warning("Este simulado ainda não tem correções. Corrija os cartões antes de anexar as discursivas.")
        return
    mapa = {}
    for r in corr_df.itertuples():
        mapa[f"{r.aluno} ({r.turma})"] = r.id
    rotulos = list(mapa.keys())
    SEL = "— selecionar —"

    ia = seletor_ia_ui(cfg, f"{kp}_ia")
    if st.button("Identificar os alunos pelas páginas", type="primary", disabled=not ia["api_key"], key=f"{kp}_btn_ident"):
        barra = st.progress(0.0, text="Identificando...")
        n_ok = n_sem = n_err = 0
        for i, pg in enumerate(paginas):
            barra.progress(i / len(paginas), text=f"Página {i + 1}/{len(paginas)}...")
            try:
                res = identify_student(pg["topo"], rotulos, ia, pagina_discursiva=True)
            except IAGradingError as e:
                st.session_state[f"{kp}_ident"][i] = {"erro": str(e)}
                n_err += 1
                continue
            st.session_state[f"{kp}_ident"][i] = res
            if res["aluno_sugerido"]:
                st.session_state[f"{kp}_sel_{i}"] = res["aluno_sugerido"]
                n_ok += 1
            else:
                n_sem += 1
        barra.progress(1.0, text="Concluído.")
        st.success(f"{n_ok} página(s) associada(s) · {n_sem} sem correspondência · {n_err} com erro de IA. Confira abaixo.")

    ident_all = st.session_state.get(f"{kp}_ident", {})
    if ident_all:
        linhas = []
        for i, r in sorted(ident_all.items()):
            if "erro" in r:
                linhas.append({"Página": i + 1, "Nome lido": "", "Sugerido": "", "Confiança": "", "Erro": r["erro"][:200]})
            else:
                linhas.append({"Página": i + 1, "Nome lido": r["nome_lido"], "Sugerido": r["aluno_sugerido"] or "(nenhum)",
                               "Confiança": r["confianca"], "Erro": ""})
        with st.expander("O que a IA leu em cada página"):
            st.dataframe(pd.DataFrame(linhas), width="stretch", hide_index=True)

    st.markdown("**Conferência** — a página à esquerda, o aluno à direita:")
    escolhas = {}
    for i, pg in enumerate(paginas):
        atual = st.session_state.get(f"{kp}_sel_{i}", SEL)
        with st.expander(f"{i + 1}. {pg['rotulo']} — {atual if atual != SEL else 'sem aluno'}"):
            c1, c2 = st.columns([2, 1])
            c1.image(pg["jpg"], width="stretch")
            escolhas[i] = c2.selectbox("Aluno / correção", [SEL] + rotulos, key=f"{kp}_sel_{i}")
            ident = ident_all.get(i)
            if ident and "erro" not in ident:
                c2.caption(f"IA leu: \"{ident['nome_lido'] or '—'}\" · confiança {ident['confianca']}")

    usados = [v for v in escolhas.values() if v != SEL]
    duplicados = {v for v in usados if usados.count(v) > 1}
    if duplicados:
        st.warning("Alunos escolhidos em mais de uma página: " + ", ".join(sorted(duplicados))
                   + ". Vale a última página da lista.")
    sem_aluno = sum(1 for v in escolhas.values() if v == SEL)
    if sem_aluno:
        st.info(f"{sem_aluno} página(s) sem aluno definido serão ignoradas.")

    sim = get_simulado(simulado_id)
    tem_rubrica = bool((sim.get("rubrica_discursiva") or "").strip())
    avaliar = st.checkbox(
        "Já avaliar com a IA depois de anexar" + ("" if tem_rubrica else " (o simulado não tem rubrica cadastrada)"),
        value=False, disabled=not (tem_rubrica and ia["api_key"]), key=f"{kp}_avaliar",
    )
    if st.button("Anexar as páginas às correções", type="primary", disabled=not usados, key=f"{kp}_btn_anexar"):
        os.makedirs(destino, exist_ok=True)
        por_corr = {mapa[v]: i for i, v in escolhas.items() if v != SEL}  # ultima pagina vence
        barra = st.progress(0.0, text="Anexando...")
        ok, falhas = [], []
        for n, (cid, i) in enumerate(por_corr.items()):
            barra.progress(n / len(por_corr), text=f"{n + 1}/{len(por_corr)}...")
            rotulo = escolhas[i]
            try:
                caminho = os.path.join(destino, f"{uuid.uuid4().hex}.jpg")
                with open(caminho, "wb") as f:
                    f.write(paginas[i]["jpg"])
                _salvar_so_imagem_discursiva(cid, caminho)
                if avaliar:
                    total, nota = _avaliar_e_salvar_discursiva(cid, caminho, sim["rubrica_discursiva"].strip(), ia, cfg)
                    ok.append((rotulo, i + 1, f"{total:.1f}", f"{nota:.0f}"))
                else:
                    ok.append((rotulo, i + 1, "—", "—"))
            except (IAGradingError, OSError) as e:
                falhas.append((rotulo, str(e)))
        barra.progress(1.0, text="Concluído.")
        st.session_state[f"{kp}_resumo"] = {"ok": ok, "falhas": falhas, "avaliou": avaliar}
        st.rerun()

    res = st.session_state.pop(f"{kp}_resumo", None)
    if res:
        if res["ok"]:
            st.success(f"{len(res['ok'])} discursiva(s) anexada(s)" + (" e avaliada(s)." if res["avaliou"] else
                       ". Use \"Correção em lote das discursivas já cadastradas\" para avaliar com a IA."))
            st.dataframe(pd.DataFrame(res["ok"], columns=["Aluno", "Página", "Discursiva (0-10)", "Nota (0-1000)"]),
                         width="stretch", hide_index=True)
        if res["falhas"]:
            st.error(f"{len(res['falhas'])} falha(s).")
            st.dataframe(pd.DataFrame(res["falhas"], columns=["Aluno", "Erro"]), width="stretch", hide_index=True)
