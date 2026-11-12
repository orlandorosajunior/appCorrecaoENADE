"""
sample_data.py
Dois utilitarios de manutencao dos dados do app:

- apagar_todos_os_dados(): apaga correcoes, alunos, turmas, simulados e as fotos
  das discursivas (e, opcionalmente, os usuarios).
- inserir_dataset_exemplo(): insere um conjunto SINTETICO (nomes e notas
  inventados, gerados com semente fixa) com 3 simulados, 2 turmas, 20 alunos e
  60 correcoes, para testar dashboards, relatorios e a evolucao por aluno.
  Tudo fica identificado com "EXEMPLO" no nome.
"""

import os
import random
from datetime import datetime, timedelta

from config import load_config
from db import (
    create_aluno, create_correcao, create_simulado, create_turma, get_conn,
    update_gabarito, update_rubrica_discursiva, update_temas_questoes,
)
from enade_referencia import OBJETOS_ADS_ESPECIFICO, OBJETOS_FORMACAO_GERAL
from scoring import calcular_nota_1000

DISCURSIVAS_DIR = os.path.join(os.path.dirname(__file__), "data", "discursivas")

RUBRICA_EXEMPLO = (
    "Padrão de resposta esperado:\n"
    "a) Diferenciar requisitos funcionais (o que o sistema faz) de não funcionais "
    "(qualidade, desempenho, segurança), com exemplos.\n"
    "b) Propor uma estrutura de banco de dados coerente (entidades, chaves e relacionamentos).\n"
    "c) Descrever verificação e validação (V&V): testes, revisões e critérios de aceite.\n"
    "Critérios: 0 a 3 pontos por item (a, b, c) + 1 ponto de bônus se integrar os três aspectos."
)

NOMES = [
    "Ana Beatriz Souza", "Bruno Henrique Lima", "Camila Ferreira", "Diego Martins", "Eduarda Alves",
    "Felipe Ribeiro", "Gabriela Rocha", "Heitor Nascimento", "Isabela Carvalho", "João Pedro Gomes",
    "Karina Mendes", "Lucas Teixeira", "Mariana Barbosa", "Nicolas Araújo", "Olívia Castro",
    "Paulo Vitor Dias", "Quézia Moreira", "Rafael Pinto", "Sofia Cardoso", "Thiago Monteiro",
]
TURMAS = ["EXEMPLO 4ADS-A", "EXEMPLO 4ADS-B"]
SIMULADOS = [("EXEMPLO Simulado 1", 0), ("EXEMPLO Simulado 2", 28), ("EXEMPLO Simulado 3", 56)]


def apagar_todos_os_dados(apagar_usuarios: bool = False) -> dict:
    """Apaga provas (correcoes), discursivas (fotos), alunos, turmas e simulados."""
    with get_conn() as conn:
        n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("correcoes", "alunos", "turmas", "simulados")}
        for t in ("correcoes", "alunos", "turmas", "simulados"):
            conn.execute(f"DELETE FROM {t}")
        try:
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('correcoes','alunos','turmas','simulados')")
        except Exception:
            pass
        if apagar_usuarios:
            n["usuarios"] = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
            conn.execute("DELETE FROM usuarios")
    # DELETE só marca as páginas como livres: o conteúdo antigo continua no
    # arquivo e pode ser recuperado. VACUUM reescreve o banco sem esses restos
    # (precisa rodar fora de transação, por isso numa conexão separada).
    with get_conn() as conn:
        conn.execute("VACUUM")
    fotos = 0
    if os.path.isdir(DISCURSIVAS_DIR):
        for nome in os.listdir(DISCURSIVAS_DIR):
            caminho = os.path.join(DISCURSIVAS_DIR, nome)
            if os.path.isfile(caminho):
                os.remove(caminho)
                fotos += 1
    n["fotos_discursivas"] = fotos
    return n


def _avaliacao_discursiva(rng, habilidade):
    def ponto(maximo):
        v = round(rng.gauss(habilidade * maximo, 0.6) * 2) / 2
        return float(min(maximo, max(0.0, v)))
    a, b, c = ponto(3), ponto(3), ponto(3)
    bonus = 1.0 if (a + b + c >= 7.5 and rng.random() < 0.7) else 0.0
    def item(p, txt):
        return {"pontos": p, "justificativa": txt}
    sug = {
        "transcricao": "Texto de exemplo (dado sintético) descrevendo requisitos, banco de dados e testes.",
        "item_a": item(a, "Distinção entre requisitos funcionais e não funcionais " + ("clara." if a >= 2 else "incompleta.")),
        "item_b": item(b, "Modelo de dados " + ("coerente, com chaves e relacionamentos." if b >= 2 else "pouco detalhado.")),
        "item_c": item(c, "V&V " + ("bem descrita (testes e critérios de aceite)." if c >= 2 else "citada de forma superficial.")),
        "bonus_integracao": item(bonus, "Integração dos três aspectos." if bonus else "Aspectos tratados isoladamente."),
        "resumo": "Avaliação sintética gerada para o dataset de exemplo.",
        "total": a + b + c + bonus,
        "modelo_usado": "exemplo",
    }
    return {
        "item_a": a, "item_b": b, "item_c": c, "bonus_integracao": bonus,
        "transcricao_final": sug["transcricao"], "sugestao_ia": sug,
    }, sug["total"]


def inserir_dataset_exemplo(seed: int = 2026) -> dict:
    """Insere o dataset sintetico. Retorna contagens. Seguro de rodar mais de uma vez
    (cria turmas/simulados com sufixo se os nomes ja existirem)."""
    rng = random.Random(seed)
    cfg = load_config()
    peso = cfg["peso_discursiva_pontos"]
    n_q = 31

    temas_pool = OBJETOS_ADS_ESPECIFICO + OBJETOS_FORMACAO_GERAL[:4]
    # temas fixos por questao (formacao geral nas 1-8, especifico nas demais)
    temas = {}
    for q in range(1, n_q + 1):
        base = OBJETOS_FORMACAO_GERAL if q <= 8 else OBJETOS_ADS_ESPECIFICO
        temas[str(q)] = base[(q * 7) % len(base)]
    dificuldade = {q: rng.uniform(0.35, 0.9) for q in range(1, n_q + 1)}  # prob. base de acerto

    # turmas e alunos
    with get_conn() as conn:
        existentes = {r[0] for r in conn.execute("SELECT nome FROM turmas")}
    turma_ids = {}
    for nome in TURMAS:
        n_final, k = nome, 2
        while n_final in existentes:
            n_final, k = f"{nome} ({k})", k + 1
        turma_ids[n_final] = create_turma(n_final, "Dados sintéticos de exemplo")
    alunos = []  # (id, nome, turma_id, turma_nome, habilidade)
    nomes_turma = list(turma_ids)
    for i, nome in enumerate(NOMES):
        t_nome = nomes_turma[i % 2]
        hab = min(0.95, max(0.25, rng.gauss(0.6, 0.16)))
        aid = create_aluno(nome, turma_ids[t_nome], "Exemplo sintético", matricula=f"EX{2026000 + i}")
        alunos.append((aid, nome, turma_ids[t_nome], t_nome, hab))

    base_data = datetime.now() - timedelta(days=90)
    n_corr = 0
    sim_ids = []
    for s_idx, (s_nome, offset) in enumerate(SIMULADOS):
        sid = create_simulado(s_nome, n_q, "Dataset sintético de exemplo")
        sim_ids.append(sid)
        gabarito = {str(q): rng.choice("ABCDE") for q in range(1, n_q + 1)}
        update_gabarito(sid, gabarito)
        update_rubrica_discursiva(sid, RUBRICA_EXEMPLO)
        update_temas_questoes(sid, temas)
        data_prova = base_data + timedelta(days=offset)

        for aid, nome, tid, t_nome, hab in alunos:
            hab_atual = min(0.97, hab + 0.05 * s_idx + rng.gauss(0, 0.03))  # evolucao ao longo dos simulados
            respostas, acertos = {}, 0
            for q in range(1, n_q + 1):
                p = min(0.97, max(0.1, dificuldade[q] * 0.5 + hab_atual * 0.55))
                r = rng.random()
                if r < p:
                    respostas[str(q)] = gabarito[str(q)]
                    acertos += 1
                elif r > 0.97:
                    respostas[str(q)] = None  # em branco
                else:
                    respostas[str(q)] = rng.choice([x for x in "ABCDE" if x != gabarito[str(q)]])
            avaliacao, pontos_disc = _avaliacao_discursiva(rng, hab_atual)
            nota = calcular_nota_1000(acertos, n_q, pontos_disc, 10.0, peso_discursiva_pontos=peso)
            inicio = datetime.combine(data_prova.date(), datetime.min.time()) + timedelta(
                hours=8, minutes=rng.choice([0, 0, 0, 5, 10, 15]))
            duracao = int(max(45, min(120, rng.gauss(100 - 15 * hab_atual, 10))))
            fim = inicio + timedelta(minutes=duracao)
            create_correcao(
                simulado_id=sid, aluno=nome, turma=t_nome, respostas=respostas,
                acertos=acertos, n_questoes=n_q, nota=round(100 * acertos / n_q, 1),
                discursiva_pontos=pontos_disc, discursiva_pontos_max=10.0,
                discursiva_avaliacao=avaliacao, discursiva_imagem_path=None,
                aluno_id=aid, turma_id=tid,
                hora_inicio=inicio.time().isoformat(), hora_fim=fim.time().isoformat(),
                tempo_prova_minutos=float(duracao),
                nota_1000=nota["nota_1000"], discursiva_pontos_1000=nota["pontos_discursiva_1000"],
            )
            n_corr += 1
    return {"simulados": len(SIMULADOS), "turmas": len(TURMAS), "alunos": len(alunos), "correcoes": n_corr}
