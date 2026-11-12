"""
import_utils.py
Leitura de planilhas de turma para importar alunos em lote.

Sistemas academicos exportam listas de chamada em formatos bem variados:
.xlsx de verdade, .xls binario antigo, ou (bem comum) um HTML disfarcado de
.xls (o sistema so troca a extensao do arquivo, sem converter o conteudo).
carregar_planilha() tenta varias estrategias de leitura, na ordem, e
devolve a primeira que funcionar - sem exigir que o professor saiba qual
formato exato o sistema da escola gerou.
"""

import io

import pandas as pd

COLUNAS_NOME_PROVAVEIS = ["aluno", "nome", "estudante", "discente"]
COLUNAS_MATRICULA_PROVAVEIS = ["matricula", "matrícula", "ra", "registro", "prontuario", "prontuário"]


class PlanilhaError(Exception):
    pass


def _tem_caracteres_invalidos(df: pd.DataFrame) -> bool:
    """Detecta o caractere de substituição (�) que aparece quando o texto foi
    lido com um encoding errado (comum: tentar utf-8 num arquivo iso-8859-1)."""
    amostra = df.astype(str).apply(lambda col: col.str.contains("\ufffd", na=False)).any()
    return bool(amostra.any())


def carregar_planilha(arquivo_bytes: bytes) -> pd.DataFrame:
    """
    Tenta ler os bytes de um arquivo de planilha (.xlsx, .xls binario, .xls
    que na verdade e HTML, ou .csv) e retorna a MAIOR tabela encontrada,
    sem nenhum filtro de coluna ainda (isso fica a cargo da interface, que
    deixa o usuario escolher qual coluna e o nome e qual e a matricula).
    Lanca PlanilhaError se nenhuma estrategia funcionar.

    Varias tentativas podem "funcionar" sem lancar excecao mas ainda assim
    produzir texto corrompido (encoding errado troca acentos por "�") -
    por isso o resultado de cada tentativa e verificado antes de aceito;
    se todas as tentativas limpas falharem, usa a primeira que ao menos
    nao deu erro, mesmo que tenha caracteres estranhos.
    """
    erros = []
    melhor_com_problema = None

    # 1) HTML disfarçado de planilha (comum em sistemas academicos).
    # iso-8859-1/cp1252 primeiro: sao o padrao em sistemas legados PT-BR e,
    # ao contrario de utf-8, tendem a nao "mascarar" erro de encoding.
    for encoding in ("iso-8859-1", "cp1252", "utf-8"):
        try:
            tabelas = pd.read_html(io.BytesIO(arquivo_bytes), encoding=encoding)
            if tabelas:
                maior = max(tabelas, key=len)
                if len(maior) > 0 and maior.shape[1] > 1:
                    if not _tem_caracteres_invalidos(maior):
                        return maior
                    melhor_com_problema = melhor_com_problema or maior
        except Exception as e:
            erros.append(f"HTML ({encoding}): {e}")

    # 2) Excel de verdade (.xlsx via openpyxl, .xls antigo via xlrd)
    for engine in ("openpyxl", "xlrd"):
        try:
            df = pd.read_excel(io.BytesIO(arquivo_bytes), engine=engine)
            if df.shape[1] >= 1 and len(df) > 0:
                if not _tem_caracteres_invalidos(df):
                    return df
                melhor_com_problema = melhor_com_problema or df
        except Exception as e:
            erros.append(f"Excel ({engine}): {e}")

    # 3) CSV (varias combinacoes comuns de separador/encoding)
    for encoding in ("iso-8859-1", "cp1252", "utf-8"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(io.BytesIO(arquivo_bytes), sep=sep, encoding=encoding, engine="python")
                if df.shape[1] > 1 and len(df) > 0:
                    if not _tem_caracteres_invalidos(df):
                        return df
                    melhor_com_problema = melhor_com_problema or df
            except Exception as e:
                erros.append(f"CSV (sep={sep!r}, {encoding}): {e}")

    if melhor_com_problema is not None:
        return melhor_com_problema

    raise PlanilhaError(
        "Não consegui ler esse arquivo como planilha. Formatos aceitos: .xlsx, .xls "
        "(inclusive os exportados como HTML por sistemas acadêmicos) ou .csv. "
        "Se o problema persistir, tente abrir no Excel/Google Sheets e salvar novamente "
        "como .xlsx ou .csv.\nDetalhes técnicos: " + " | ".join(erros[-3:])
    )


def sugerir_coluna(colunas, candidatos: list) -> str:
    """Tenta achar, entre `colunas`, uma que combine com algum nome em `candidatos`
    (comparação sem acento/caixa). Retorna o nome da coluna ou None."""
    import unicodedata

    def _normaliza(s):
        s = str(s).lower().strip()
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

    candidatos_norm = [_normaliza(c) for c in candidatos]
    for col in colunas:
        col_norm = _normaliza(col)
        if any(cand in col_norm for cand in candidatos_norm):
            return col
    return None


def _limpa_matricula(valor) -> str:
    """Normaliza um valor de matrícula: remove o '.0' que aparece quando o Excel/pandas
    trata a coluna como número decimal, sem cortar zeros que fazem parte do número real."""
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def extrair_alunos(df: pd.DataFrame, coluna_nome: str, coluna_matricula: str = None) -> pd.DataFrame:
    """
    A partir da planilha bruta e das colunas escolhidas, monta um DataFrame
    limpo com ["Incluir", "Nome", "Matrícula"] — uma linha por aluno,
    descartando linhas sem nome e duplicatas exatas.
    """
    nomes = df[coluna_nome].astype(str).str.strip()
    if coluna_matricula and coluna_matricula in df.columns:
        matriculas = df[coluna_matricula].apply(_limpa_matricula)
    else:
        matriculas = pd.Series([""] * len(df))

    saida = pd.DataFrame({"Incluir": True, "Nome": nomes, "Matrícula": matriculas})
    saida = saida[saida["Nome"].str.len() > 0]
    saida = saida[~saida["Nome"].str.lower().isin(["nan", "none", "aluno", "nome"])]
    saida = saida.drop_duplicates(subset=["Nome", "Matrícula"]).reset_index(drop=True)
    return saida
