"""
groq_grading.py
Mesma funcionalidade de gemini_grading.py (transcrever/avaliar a discursiva e
identificar o aluno pelo cabecalho do cartao), mas usando a API da Groq
(compativel com a da OpenAI): https://api.groq.com/openai/v1/chat/completions

Usa apenas `requests` (ja instalado junto com o Streamlit). Imagens vao em
base64 (data URL) e a resposta e pedida em "JSON mode".

Os modelos com visao disponiveis na Groq mudam com o tempo: o padrao esta em
config.py (groq_model) e pode ser trocado na pagina Configuracoes.
"""

import base64
import json
import re
import time

import requests

from gemini_grading import (
    PROMPT_FROM_IMAGE, PROMPT_FROM_TEXT, PROMPT_IDENTIFICAR, PROMPT_IDENTIFICAR_DISCURSIVA, _normalize, normalizar_identificacao,
)

DEFAULT_MODEL = "qwen/qwen3.8-27b"
URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_TENTATIVAS = 3

FORMATO_AVALIACAO = """

Responda SOMENTE com um objeto JSON (sem texto fora dele, sem markdown) no formato:
{"transcricao": "...", "item_a": {"pontos": 0, "justificativa": "..."},
 "item_b": {"pontos": 0, "justificativa": "..."}, "item_c": {"pontos": 0, "justificativa": "..."},
 "bonus_integracao": {"pontos": 0, "justificativa": "..."}, "resumo": "..."}
"""

FORMATO_IDENTIFICACAO = """

Responda SOMENTE com um objeto JSON (sem texto fora dele) no formato:
{"nome_lido": "...", "cpf_lido": "...", "melhor_candidato": "...", "confianca": "alta|media|baixa"}
"""


class GroqGradingError(Exception):
    pass


def _extrair_json(texto: str) -> dict:
    texto = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini < 0 or fim <= ini:
        raise GroqGradingError("A resposta do modelo não continha um JSON.")
    try:
        return json.loads(texto[ini:fim + 1])
    except ValueError as exc:
        raise GroqGradingError(f"Resposta do modelo não veio em JSON válido: {exc}") from exc


def _chat(conteudo: list, api_key: str, model: str) -> dict:
    if not api_key:
        raise GroqGradingError("Nenhuma chave de API da Groq foi informada (cadastre em Configurações).")
    tem_imagem = any(parte.get("type") == "image_url" for parte in conteudo)
    # so texto: manda como string simples (aceito por TODOS os modelos); com imagem: lista de partes
    mensagem = conteudo[0]["text"] if not tem_imagem and len(conteudo) == 1 else conteudo
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": mensagem}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_completion_tokens": 3000,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = requests.post(URL, headers=headers, json=payload, timeout=120)
        except requests.RequestException as exc:
            raise GroqGradingError(f"Falha ao chamar a API da Groq: {exc}") from exc
        if resp.status_code in (429, 500, 502, 503, 504) and tentativa < MAX_TENTATIVAS:
            time.sleep(2 * tentativa)
            continue
        if resp.status_code == 400 and tem_imagem and "must be a string" in resp.text:
            raise GroqGradingError(
                f"O modelo \"{model}\" da Groq não aceita imagens (é um modelo só de texto). Em Configurações, "
                "troque o \"Modelo da Groq (com visão)\" por um modelo com visão — por exemplo "
                f"{DEFAULT_MODEL} (lista em console.groq.com/docs/vision) — e salve."
            )
        if resp.status_code != 200:
            raise GroqGradingError(f"Falha ao chamar a API da Groq: {resp.status_code} {resp.text[:300]}")
        try:
            texto = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise GroqGradingError(f"Resposta inesperada da Groq: {exc}") from exc
        return _extrair_json(texto)
    raise GroqGradingError("A Groq está indisponível no momento. Tente novamente em instantes.")


def _imagem(image_bytes: bytes, mime_type: str) -> dict:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}


def grade_discursive(image_bytes: bytes, rubrica: str, api_key: str, model: str = DEFAULT_MODEL,
                      mime_type: str = "image/jpeg") -> dict:
    parsed = _chat(
        [{"type": "text", "text": PROMPT_FROM_IMAGE.format(rubrica=rubrica) + FORMATO_AVALIACAO},
         _imagem(image_bytes, mime_type)],
        api_key, model,
    )
    return _normalize(parsed, model)


def grade_discursive_from_text(transcricao: str, rubrica: str, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    if not transcricao or not transcricao.strip():
        raise GroqGradingError("A transcrição está vazia — nada para reavaliar.")
    parsed = _chat(
        [{"type": "text", "text": PROMPT_FROM_TEXT.format(rubrica=rubrica, transcricao=transcricao) + FORMATO_AVALIACAO}],
        api_key, model,
    )
    return _normalize(parsed, model)


def identify_student(image_bytes: bytes, candidatos: list, api_key: str, model: str = DEFAULT_MODEL,
                      mime_type: str = "image/jpeg", pagina_discursiva: bool = False) -> dict:
    prompt = (PROMPT_IDENTIFICAR_DISCURSIVA if pagina_discursiva else PROMPT_IDENTIFICAR).format(candidatos="\n".join(f"- {c}" for c in candidatos) or "(lista vazia)")
    parsed = _chat([{"type": "text", "text": prompt + FORMATO_IDENTIFICACAO}, _imagem(image_bytes, mime_type)],
                   api_key, model)
    return normalizar_identificacao(parsed, candidatos)
