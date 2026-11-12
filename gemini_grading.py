"""
gemini_grading.py
Integracao com a API do Google Gemini para sugerir uma avaliacao da questao
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

Usa o SDK oficial `google-genai` (pip install google-genai) e a saida
estruturada da API (response_schema) para receber um JSON no formato
esperado, com fallback tolerante a variacoes na resposta do modelo.
"""

import json
import time

from pydantic import BaseModel  # (google-genai e importado so quando o Gemini e realmente usado)

DEFAULT_MODEL = "gemini-3.7-flash"
MAX_TENTATIVAS_SOBRECARGA = 3
ESPERA_INICIAL_SEGUNDOS = 2


class _ItemAvaliado(BaseModel):
    pontos: float
    justificativa: str


class _AvaliacaoSchema(BaseModel):
    transcricao: str
    item_a: _ItemAvaliado
    item_b: _ItemAvaliado
    item_c: _ItemAvaliado
    bonus_integracao: _ItemAvaliado
    resumo: str


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

Cada item (item_a, item_b, item_c) vale de 0 a 3 pontos. O bônus de
integração vale 0 ou 1. Se a imagem estiver ilegível, em branco, ou não
corresponder a uma resposta para esta questão, deixe "transcricao" vazia,
atribua 0 a todos os itens e explique isso nas justificativas.
"""

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

Avalie estritamente conforme a rubrica. Cada item (item_a, item_b, item_c)
vale de 0 a 3 pontos. O bônus de integração vale 0 ou 1. Repita o texto
recebido no campo "transcricao" sem alterá-lo.
"""


class GeminiGradingError(Exception):
    pass


def _normalize(parsed: dict, model: str) -> dict:
    def _pontos(chave, maximo):
        try:
            valor = float(parsed.get(chave, {}).get("pontos", 0))
        except (TypeError, ValueError, AttributeError):
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


def _call_gemini(contents: list, api_key: str, model: str, schema=None, normalizar: bool = True) -> dict:
    from google import genai
    from google.genai import errors, types

    schema = schema or _AvaliacaoSchema
    if not api_key:
        raise GeminiGradingError("Nenhuma chave de API do Gemini foi informada.")

    client = genai.Client(api_key=api_key)
    config = {
        "response_mime_type": "application/json",
        "response_schema": schema,
        "temperature": 0.2,
        # Não usamos tools/function calling nesta integração — desabilita
        # explicitamente o recurso automático (AFC) da SDK para evitar o
        # aviso "Direct use of AFC in Models.generate_content is not
        # recommended" e qualquer log ruidoso associado a ele.
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }

    response = None
    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS_SOBRECARGA + 1):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            break
        except errors.ServerError as exc:
            # 5xx (ex.: 503 "modelo sobrecarregado") — condição transitória do
            # lado do Google, vale tentar de novo com espera crescente.
            ultimo_erro = exc
            if tentativa < MAX_TENTATIVAS_SOBRECARGA:
                time.sleep(ESPERA_INICIAL_SEGUNDOS * tentativa)
                continue
            raise GeminiGradingError(
                f"O Gemini está sobrecarregado no momento (tentei {MAX_TENTATIVAS_SOBRECARGA} vezes). "
                f"Tente novamente em alguns instantes. Detalhe: {exc}"
            ) from exc
        except errors.ClientError as exc:
            # 4xx (ex.: chave invalida, requisicao malformada) — nao adianta
            # tentar de novo, o erro nao vai mudar.
            raise GeminiGradingError(f"Falha ao chamar a API do Gemini: {exc}") from exc
        except Exception as exc:  # outros erros de rede/SDK
            raise GeminiGradingError(f"Falha ao chamar a API do Gemini: {exc}") from exc

    raw_text = response.text
    try:
        parsed = json.loads(raw_text)
    except Exception as exc:
        raise GeminiGradingError(f"Resposta do modelo não veio em JSON válido: {exc}") from exc

    return _normalize(parsed, model) if normalizar else parsed


def grade_discursive(image_bytes: bytes, rubrica: str, api_key: str,
                      model: str = DEFAULT_MODEL, mime_type: str = "image/jpeg") -> dict:
    """
    Envia a imagem da resposta + a rubrica para o Gemini e retorna a
    avaliação sugerida já normalizada (inclui "transcricao" do que a IA
    leu na imagem, para o professor revisar/corrigir antes de reavaliar):

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

    Lança GeminiGradingError em caso de falha de rede, autenticação ou parsing.
    """
    from google.genai import types

    contents = [
        PROMPT_FROM_IMAGE.format(rubrica=rubrica),
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
    ]
    return _call_gemini(contents, api_key, model)


def grade_discursive_from_text(transcricao: str, rubrica: str, api_key: str,
                                model: str = DEFAULT_MODEL) -> dict:
    """
    Reavalia a questão discursiva usando apenas o texto (já corrigido pelo
    professor) da transcrição, sem reenviar a imagem — evita repetir um
    erro de leitura da caligrafia. Mesmo formato de retorno de
    grade_discursive().
    """
    if not transcricao or not transcricao.strip():
        raise GeminiGradingError("A transcrição está vazia — nada para reavaliar.")

    contents = [PROMPT_FROM_TEXT.format(rubrica=rubrica, transcricao=transcricao)]
    return _call_gemini(contents, api_key, model)


# ---------------------------------------------------------------------------
# Identificacao do aluno pelo cabecalho do cartao-resposta
# ---------------------------------------------------------------------------

class _IdentificacaoSchema(BaseModel):
    nome_lido: str
    cpf_lido: str
    melhor_candidato: str
    confianca: str


PROMPT_IDENTIFICAR = """\
A imagem é o topo de um CARTÃO-RESPOSTA de simulado preenchido à mão. Leia o
campo "Nome completo" e o campo "CPF" (11 quadradinhos) escritos pelo aluno.

LISTA DE ALUNOS CANDIDATOS (copie EXATAMENTE um dos nomes abaixo, sem alterar):
{candidatos}

Responda em JSON com:
- "nome_lido": o nome como você leu na imagem (vazio se ilegível/em branco);
- "cpf_lido": somente os dígitos do CPF que conseguiu ler (vazio se não leu);
- "melhor_candidato": o nome da lista que mais provavelmente corresponde ao
  nome escrito (copiado literalmente da lista), ou "" se nenhum combinar de
  forma razoável. Tolere erros de caligrafia, acentos e abreviações, mas NÃO
  chute: se estiver em dúvida entre dois nomes, devolva "";
- "confianca": "alta", "media" ou "baixa".
"""


PROMPT_IDENTIFICAR_DISCURSIVA = """\
A imagem é uma página de RESPOSTA DISCURSIVA manuscrita de um simulado. O aluno
pode ter escrito o nome (e/ou CPF) no topo, no cabeçalho ou no início do texto.
Procure o nome do aluno nessa página; ignore o enunciado e o texto da resposta.

LISTA DE ALUNOS CANDIDATOS (copie EXATAMENTE um dos nomes abaixo, sem alterar):
{candidatos}

Responda em JSON com:
- "nome_lido": o nome como você leu na imagem (vazio se não houver nome legível);
- "cpf_lido": somente os dígitos do CPF que conseguiu ler (vazio se não houver);
- "melhor_candidato": o nome da lista que mais provavelmente corresponde ao
  nome escrito (copiado literalmente da lista), ou "" se nenhum combinar de
  forma razoável. NÃO chute: se estiver em dúvida entre dois nomes, devolva "";
- "confianca": "alta", "media" ou "baixa".
"""


def _sem_acento(txt: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", txt.casefold()) if unicodedata.category(c) != "Mn")


def _melhor_por_similaridade(nome_lido: str, candidatos: list, corte: float = 0.72, folga: float = 0.06) -> str:
    """Plano B quando a IA leu o nome mas nao devolveu um candidato exato: compara o nome lido com a
    lista (sem acentos/maiusculas, tolerando erros de letra) e so aceita se houver um vencedor claro."""
    from difflib import SequenceMatcher

    alvo = _sem_acento(nome_lido)
    tokens_alvo = set(alvo.split())
    pontos = []
    for c in candidatos:
        cn = _sem_acento(c.split(" (")[0])
        r = SequenceMatcher(None, alvo, cn).ratio()
        toks = set(cn.split())
        comuns = len(tokens_alvo & toks) / max(len(tokens_alvo), 1)
        pontos.append((max(r, 0.5 * r + 0.5 * comuns), c))
    pontos.sort(reverse=True)
    if not pontos or pontos[0][0] < corte:
        return ""
    if len(pontos) > 1 and pontos[0][0] - pontos[1][0] < folga:
        return ""
    return pontos[0][1]


def normalizar_identificacao(parsed: dict, candidatos: list) -> dict:
    """Garante que `melhor_candidato` seja um nome da lista (ou None)."""
    melhor = (parsed.get("melhor_candidato") or "").strip()
    if melhor not in candidatos:
        baixo = {c.casefold(): c for c in candidatos}
        melhor = baixo.get(melhor.casefold(), "")
    nome_lido = (parsed.get("nome_lido") or "").strip()
    if not melhor and nome_lido:
        melhor = _melhor_por_similaridade(nome_lido, candidatos)
    conf = (parsed.get("confianca") or "baixa").strip().lower()
    return {
        "nome_lido": (parsed.get("nome_lido") or "").strip(),
        "cpf_lido": "".join(ch for ch in (parsed.get("cpf_lido") or "") if ch.isdigit()),
        "aluno_sugerido": melhor or None,
        "confianca": conf if conf in ("alta", "media", "baixa") else "baixa",
    }


def identify_student(image_bytes: bytes, candidatos: list, api_key: str,
                      model: str = DEFAULT_MODEL, mime_type: str = "image/jpeg",
                      pagina_discursiva: bool = False) -> dict:
    """Le o nome/CPF no cabecalho do cartao e sugere qual dos `candidatos` e o aluno."""
    from google.genai import types

    contents = [
        (PROMPT_IDENTIFICAR_DISCURSIVA if pagina_discursiva else PROMPT_IDENTIFICAR).format(
            candidatos="\n".join(f"- {c}" for c in candidatos) or "(lista vazia)"),
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
    ]
    parsed = _call_gemini(contents, api_key, model, schema=_IdentificacaoSchema, normalizar=False)
    return normalizar_identificacao(parsed, candidatos)
