"""
omr_utils.py
Leitura optica de marcas (OMR) calibrada para o template fixo do
Cartao-Resposta do Simulado ENADE - ADS (31 questoes objetivas, 5
alternativas, em duas colunas: questoes 01-16 a esquerda e 17-31 a direita).

Como o layout e sempre o mesmo, em vez de "adivinhar" a grade de bolhas por
contornos genericos (fragil com cabecalho, tabela de exemplo, texto etc.),
usamos um TEMPLATE calibrado com a posicao exata de cada bolha, extraido
diretamente do PDF oficial (vetorial).

IMPORTANTE: as coordenadas do template sao fracoes (0-1) relativas ao
retangulo externo da propria tabela de questoes (o bloco que engloba as
duas colunas, 01-16 e 17-31) - NAO da pagina inteira. Isso e proposital:
em fotos reais, a folha inteira costuma ter baixo contraste com o fundo
(dificultando achar os 4 cantos da pagina), enquanto a borda preta da
tabela de questoes tem contraste forte e e detectada de forma muito mais
confiavel. O mesmo detector de contorno (find_document_contour) e usado
tanto na calibracao (a partir do PDF em branco) quanto em tempo de
execucao (na foto do usuario), entao o que importa e a consistencia entre
os dois, nao qual regiao exata foi encontrada.

Pipeline:

1. find_document_contour / warp_to_canvas -> localiza esse retangulo (a
   tabela de questoes) na foto/scan e corrige a perspectiva para um
   tamanho fixo, na mesma proporcao do retangulo de referencia calibrado.
2. read_answers_from_template -> para cada bolha do template, mede a
   proporcao de pixels escuros numa pequena janela ao redor da posicao
   calibrada e decide qual alternativa foi marcada.
"""

import json

import cv2
import numpy as np


# --------------------------------------------------------------------------
# Template
# --------------------------------------------------------------------------

def load_template(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Correcao de perspectiva
# --------------------------------------------------------------------------

def order_points(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 pontos como: topo-esquerda, topo-direita, baixo-direita, baixo-esquerda."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


# Cantos (x,y normalizados pela largura/altura da pagina A4) da tabela de questoes:
# topo-esq, topo-dir, baixo-dir, baixo-esq.
_QUADRO_TABELA_A4 = [0.089, 0.431, 0.923, 0.427, 0.924, 0.882, 0.091, 0.886]


def find_document_contour(image: np.ndarray):
    """Tenta localizar o contorno retangular da folha de respostas."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 50, 150)
    edged = cv2.dilate(edged, None, iterations=2)

    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            area = cv2.contourArea(approx)
            if area > 0.2 * image.shape[0] * image.shape[1]:
                return approx.reshape(4, 2)
    return None


def warp_to_canvas(image_bgr: np.ndarray, canvas_w: int, canvas_h: int):
    """
    Localiza a folha na imagem e corrige a perspectiva para um retangulo
    fixo (canvas_w x canvas_h), na mesma proporcao do template calibrado.
    Se nao conseguir achar os 4 cantos, apenas redimensiona a imagem
    inteira (assume que ja esta bem enquadrada/recortada).
    Retorna (imagem_corrigida, corners_encontrados: bool).
    """
    doc_contour = find_document_contour(image_bgr)
    if doc_contour is None:
        h, w = image_bgr.shape[:2]
        if 1.30 <= h / w <= 1.55:
            # Pagina A4 inteira (ex.: PDF escaneado) em que a borda da tabela nao foi
            # detectada (linhas apagadas/falhas no scan): recorta a regiao onde a tabela
            # fica nas folhas A4 deste cartao (media medida em 29 escaneamentos reais, variacao
            # de +-0,6%) - alinhar_ao_template() corrige o resto.
            rect = (np.array(_QUADRO_TABELA_A4, dtype="float32").reshape(4, 2) * np.array([w, h], dtype="float32"))
            dst = np.array([[0, 0], [canvas_w - 1, 0], [canvas_w - 1, canvas_h - 1], [0, canvas_h - 1]], dtype="float32")
            warped = cv2.warpPerspective(image_bgr, cv2.getPerspectiveTransform(rect, dst), (canvas_w, canvas_h))
            return warped, False
        resized = cv2.resize(image_bgr, (canvas_w, canvas_h))
        return resized, False

    rect = order_points(doc_contour.astype("float32"))
    dst = np.array(
        [[0, 0], [canvas_w - 1, 0], [canvas_w - 1, canvas_h - 1], [0, canvas_h - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image_bgr, matrix, (canvas_w, canvas_h))
    return warped, True


# --------------------------------------------------------------------------
# Leitura das marcacoes usando o template
# --------------------------------------------------------------------------
#
# Em escaneamentos e fotos reais o recorte da moldura raramente coincide ao
# pixel com o do PDF de referencia (a moldura detectada pode incluir a borda
# grossa, ter pequena inclinacao etc.), o que desloca TODAS as bolhas de 10-20
# px. Por isso a leitura e feita em dois passos:
#
# 1. alinhar_ao_template(): usa os circulos impressos (aneis vazios, presentes
#    em qualquer cartao) para estimar escala e deslocamento globais e corrige a
#    imagem, de modo que as bolhas caiam sobre as posicoes do template;
# 2. read_answers_from_template(): para cada bolha, refina localmente o centro
#    do anel e mede o quanto o INTERIOR do circulo esta preenchido (anel vazio
#    ~0, marcacao ~0.9-1.0), o que funciona com marcas pequenas, claras ou
#    irregulares.

_ANGULOS_ANEL = np.linspace(0, 2 * np.pi, 12, endpoint=False)
_RAIO_ANEL_PX = 4.6


def _binarizar(image_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]


def _centros_template(template_questions: dict, canvas_w: int, canvas_h: int):
    xs, ys = [], []
    for alts in template_questions.values():
        for xf, yf in alts.values():
            xs.append(xf * canvas_w)
            ys.append(yf * canvas_h)
    return np.array(xs), np.array(ys)


def estimar_inclinacao(thresh: np.ndarray, max_graus: float = 4.0) -> float:
    """Angulo (graus) que melhor endireita as linhas de texto/bolhas (perfil de projecao)."""
    pequena = cv2.resize(thresh, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    h, w = pequena.shape
    centro = (w / 2, h / 2)
    melhor, ang_melhor = -1.0, 0.0
    for ang in np.arange(-max_graus, max_graus + 0.01, 0.25):
        M = cv2.getRotationMatrix2D(centro, ang, 1.0)
        rot = cv2.warpAffine(pequena, M, (w, h), flags=cv2.INTER_NEAREST)
        v = float(np.var(rot.sum(axis=1).astype(np.float64)))
        if v > melhor:
            melhor, ang_melhor = v, float(ang)
    return ang_melhor


def estimar_alinhamento(thresh: np.ndarray, template_questions: dict, canvas_w: int, canvas_h: int,
                        faixa: int = 30, passo: int = 3):
    """Procura (sx, sy, dx, dy) que melhor leva as posicoes do template sobre os aneis
    impressos na imagem binarizada. Retorna (score, sx, sy, dx, dy); score = fracao
    media de pixels de tinta sobre os aneis (~0.45+ quando alinhado)."""
    ink = cv2.dilate(thresh, np.ones((2, 2), np.uint8)) / 255.0
    h, w = ink.shape
    bx, by = _centros_template(template_questions, canvas_w, canvas_h)
    cx0, cy0 = canvas_w / 2, canvas_h / 2
    cos_a, sin_a = np.cos(_ANGULOS_ANEL)[None, :], np.sin(_ANGULOS_ANEL)[None, :]

    def score(sx, sy, dx, dy):
        px = (bx - cx0) * sx + cx0 + dx
        py = (by - cy0) * sy + cy0 + dy
        X = (px[:, None] + _RAIO_ANEL_PX * cos_a).round().astype(int)
        Y = (py[:, None] + _RAIO_ANEL_PX * sin_a).round().astype(int)
        ok = (X >= 0) & (X < w) & (Y >= 0) & (Y < h)
        return float(np.where(ok, ink[np.clip(Y, 0, h - 1), np.clip(X, 0, w - 1)], 0).mean())

    melhor = (-1.0, 1.0, 1.0, 0, 0)
    for sx in (0.97, 1.0, 1.03):
        for sy in (0.97, 1.0, 1.03):
            for dx in range(-faixa, faixa + 1, passo):
                for dy in range(-faixa, faixa + 1, passo):
                    sc = score(sx, sy, dx, dy)
                    if sc > melhor[0]:
                        melhor = (sc, sx, sy, dx, dy)
    _, sx, sy, dx, dy = melhor
    for _ in range(2):  # refinamento fino (escala e deslocamento)
        for dsx in (-0.01, 0, 0.01):
            for dsy in (-0.01, 0, 0.01):
                for ddx in range(-passo, passo + 1):
                    for ddy in range(-passo, passo + 1):
                        sc = score(sx + dsx, sy + dsy, dx + ddx, dy + ddy)
                        if sc > melhor[0]:
                            melhor = (sc, sx + dsx, sy + dsy, dx + ddx, dy + ddy)
        _, sx, sy, dx, dy = melhor
    return melhor


def alinhar_ao_template(warped_bgr: np.ndarray, template_questions: dict, canvas_w: int, canvas_h: int):
    """Corrige escala/deslocamento residuais (e, se preciso, a inclinacao) para que as
    bolhas caiam nas posicoes do template. Retorna (imagem_alinhada, score). Se o
    alinhamento nao for convincente, devolve a melhor tentativa ou a imagem original."""
    img = warped_bgr
    sc, sx, sy, dx, dy = estimar_alinhamento(_binarizar(img), template_questions, canvas_w, canvas_h)
    if sc < 0.30:
        # alinhamento ruim: provavelmente pagina torta/deslocada. Endireita e procura numa faixa maior.
        ang = estimar_inclinacao(_binarizar(img))
        if abs(ang) >= 0.25:
            M = cv2.getRotationMatrix2D((canvas_w / 2, canvas_h / 2), ang, 1.0)
            img = cv2.warpAffine(img, M, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        sc2, sx2, sy2, dx2, dy2 = estimar_alinhamento(
            _binarizar(img), template_questions, canvas_w, canvas_h, faixa=100, passo=5)
        if sc2 > sc:
            sc, sx, sy, dx, dy = sc2, sx2, sy2, dx2, dy2
        else:
            img = warped_bgr
    if sc < 0.25:
        return warped_bgr, sc

    def _aplicar(imagem, sx_, sy_, dx_, dy_):
        cx0, cy0 = canvas_w / 2, canvas_h / 2
        M = np.array([[sx_, 0, cx0 * (1 - sx_) + dx_], [0, sy_, cy0 * (1 - sy_) + dy_]], dtype=np.float32)
        return cv2.warpAffine(
            imagem, M, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255),
        )

    alinhada = _aplicar(img, sx, sy, dx, dy)

    if sc < 0.30:
        # pagina muito deformada (escaneada torta): alinha cada coluna de questoes separadamente
        esq = {q: a for q, a in template_questions.items() if next(iter(a.values()))[0] < 0.5}
        dir_ = {q: a for q, a in template_questions.items() if q not in esq}
        if esq and dir_:
            bin_img = _binarizar(img)
            r_e = estimar_alinhamento(bin_img, esq, canvas_w, canvas_h, faixa=90, passo=5)
            r_d = estimar_alinhamento(bin_img, dir_, canvas_w, canvas_h, faixa=90, passo=5)
            if min(r_e[0], r_d[0]) > sc:
                img_e = _aplicar(img, *r_e[1:])
                img_d = _aplicar(img, *r_d[1:])
                meio = canvas_w // 2
                alinhada = img_d.copy()
                alinhada[:, :meio] = img_e[:, :meio]
                sc = min(r_e[0], r_d[0])
    return alinhada, sc


def read_answers_from_template(
    warped_bgr: np.ndarray,
    template_questions: dict,
    canvas_w: int,
    canvas_h: int,
    sample_radius_frac: float = 0.008,  # mantido por compatibilidade (nao usado)
    fill_threshold: float = 0.25,
    relative_margin: float = 1.15,
):
    """
    Mede o preenchimento do interior de cada bolha (0-1) e decide a alternativa.

    Regras: a mais preenchida so vale se (a) preenchimento >= max(fill_threshold, 0.5),
    (b) for pelo menos `relative_margin` vezes a segunda mais preenchida e (c) superar a
    segunda por >= 0.15 - isso descarta em branco e dupla marcacao (None).

    Retorna:
      answers: {numero_questao(int): letra ou None}
      fills:   {numero_questao(int): {letra: preenchimento}}  (para debug/ajuste fino)
    """
    thresh = _binarizar(warped_bgr)
    ink = cv2.dilate(thresh, np.ones((2, 2), np.uint8)) / 255.0
    h, w = thresh.shape
    yy, xx = np.mgrid[-8:9, -8:9]
    disco = (xx ** 2 + yy ** 2) <= 2.8 ** 2
    cos_a, sin_a = np.cos(np.linspace(0, 2 * np.pi, 20, endpoint=False)), np.sin(np.linspace(0, 2 * np.pi, 20, endpoint=False))
    min_fill = max(fill_threshold, 0.5)

    # centros esperados (vetorizado): busca local do melhor anel em +-6 px para cada bolha
    chaves = [(q_str, letra) for q_str, alts in template_questions.items() for letra in alts]
    cxs = np.array([template_questions[q][l][0] * canvas_w for q, l in chaves])
    cys = np.array([template_questions[q][l][1] * canvas_h for q, l in chaves])
    desl = np.arange(-6, 7)
    OY, OX = np.meshgrid(desl, desl, indexing="ij")
    OX, OY = OX.ravel(), OY.ravel()
    X = np.clip((cxs[:, None, None] + OX[None, :, None] + _RAIO_ANEL_PX * cos_a[None, None, :]).round().astype(int), 0, w - 1)
    Y = np.clip((cys[:, None, None] + OY[None, :, None] + _RAIO_ANEL_PX * sin_a[None, None, :]).round().astype(int), 0, h - 1)
    scores = ink[Y, X].mean(axis=2) - 0.01 * (np.abs(OX) + np.abs(OY))[None, :]
    melhor_idx = scores.argmax(axis=1)
    cent_x = np.round(cxs + OX[melhor_idx]).astype(int)
    cent_y = np.round(cys + OY[melhor_idx]).astype(int)
    fill_por_bolha = {}
    for k, key in enumerate(chaves):
        x0, y0 = cent_x[k] - 8, cent_y[k] - 8
        roi = thresh[max(y0, 0):y0 + 17, max(x0, 0):x0 + 17]
        fill_por_bolha[key] = float(roi[disco].mean() / 255) if roi.shape == (17, 17) else 0.0

    answers, fills_out = {}, {}
    for q_str, alts in template_questions.items():
        q_num = int(q_str)
        fills = {letra: fill_por_bolha[(q_str, letra)] for letra in alts}
        fills_out[q_num] = fills

        ordenadas = sorted(fills.items(), key=lambda kv: kv[1], reverse=True)
        (melhor_letra, melhor_val), (_, segundo) = ordenadas[0], ordenadas[1]
        if melhor_val < min_fill or melhor_val < segundo * relative_margin or melhor_val - segundo < 0.15:
            answers[q_num] = None
        else:
            answers[q_num] = melhor_letra

    return answers, fills_out
