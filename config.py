"""
config.py
Configuracoes locais do app: chave de API do Gemini, modelo padrao,
sensibilidade padrao de leitura do OMR, nota maxima padrao da discursiva
e o peso da discursiva na nota final (0-1000).

Fica salvo em data/config.json - um arquivo separado do banco de
simulados/correcoes (data/gabarito_app.db), pensado so para preferencias
de configuracao, nao para dados de alunos.

IMPORTANTE (seguranca): isto NAO e um cofre de segredos. E uma
conveniencia para uso local/pessoal - equivalente a guardar a chave numa
variavel de ambiente. Qualquer pessoa com acesso a esta pasta no disco
consegue ler a chave salva aqui. Se varias pessoas usam a mesma
instalacao do app, tenha isso em mente.
"""

import json
import os

BASE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(BASE_DIR, "data", "config.json")

DEFAULTS = {
    # Provedor de IA usado na leitura/avaliacao da discursiva e na identificacao
    # dos alunos: "gemini" ou "groq". As chaves ficam SO aqui (pagina
    # Configuracoes) - as paginas de correcao nao mostram nem pedem a chave.
    "ia_provider": "gemini",
    "gemini_api_key": "",
    "gemini_model": "gemini-3.7-flash",
    "groq_api_key": "",
    "groq_model": "qwen/qwen3.8-27b",
    "fill_threshold": 0.25,
    "relative_margin": 1.15,
    "discursiva_nota_max_padrao": 10.0,
    # Quantos dos 1000 pontos da nota final a questao discursiva vale. Os
    # pontos restantes (1000 - este valor) sao divididos igualmente entre
    # as 31 questoes objetivas. Ver scoring.calcular_nota_1000.
    "peso_discursiva_pontos": 100.0,
}


def load_config() -> dict:
    """Retorna as configurações salvas, preenchendo com os padrões qualquer
    chave ausente (inclusive se o arquivo ainda não existir ou estiver corrompido)."""
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                salvo = json.load(f)
            cfg.update({k: v for k, v in salvo.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(novos_valores: dict):
    """Atualiza e persiste as configurações (mescla com o que já existe)."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    atual = load_config()
    atual.update({k: v for k, v in novos_valores.items() if k in DEFAULTS})
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(atual, f, ensure_ascii=False, indent=2)
