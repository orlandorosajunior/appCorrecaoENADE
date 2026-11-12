"""
ai_grading.py
Camada unica de acesso a IA (Gemini ou Groq). As paginas do app chamam
SOMENTE as funcoes deste modulo, passando um dict `ia` obtido de
`resolver_ia(cfg, provedor, modelo)` - a chave de API vem sempre da pagina
Configuracoes (ou de variavel de ambiente) e nunca e digitada/exibida nas
paginas de correcao.
"""

import os

PROVEDORES = {"gemini": "Google Gemini", "groq": "Groq"}


class IAGradingError(Exception):
    """Erro de qualquer provedor (rede, chave, resposta invalida...)."""


def modelo_padrao(provedor: str) -> str:
    if provedor == "groq":
        from groq_grading import DEFAULT_MODEL
    else:
        from gemini_grading import DEFAULT_MODEL
    return DEFAULT_MODEL


def resolver_ia(cfg: dict, provedor: str = None, modelo: str = None) -> dict:
    """Monta {"provedor", "modelo", "api_key"} a partir das configuracoes salvas."""
    provedor = provedor if provedor in PROVEDORES else cfg.get("ia_provider", "gemini")
    if provedor not in PROVEDORES:
        provedor = "gemini"
    if provedor == "groq":
        chave = cfg.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
        padrao_modelo = cfg.get("groq_model") or modelo_padrao("groq")
    else:
        chave = cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
        padrao_modelo = cfg.get("gemini_model") or modelo_padrao("gemini")
    return {"provedor": provedor, "modelo": (modelo or "").strip() or padrao_modelo, "api_key": chave}


def _modulo(ia: dict):
    if ia["provedor"] == "groq":
        import groq_grading as m
        return m, m.GroqGradingError
    import gemini_grading as m
    return m, m.GeminiGradingError


def _executar(nome_funcao: str, ia: dict, *args, **extra):
    m, erro = _modulo(ia)
    if not ia.get("api_key"):
        raise IAGradingError(
            f"Nenhuma chave de API do {PROVEDORES[ia['provedor']]} cadastrada. "
            "Cadastre na página Configurações."
        )
    try:
        return getattr(m, nome_funcao)(*args, api_key=ia["api_key"], model=ia["modelo"], **extra)
    except erro as e:
        raise IAGradingError(str(e)) from e
    except ImportError as e:
        raise IAGradingError(f"Biblioteca ausente para o provedor {PROVEDORES[ia['provedor']]}: {e}") from e


def grade_discursive(image_bytes: bytes, rubrica: str, ia: dict) -> dict:
    return _executar("grade_discursive", ia, image_bytes, rubrica)


def grade_discursive_from_text(transcricao: str, rubrica: str, ia: dict) -> dict:
    return _executar("grade_discursive_from_text", ia, transcricao, rubrica)


def identify_student(image_bytes: bytes, candidatos: list, ia: dict, pagina_discursiva: bool = False) -> dict:
    return _executar("identify_student", ia, image_bytes, candidatos, pagina_discursiva=pagina_discursiva)


def testar_conexao(ia: dict) -> str:
    """Faz uma chamada minima; devolve o nome do modelo que respondeu."""
    res = grade_discursive_from_text(
        "Isto é apenas um texto de teste para validar a chave de API.",
        "Rubrica de teste: item_a vale de 0 a 3 pontos por qualquer conteúdo coerente.", ia,
    )
    return res.get("modelo_usado", ia["modelo"])
