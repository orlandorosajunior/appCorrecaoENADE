"""
grok_grading.py
Integracao com a API da xAI (Grok) para sugerir uma avaliacao da questao
discursiva (32) com base numa rubrica definida pelo professor e numa foto
da resposta manuscrita do aluno.

Fluxo em duas etapas, pensado para lidar com erros de leitura da letra
manuscrita:

1. grade_discursive(imagem, rubrica) -> le a imagem, TRANSCREVE o texto
   manuscrito e ja sugere uma pontuacao com base nessa transcricao.
2. O professor revisa a transcricao (texto editavel) e corrige o que a IA
   leu errado.
3. grade_discursive_from_text(transcricao_corrigida, rubrica) -> reavalia
   a pontuacao com base SOMENTE no texto corrigido (sem imagem), evitando
   que um novo erro de leitura da imagem aconteca de novo.

IMPORTANTE: isto gera uma SUGESTAO de nota, transcricao e justificativa,
nao um resultado definitivo. O professor sempre revisa e confirma (ou
corrige) antes de salvar.

A API da xAI e compativel com o formato da OpenAI. Endpoint:
https://api.x.ai/v1 . Por padrao, a xAI guarda as requisicoes (incluindo
imagens enviadas) por ate 30 dias em seus servidores para fins de auditoria
- vale avisar os alunos/instituicao sobre isso se for usar em producao.
"""

import base64
import json
import re

from openai import OpenAI

XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-4.6"

RESPONSE_SCHEMA_TEXT = """\
{{
  "transcricao": "<transcrição fiel do texto manuscrito/digitado do aluno, preservando a estrutura em a) b) c) se houver>",
  "item_a": {{"pontos": <numero de 0 a 3>, "justificativa": "<1-2 frases citando o que o aluno escreveu>"}},
  "item_b": {{"pontos": <numero de 0 a 3>, "justificativa": "<1-2 frases>"}},
  "item_c": {{"pontos": <numero de 0 a 3>, "justificativa": "<1-2 frases>"}},
  "bonus_integracao": {{"pontos": <0 ou 1>, "justificativa": "<1 frase>"}},
  "resumo": "<2-3 frases resumindo o desempenho geral do aluno nesta questao>"
}}"""

PROMPT_FROM_IMAGE = """\
Você é um assistente que ajuda um professor a avaliar UMA resposta
dissertativa de aluno, a partir da rubrica abaixo. Você NÃO decide a nota
final - apenas transcreve o texto e sugere uma pontuação com justificativa
objetiva, que o professor vai revisar.

RUBRICA (definida pelo professor):
---
{rubrica}
---

Leia a imagem em anexo (foto da resposta manuscrita ou digitada do aluno).
Primeiro, transcreva o texto o mais fielmente possível — isso é importante
porque o professor vai conferir se você leu a letra corretamente antes de
confiar na nota. Depois, avalie estritamente conforme a rubrica.

Se a caligrafia estiver ambígua em algum trecho, transcreva sua melhor
interpretação mas mencione a incerteza na justificativa do item afetado.

Responda APENAS com um JSON no formato abaixo, sem nenhum texto antes ou
depois, sem markdown:

{schema}

Se a imagem estiver ilegível, em branco, ou não corresponder a uma
resposta para esta questão, deixe "transcricao" vazia, atribua 0 a todos
os itens e explique isso nas justificativas.
""".format(rubrica="{rubrica}", schema=RESPONSE_SCHEMA_TEXT)

PROMPT_FROM_TEXT = """\
Você é um assistente que ajuda um professor a avaliar UMA resposta
dissertativa de aluno, a partir da rubrica abaixo. Você NÃO decide a nota
final - apenas sugere uma pontuação com justificativa objetiva, que o
professor vai revisar.

RUBRICA (definida pelo professor):
---
{rubrica}
---

TEXTO DA RESPOSTA DO ALUNO (já revisado e corrigido pelo professor a
partir da transcrição original — trate como fiel ao que o aluno escreveu):
---
{transcricao}
---

Avalie estritamente conforme a rubrica. Responda APENAS com um JSON no
formato abaixo, sem nenhum texto antes ou depois, sem markdown. Repita o
texto recebido no campo "transcricao" sem alterá-lo:

{schema}
""".format(rubrica="{rubrica}", transcricao="{transcricao}", schema=RESPONSE_SCHEMA_TEXT)


class GrokGradingError(Exception):
    pass


def _extract_json(text: str) -> dict:
    """Extrai o primeiro objeto JSON valido de uma string (tolera texto extra ao redor)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise GrokGradingError("Não consegui interpretar a resposta do modelo como JSON.")


def _normalize(parsed: dict, model: str) -> dict:
    def _pontos(chave, maximo):
        try:
            valor = float(parsed.get(chave, {}).get("pontos", 0))
        except (TypeError, ValueError):
            valor = 0.0
        return max(0.0, min(maximo, valor))

    item_a = {"pontos": _pontos("item_a", 3), "justificativa": parsed.get("item_a", {}).get("justificativa", "")}
    item_b = {"pontos": _pontos("item_b", 3), "justificativa": parsed.get("item_b", {}).get("justificativa", "")}
    item_c = {"pontos": _pontos("item_c", 3), "justificativa": parsed.get("item_c", {}).get("justificativa", "")}
    bonus = {
        "pontos": _pontos("bonus_integracao", 1),
        "justificativa": parsed.get("bonus_integracao", {}).get("justificativa", ""),
    }
    total = item_a["pontos"] + item_b["pontos"] + item_c["pontos"] + bonus["pontos"]

    return {
        "transcricao": parsed.get("transcricao", ""),
        "item_a": item_a,
        "item_b": item_b,
        "item_c": item_c,
        "bonus_integracao": bonus,
        "resumo": parsed.get("resumo", ""),
        "total": total,
        "modelo_usado": model,
    }


def _call_grok(messages: list, api_key: str, model: str) -> dict:
    if not api_key:
        raise GrokGradingError("Nenhuma chave de API da xAI foi informada.")

    client = OpenAI(api_key=api_key, base_url=XAI_BASE_URL)

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except Exception as exc:  # erros de rede/autenticação/API da biblioteca openai
        raise GrokGradingError(f"Falha ao chamar a API da xAI: {exc}") from exc

    raw_text = completion.choices[0].message.content
    try:
        parsed = _extract_json(raw_text)
    except GrokGradingError:
        raise
    except Exception as exc:
        raise GrokGradingError(f"Resposta do modelo não veio em JSON válido: {exc}") from exc

    return _normalize(parsed, model)


def grade_discursive(image_bytes: bytes, rubrica: str, api_key: str,
                      model: str = DEFAULT_MODEL, mime_type: str = "image/jpeg") -> dict:
    """
    Envia a imagem da resposta + a rubrica para o Grok e retorna a avaliação
    sugerida já normalizada (inclui "transcricao" do que a IA leu na
    imagem, para o professor revisar/corrigir antes de reavaliar):

    {
        "transcricao": str,
        "item_a": {"pontos": float, "justificativa": str},
        "item_b": {"pontos": float, "justificativa": str},
        "item_c": {"pontos": float, "justificativa": str},
        "bonus_integracao": {"pontos": float, "justificativa": str},
        "resumo": str,
        "total": float,          # calculado localmente (soma dos itens)
        "modelo_usado": str,
    }

    Lança GrokGradingError em caso de falha de rede, autenticação ou parsing.
    """
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT_FROM_IMAGE.format(rubrica=rubrica)},
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
            ],
        }
    ]
    return _call_grok(messages, api_key, model)


def grade_discursive_from_text(transcricao: str, rubrica: str, api_key: str,
                                model: str = DEFAULT_MODEL) -> dict:
    """
    Reavalia a questão discursiva usando apenas o texto (já corrigido pelo
    professor) da transcrição, sem reenviar a imagem — evita repetir um
    erro de leitura da caligrafia. Mesmo formato de retorno de
    grade_discursive().
    """
    if not transcricao or not transcricao.strip():
        raise GrokGradingError("A transcrição está vazia — nada para reavaliar.")

    messages = [
        {
            "role": "user",
            "content": PROMPT_FROM_TEXT.format(rubrica=rubrica, transcricao=transcricao),
        }
    ]
    return _call_grok(messages, api_key, model)
