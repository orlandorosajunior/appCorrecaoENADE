"""
scoring.py
Calculo da nota na escala 0-1000 (estilo ENEM) e do tempo de prova.

ATENCAO - LEIA ANTES DE CONFIAR NESSE NUMERO:
A nota real do ENEM/ENADE usa TRI (Teoria de Resposta ao Item), um modelo
estatistico calibrado com a resposta de centenas de milhares de
participantes, que leva em conta a dificuldade e o poder de discriminacao
de cada item. NAO E uma simples "regra de tres" a partir do numero de
acertos - a mesma quantidade de acertos pode gerar notas TRI diferentes
dependendo de QUAIS questoes foram acertadas.

O que este modulo calcula e uma **conversao proporcional simples** (linear)
para a escala 0-1000, com peso configuravel para a questao discursiva:

- O professor define, em Configuracoes, quantos dos 1000 pontos totais a
  questao discursiva vale (`peso_discursiva_pontos`).
- Os pontos restantes (1000 - peso_discursiva_pontos) sao divididos
  igualmente entre as questoes objetivas.
- A nota final e a soma dos pontos ganhos nas objetivas com os pontos
  ganhos na discursiva (proporcional ao que ela vale), com maximo de 1000.

E util como referencia rapida no mesmo range de numeros que o ENEM usa,
mas NAO E o calculo oficial do INEP e nao deve ser apresentado aos alunos
como se fosse.
"""

from datetime import datetime, time

NOTA_MAXIMA = 1000.0


def calcular_nota_1000(acertos_objetivas: int, n_objetivas: int,
                        discursiva_pontos: float = None, discursiva_pontos_max: float = None,
                        peso_discursiva_pontos: float = 0.0) -> dict:
    """
    Calcula a nota (0-1000) combinando as questoes objetivas com a
    questao discursiva, usando um peso configuravel para a discursiva:

    - `peso_discursiva_pontos` e quantos dos 1000 pontos totais a questao
      discursiva vale (definido pelo professor em Configuracoes). Os
      (1000 - peso_discursiva_pontos) pontos restantes sao divididos
      igualmente entre as `n_objetivas` questoes objetivas.
    - `discursiva_pontos` / `discursiva_pontos_max` sao a nota bruta da
      discursiva na escala em que ela foi avaliada (ex.: 7.5 de 10, ou
      6 de 9 pela rubrica) - convertida em fracao e aplicada sobre
      `peso_discursiva_pontos`.
    - Se `peso_discursiva_pontos` for 0 (ou None), a discursiva nao entra
      na conta e os 1000 pontos ficam todos com as objetivas.

    Se a discursiva ainda nao foi avaliada (discursiva_pontos is None),
    ela conta como 0 pontos ganhos (mas o peso dela nas objetivas ja e
    descontado do total, entao a nota fica "provisoria" ate a discursiva
    ser avaliada) - o campo "discursiva_avaliada" do retorno sinaliza
    isso para a interface avisar o usuario.

    Quando o aluno acerta todas as objetivas E tira a nota máxima na
    discursiva, o resultado é exatamente 1000.

    Retorna: {
        "nota_1000": float,                 # nota final (objetivas + discursiva)
        "discursiva_avaliada": bool,
        "pontos_objetivas_1000": float,      # quanto as objetivas contribuiram, na escala 1000
        "pontos_discursiva_1000": float,     # quanto a discursiva contribuiu, na escala 1000
                                              # (a conversao dos pontos "brutos" dela — ex.: 7/10 —
                                              # para o peso configurado; 0.0 se ainda nao avaliada)
        "discursiva_percentual": float|None, # aproveitamento bruto da discursiva em % (0-100),
                                              # independente do peso configurado; None se nao avaliada
    }
    """
    peso_discursiva_pontos = max(0.0, min(NOTA_MAXIMA, peso_discursiva_pontos or 0.0))

    pontos_por_objetiva = (NOTA_MAXIMA - peso_discursiva_pontos) / n_objetivas if n_objetivas else 0.0
    pontos_objetivas_total = acertos_objetivas * pontos_por_objetiva

    discursiva_avaliada = discursiva_pontos is not None and discursiva_pontos_max not in (None, 0)
    if discursiva_avaliada:
        proporcao_discursiva = discursiva_pontos / discursiva_pontos_max
        pontos_discursiva_total = proporcao_discursiva * peso_discursiva_pontos
        discursiva_percentual = round(proporcao_discursiva * 100, 1)
    else:
        pontos_discursiva_total = 0.0
        discursiva_percentual = None

    nota_1000 = pontos_objetivas_total + pontos_discursiva_total
    return {
        "nota_1000": round(nota_1000, 1),
        "discursiva_avaliada": discursiva_avaliada,
        "pontos_objetivas_1000": round(pontos_objetivas_total, 1),
        "pontos_discursiva_1000": round(pontos_discursiva_total, 1),
        "discursiva_percentual": discursiva_percentual,
    }


def calcular_tempo_prova_minutos(hora_inicio: time, hora_fim: time) -> float:
    """
    Calcula a duracao da prova em minutos a partir de dois horarios (mesmo
    dia). Se hora_fim for menor que hora_inicio (ex.: prova atravessou a
    meia-noite), assume que passou para o dia seguinte.
    """
    hoje = datetime.today().date()
    dt_inicio = datetime.combine(hoje, hora_inicio)
    dt_fim = datetime.combine(hoje, hora_fim)
    if dt_fim < dt_inicio:
        from datetime import timedelta
        dt_fim += timedelta(days=1)
    return round((dt_fim - dt_inicio).total_seconds() / 60, 1)
