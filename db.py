"""
db.py
Camada de persistencia (SQLite) para simulados, gabaritos, turmas, alunos e
correcoes.

O banco fica em data/gabarito_app.db, na mesma pasta do app. Isso funciona
bem para uso local (ou num servidor com disco persistente). Se o app for
publicado num servico com armazenamento efemero (ex.: alguns provedores de
deploy gratuito que reiniciam o container), o banco pode ser perdido a cada
reinicio - nesse caso e preciso apontar DB_PATH para um disco persistente
ou trocar por um banco externo.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "gabarito_app.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                data_criacao TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS simulados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                n_questoes INTEGER NOT NULL,
                gabarito TEXT,
                data_criacao TEXT NOT NULL,
                observacoes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turmas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                observacoes TEXT,
                data_criacao TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alunos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                turma_id INTEGER,
                observacoes TEXT,
                data_criacao TEXT NOT NULL,
                FOREIGN KEY (turma_id) REFERENCES turmas(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS correcoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulado_id INTEGER NOT NULL,
                aluno TEXT NOT NULL,
                turma TEXT,
                respostas TEXT NOT NULL,
                acertos INTEGER,
                n_questoes INTEGER,
                nota REAL,
                data TEXT NOT NULL,
                FOREIGN KEY (simulado_id) REFERENCES simulados(id) ON DELETE CASCADE
            )
            """
        )
    _migrate_schema()


def _migrate_schema():
    """Adiciona colunas novas em bancos criados por versoes anteriores do app."""
    novas_colunas = {
        "simulados": [
            ("rubrica_discursiva", "TEXT"),
            ("temas_questoes", "TEXT"),
        ],
        "correcoes": [
            ("discursiva_pontos", "REAL"),
            ("discursiva_pontos_max", "REAL"),
            ("discursiva_avaliacao", "TEXT"),
            ("discursiva_imagem_path", "TEXT"),
            ("aluno_id", "INTEGER"),
            ("turma_id", "INTEGER"),
            ("hora_inicio", "TEXT"),
            ("hora_fim", "TEXT"),
            ("tempo_prova_minutos", "REAL"),
            ("nota_1000", "REAL"),
            # Quanto a discursiva contribuiu para a nota_1000 (ja convertida
            # do valor bruto, ex. 7/10, para o peso configurado no momento
            # em que a correcao foi salva). Ver scoring.calcular_nota_1000.
            ("discursiva_pontos_1000", "REAL"),
        ],
        "alunos": [
            ("matricula", "TEXT"),
        ],
    }
    with get_conn() as conn:
        for tabela, colunas in novas_colunas.items():
            existentes = {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}
            for nome, tipo in colunas:
                if nome not in existentes:
                    conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")


# ---------------------------------------------------------------------------
# Simulados
# ---------------------------------------------------------------------------

def create_simulado(nome: str, n_questoes: int, observacoes: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO simulados (nome, n_questoes, gabarito, data_criacao, observacoes) "
            "VALUES (?, ?, NULL, ?, ?)",
            (nome, n_questoes, datetime.now().isoformat(timespec="seconds"), observacoes),
        )
        return cur.lastrowid


def list_simulados() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT id, nome, n_questoes, gabarito, rubrica_discursiva, data_criacao, observacoes "
            "FROM simulados ORDER BY id DESC",
            conn,
        )
    if len(df):
        df["tem_gabarito"] = df["gabarito"].notna()
        df["tem_rubrica"] = df["rubrica_discursiva"].notna() & (df["rubrica_discursiva"].str.strip() != "")
    else:
        df["tem_gabarito"] = pd.Series(dtype=bool)
        df["tem_rubrica"] = pd.Series(dtype=bool)
    return df


def get_simulado(simulado_id: int):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT id, nome, n_questoes, gabarito, rubrica_discursiva, temas_questoes, data_criacao, observacoes "
            "FROM simulados WHERE id = ?",
            (simulado_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    cols = ["id", "nome", "n_questoes", "gabarito", "rubrica_discursiva", "temas_questoes", "data_criacao", "observacoes"]
    d = dict(zip(cols, row))
    d["gabarito_dict"] = json.loads(d["gabarito"]) if d["gabarito"] else {}
    d["temas_questoes_dict"] = json.loads(d["temas_questoes"]) if d["temas_questoes"] else {}
    return d


def update_gabarito(simulado_id: int, gabarito: dict):
    with get_conn() as conn:
        conn.execute(
            "UPDATE simulados SET gabarito = ? WHERE id = ?",
            (json.dumps(gabarito, ensure_ascii=False), simulado_id),
        )


def update_rubrica_discursiva(simulado_id: int, rubrica: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE simulados SET rubrica_discursiva = ? WHERE id = ?",
            (rubrica, simulado_id),
        )


def update_temas_questoes(simulado_id: int, temas: dict):
    """Salva o tema/objeto de aprendizagem de cada questão objetiva (ex.: {'1': 'Banco de Dados', ...}).
    Usado para sugerir o que o aluno deveria revisar, com base nas questões que errou."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE simulados SET temas_questoes = ? WHERE id = ?",
            (json.dumps(temas, ensure_ascii=False), simulado_id),
        )


def delete_simulado(simulado_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM simulados WHERE id = ?", (simulado_id,))


# ---------------------------------------------------------------------------
# Turmas
# ---------------------------------------------------------------------------

def create_turma(nome: str, observacoes: str = "") -> int:
    nome = nome.strip()
    with get_conn() as conn:
        existe = conn.execute("SELECT id FROM turmas WHERE nome = ?", (nome,)).fetchone()
        if existe:
            raise ValueError(f'Já existe uma turma chamada "{nome}".')
        cur = conn.execute(
            "INSERT INTO turmas (nome, observacoes, data_criacao) VALUES (?, ?, ?)",
            (nome, observacoes, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def list_turmas() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT t.id, t.nome, t.observacoes, t.data_criacao,
                   COUNT(a.id) AS n_alunos
            FROM turmas t
            LEFT JOIN alunos a ON a.turma_id = t.id
            GROUP BY t.id
            ORDER BY t.nome
            """,
            conn,
        )
    return df


def get_turma(turma_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, nome, observacoes, data_criacao FROM turmas WHERE id = ?", (turma_id,)
        ).fetchone()
    if row is None:
        return None
    return dict(zip(["id", "nome", "observacoes", "data_criacao"], row))


def delete_turma(turma_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM turmas WHERE id = ?", (turma_id,))


# ---------------------------------------------------------------------------
# Alunos
# ---------------------------------------------------------------------------

def create_aluno(nome: str, turma_id: int = None, observacoes: str = "", matricula: str = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO alunos (nome, turma_id, observacoes, matricula, data_criacao) VALUES (?, ?, ?, ?, ?)",
            (nome.strip(), turma_id, observacoes, matricula, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def list_alunos(turma_id: int = None) -> pd.DataFrame:
    query = """
        SELECT a.id, a.nome, a.turma_id, t.nome AS turma, a.observacoes, a.matricula, a.data_criacao
        FROM alunos a
        LEFT JOIN turmas t ON t.id = a.turma_id
        WHERE 1=1
    """
    params = []
    if turma_id is not None:
        query += " AND a.turma_id = ?"
        params.append(turma_id)
    query += " ORDER BY a.nome"
    with get_conn() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


def get_aluno(aluno_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT a.id, a.nome, a.turma_id, t.nome AS turma, a.observacoes, a.matricula, a.data_criacao
            FROM alunos a LEFT JOIN turmas t ON t.id = a.turma_id
            WHERE a.id = ?
            """,
            (aluno_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(zip(["id", "nome", "turma_id", "turma", "observacoes", "matricula", "data_criacao"], row))


def update_aluno_turma(aluno_id: int, turma_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE alunos SET turma_id = ? WHERE id = ?", (turma_id, aluno_id))


def delete_aluno(aluno_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))


def import_alunos_bulk(alunos: list, turma_id: int) -> dict:
    """
    Importa varios alunos de uma vez (ex.: de uma planilha) para uma turma.
    `alunos`: lista de dicts {"nome": str, "matricula": str opcional}.

    Evita duplicar quem ja esta cadastrado:
    - se a matricula bater com um aluno ja existente (em qualquer turma),
      reaproveita esse cadastro e so atualiza a turma se for diferente;
    - senao, se o nome (sem diferenciar maiusculas) ja existir NESSA turma,
      considera que ja esta cadastrado.
    Caso contrario, cria um cadastro novo.

    Retorna {"criados": int, "ja_existiam": int, "turma_atualizada": int}.
    """
    criados = ja_existiam = turma_atualizada = 0
    agora = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        for item in alunos:
            nome = (item.get("nome") or "").strip()
            matricula = (item.get("matricula") or "").strip() or None
            if not nome:
                continue

            existente = None
            if matricula:
                existente = conn.execute(
                    "SELECT id, turma_id FROM alunos WHERE matricula = ?", (matricula,)
                ).fetchone()
            if existente is None:
                existente = conn.execute(
                    "SELECT id, turma_id FROM alunos WHERE lower(nome) = lower(?) AND turma_id = ?",
                    (nome, turma_id),
                ).fetchone()

            if existente:
                aluno_id, turma_atual = existente
                if turma_atual != turma_id:
                    conn.execute("UPDATE alunos SET turma_id = ? WHERE id = ?", (turma_id, aluno_id))
                    turma_atualizada += 1
                else:
                    ja_existiam += 1
                if matricula:
                    conn.execute(
                        "UPDATE alunos SET matricula = ? WHERE id = ? AND (matricula IS NULL OR matricula = '')",
                        (matricula, aluno_id),
                    )
            else:
                conn.execute(
                    "INSERT INTO alunos (nome, turma_id, observacoes, matricula, data_criacao) "
                    "VALUES (?, ?, '', ?, ?)",
                    (nome, turma_id, matricula, agora),
                )
                criados += 1

    return {"criados": criados, "ja_existiam": ja_existiam, "turma_atualizada": turma_atualizada}


# ---------------------------------------------------------------------------
# Correcoes
# ---------------------------------------------------------------------------

def create_correcao(simulado_id: int, aluno: str, turma: str, respostas: dict,
                     acertos: int, n_questoes: int, nota: float,
                     discursiva_pontos: float = None, discursiva_pontos_max: float = None,
                     discursiva_avaliacao: dict = None, discursiva_imagem_path: str = None,
                     aluno_id: int = None, turma_id: int = None,
                     hora_inicio: str = None, hora_fim: str = None,
                     tempo_prova_minutos: float = None, nota_1000: float = None,
                     discursiva_pontos_1000: float = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO correcoes "
            "(simulado_id, aluno, turma, respostas, acertos, n_questoes, nota, data, "
            "discursiva_pontos, discursiva_pontos_max, discursiva_avaliacao, discursiva_imagem_path, "
            "aluno_id, turma_id, hora_inicio, hora_fim, tempo_prova_minutos, nota_1000, "
            "discursiva_pontos_1000) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                simulado_id,
                aluno,
                turma,
                json.dumps(respostas, ensure_ascii=False),
                acertos,
                n_questoes,
                nota,
                datetime.now().isoformat(timespec="seconds"),
                discursiva_pontos,
                discursiva_pontos_max,
                json.dumps(discursiva_avaliacao, ensure_ascii=False) if discursiva_avaliacao else None,
                discursiva_imagem_path,
                aluno_id,
                turma_id,
                hora_inicio,
                hora_fim,
                tempo_prova_minutos,
                nota_1000,
                discursiva_pontos_1000,
            ),
        )
        return cur.lastrowid


def list_correcoes(simulado_id=None, turma=None, aluno=None, turma_id=None, aluno_id=None) -> pd.DataFrame:
    query = (
        "SELECT c.id, c.simulado_id, s.nome AS simulado, c.aluno, c.turma, c.aluno_id, c.turma_id, "
        "c.acertos, c.n_questoes, c.nota, c.nota_1000, c.hora_inicio, c.hora_fim, c.tempo_prova_minutos, "
        "c.data, c.respostas, "
        "c.discursiva_pontos, c.discursiva_pontos_max, c.discursiva_avaliacao, c.discursiva_imagem_path, "
        "c.discursiva_pontos_1000 "
        "FROM correcoes c JOIN simulados s ON s.id = c.simulado_id WHERE 1=1"
    )
    params = []
    if simulado_id:
        query += " AND c.simulado_id = ?"
        params.append(simulado_id)
    if turma_id:
        query += " AND c.turma_id = ?"
        params.append(turma_id)
    if aluno_id:
        query += " AND c.aluno_id = ?"
        params.append(aluno_id)
    if turma:
        query += " AND c.turma LIKE ?"
        params.append(f"%{turma}%")
    if aluno:
        query += " AND c.aluno LIKE ?"
        params.append(f"%{aluno}%")
    query += " ORDER BY c.id DESC"
    with get_conn() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


def delete_correcao(correcao_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM correcoes WHERE id = ?", (correcao_id,))


def get_correcao(correcao_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT c.id, c.simulado_id, c.aluno, c.turma, c.aluno_id, c.turma_id, c.respostas, "
            "c.acertos, c.n_questoes, c.nota, c.nota_1000, "
            "c.discursiva_pontos, c.discursiva_pontos_max, c.discursiva_avaliacao, c.discursiva_imagem_path, "
            "c.discursiva_pontos_1000, "
            "c.hora_inicio, c.hora_fim, c.tempo_prova_minutos, c.data "
            "FROM correcoes c WHERE c.id = ?",
            (correcao_id,),
        ).fetchone()
    if row is None:
        return None
    cols = [
        "id", "simulado_id", "aluno", "turma", "aluno_id", "turma_id", "respostas",
        "acertos", "n_questoes", "nota", "nota_1000",
        "discursiva_pontos", "discursiva_pontos_max", "discursiva_avaliacao", "discursiva_imagem_path",
        "discursiva_pontos_1000",
        "hora_inicio", "hora_fim", "tempo_prova_minutos", "data",
    ]
    d = dict(zip(cols, row))
    d["respostas_dict"] = json.loads(d["respostas"]) if d["respostas"] else {}
    d["discursiva_avaliacao_dict"] = json.loads(d["discursiva_avaliacao"]) if d["discursiva_avaliacao"] else None
    return d


def update_discursiva(correcao_id: int, discursiva_pontos: float, discursiva_pontos_max: float,
                       discursiva_avaliacao: dict, discursiva_imagem_path: str, nota_1000: float,
                       discursiva_pontos_1000: float = None):
    """Atualiza a avaliacao da questao discursiva de uma correcao ja salva (e a nota 0-1000
    recalculada com base nela), permitindo avaliar a discursiva depois de inserir a correcao."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE correcoes SET discursiva_pontos = ?, discursiva_pontos_max = ?, "
            "discursiva_avaliacao = ?, discursiva_imagem_path = ?, nota_1000 = ?, "
            "discursiva_pontos_1000 = ? WHERE id = ?",
            (
                discursiva_pontos,
                discursiva_pontos_max,
                json.dumps(discursiva_avaliacao, ensure_ascii=False) if discursiva_avaliacao else None,
                discursiva_imagem_path,
                nota_1000,
                discursiva_pontos_1000,
                correcao_id,
            ),
        )


_CAMPOS_CORRECAO_JSON = {"respostas", "discursiva_avaliacao"}
_CAMPOS_CORRECAO_VALIDOS = {
    "aluno", "turma", "aluno_id", "turma_id", "respostas", "acertos", "n_questoes", "nota",
    "discursiva_pontos", "discursiva_pontos_max", "discursiva_avaliacao", "discursiva_imagem_path",
    "hora_inicio", "hora_fim", "tempo_prova_minutos", "nota_1000", "discursiva_pontos_1000",
}


def update_correcao(correcao_id: int, **campos):
    """
    Atualiza qualquer subconjunto dos campos editaveis de uma correcao ja
    salva (usado na pagina de recorrecao). Aceita os mesmos nomes de campo
    de create_correcao; `respostas` e `discursiva_avaliacao` podem ser
    passados como dict (sao serializados para JSON automaticamente).
    Campos nao reconhecidos sao ignorados silenciosamente.
    """
    sets, valores = [], []
    for chave, valor in campos.items():
        if chave not in _CAMPOS_CORRECAO_VALIDOS:
            continue
        if chave in _CAMPOS_CORRECAO_JSON and valor is not None and not isinstance(valor, str):
            valor = json.dumps(valor, ensure_ascii=False)
        sets.append(f"{chave} = ?")
        valores.append(valor)
    if not sets:
        return
    valores.append(correcao_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE correcoes SET {', '.join(sets)} WHERE id = ?", valores)


# ---------------------------------------------------------------------------
# Usuarios (login)
# ---------------------------------------------------------------------------
# Senhas nunca sao guardadas em texto puro: usamos PBKDF2-HMAC-SHA256 (modulo
# hashlib, ja embutido no Python - sem dependencia externa) com um "salt"
# aleatorio por usuario, para dificultar ataques de forca bruta e de tabela
# arco-iris caso alguem tenha acesso direto ao arquivo do banco.

import hashlib
import secrets


def _hash_senha(senha: str, salt_hex: str = None) -> tuple:
    if salt_hex is None:
        salt_hex = secrets.token_hex(16)
    salt = bytes.fromhex(salt_hex)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, 200_000)
    return hash_bytes.hex(), salt_hex


def count_usuarios() -> int:
    with get_conn() as conn:
        (n,) = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()
    return n


def create_usuario(username: str, senha: str) -> int:
    username = username.strip()
    if not username or not senha:
        raise ValueError("Usuário e senha são obrigatórios.")
    with get_conn() as conn:
        existe = conn.execute("SELECT id FROM usuarios WHERE username = ?", (username,)).fetchone()
        if existe:
            raise ValueError(f'Já existe um usuário chamado "{username}".')
        senha_hash, salt_hex = _hash_senha(senha)
        cur = conn.execute(
            "INSERT INTO usuarios (username, password_hash, password_salt, data_criacao) VALUES (?, ?, ?, ?)",
            (username, senha_hash, salt_hex, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def verificar_login(username: str, senha: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash, password_salt FROM usuarios WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None:
        return False
    hash_salvo, salt_hex = row
    hash_calculado, _ = _hash_senha(senha, salt_hex)
    return secrets.compare_digest(hash_calculado, hash_salvo)


def list_usuarios() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT id, username, data_criacao FROM usuarios ORDER BY username", conn
        )
    return df


def alterar_senha(username: str, senha_atual: str, nova_senha: str) -> bool:
    """Retorna False se a senha atual informada estiver incorreta."""
    if not verificar_login(username, senha_atual):
        return False
    senha_hash, salt_hex = _hash_senha(nova_senha)
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios SET password_hash = ?, password_salt = ? WHERE username = ?",
            (senha_hash, salt_hex, username.strip()),
        )
    return True


def delete_usuario(usuario_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
