import json
import random
import sqlite3
from typing import Any, Optional
from .config import DB_PATH

def get_connection() -> sqlite3.Connection:
    """Retorna uma conexão SQLite configurada com WAL e timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn

def init_db() -> None:
    """Inicializa as tabelas do banco de dados relacional."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS apartamentos (
                numero TEXT PRIMARY KEY,
                morador TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS areas (
                id TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                taxa REAL NOT NULL
            );
        """)
        # Garantia 5: UNIQUE(area, data) garante que duas reservas ativas
        # para a mesma área na mesma data nunca coexistam no banco.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reservas (
                codigo TEXT PRIMARY KEY,
                apartamento TEXT NOT NULL,
                area TEXT NOT NULL,
                data TEXT NOT NULL,
                UNIQUE(area, data)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartamento TEXT NOT NULL,
                nome TEXT NOT NULL,
                data TEXT NOT NULL
            );
        """)
        # Histórico de todos os códigos de reservas gerados (inclusive canceladas)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historico_codigos (
                codigo TEXT PRIMARY KEY
            );
        """)
        # Controle transacional de confirmações pendentes
        conn.execute("""
            CREATE TABLE IF NOT EXISTS confirmacoes_pendentes (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                acao TEXT NOT NULL,
                detalhes TEXT NOT NULL,
                status TEXT NOT NULL,
                original_fc_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

def normalize_area_id(area_input: str) -> str:
    """Normaliza o identificador da área comum para o formato padrão do sistema."""
    if not area_input:
        return ""
    a = area_input.strip().lower()
    if "sal" in a or "fest" in a:
        return "salao-de-festas"
    if "churr" in a:
        return "churrasqueira"
    if "quadr" in a:
        return "quadra"
    return a

def get_taxa_area(area_id: str) -> float:
    """Retorna a taxa cadastrada para a área."""
    area_norm = normalize_area_id(area_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT taxa FROM areas WHERE id = ?", (area_norm,))
        row = cursor.fetchone()
        if row:
            return float(row["taxa"])
    return 0.0

def gerar_codigo_reserva_unico(conn: sqlite3.Connection) -> str:
    """Gera um código de reserva inédito no formato RSV-XXXX que nunca foi usado."""
    cursor = conn.cursor()
    while True:
        num = random.randint(1000, 9999)
        codigo = f"RSV-{num}"
        cursor.execute("SELECT 1 FROM historico_codigos WHERE codigo = ?", (codigo,))
        if not cursor.fetchone():
            return codigo

def inserir_reserva(apartamento: str, area: str, data: str) -> tuple[bool, str, str]:
    """
    Insere uma reserva de forma atômica no banco de dados.
    Garantia 5: A exclusividade é assegurada no instante da gravação através da
    restrição UNIQUE(area, data) e transação exclusiva no SQLite.
    """
    area_norm = normalize_area_id(area)
    with get_connection() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Verifica se já está ocupada
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM reservas WHERE area = ? AND data = ?", (area_norm, data))
            if cursor.fetchone():
                conn.rollback()
                return False, "", f"A área {area_norm} já está reservada para a data {data}."

            codigo = gerar_codigo_reserva_unico(conn)
            cursor.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data) VALUES (?, ?, ?, ?)",
                (codigo, apartamento, area_norm, data),
            )
            cursor.execute(
                "INSERT INTO historico_codigos (codigo) VALUES (?)",
                (codigo,),
            )
            conn.commit()
            return True, codigo, f"Reserva {codigo} confirmada com sucesso para a área {area_norm} na data {data}."
        except sqlite3.IntegrityError:
            conn.rollback()
            return False, "", f"A área {area_norm} já foi reservada por outro morador para a data {data}."
        except Exception as e:
            conn.rollback()
            return False, "", f"Erro ao processar reserva: {str(e)}"

def cancelar_reserva(apartamento: str, area: str, data: str) -> tuple[bool, str]:
    """
    Garantia 2: Cancela reservas pertencentes estritamente ao apartamento da sessão.
    Não altera reservas de outros apartamentos nem vaza seus códigos.
    """
    area_norm = normalize_area_id(area)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT codigo FROM reservas WHERE apartamento = ? AND area = ? AND data = ?",
            (apartamento, area_norm, data),
        )
        row = cursor.fetchone()
        if not row:
            return False, f"Nenhuma reserva encontrada para o seu apartamento ({apartamento}) na área {area_norm} no dia {data}."
        codigo = row["codigo"]
        cursor.execute("DELETE FROM reservas WHERE codigo = ?", (codigo,))
        conn.commit()
        return True, f"Reserva {codigo} da área {area_norm} no dia {data} cancelada com sucesso."

def inserir_visitante(apartamento: str, nome: str, data: str) -> tuple[bool, str]:
    """
    Registra autorização de entrada de visitante para o apartamento.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
            (apartamento, nome.strip(), data.strip()),
        )
        conn.commit()
        return True, f"Visitante {nome} autorizado(a) para o apartamento {apartamento} na data {data}."

def listar_reservas_apartamento(apartamento: str) -> list[dict[str, Any]]:
    """Lista as reservas de um apartamento para a rota de verificação."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT codigo, area, data FROM reservas WHERE apartamento = ? ORDER BY data ASC",
            (apartamento,),
        )
        return [{"codigo": row["codigo"], "area": row["area"], "data": row["data"]} for row in cursor.fetchall()]

def listar_visitantes_apartamento(apartamento: str) -> list[dict[str, Any]]:
    """Lista os visitantes autorizados de um apartamento para a rota de verificação."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento = ? ORDER BY data ASC",
            (apartamento,),
        )
        return [{"nome": row["nome"], "data": row["data"]} for row in cursor.fetchall()]

def verificar_disponibilidade(area: str, data: str) -> bool:
    """Verifica se uma área está livre em determinada data sem vazar dados de quem reservou."""
    area_norm = normalize_area_id(area)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM reservas WHERE area = ? AND data = ?", (area_norm, data))
        return cursor.fetchone() is None

def registrar_confirmacao_pendente(
    conf_id: str, session_id: str, acao: str, detalhes: dict[str, Any], original_fc_id: str = ""
) -> None:
    """Registra uma confirmação pendente no banco de dados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO confirmacoes_pendentes (id, session_id, acao, detalhes, status, original_fc_id)
            VALUES (?, ?, ?, ?, 'pendente', ?)
            """,
            (conf_id, session_id, acao, json.dumps(detalhes), original_fc_id),
        )
        conn.commit()

def listar_confirmacoes_pendentes(session_id: str) -> list[dict[str, Any]]:
    """Retorna todas as confirmações pendentes ativas de uma sessão."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, acao, detalhes FROM confirmacoes_pendentes WHERE session_id = ? AND status = 'pendente'",
            (session_id,),
        )
        result = []
        for row in cursor.fetchall():
            result.append({
                "id": row["id"],
                "acao": row["acao"],
                "detalhes": json.loads(row["detalhes"]),
            })
        return result

def validar_e_consumir_confirmacao(session_id: str, conf_id: str) -> bool:
    """
    Garantia 1: Valida se a confirmação pertence à sessão e está pendente.
    Se estiver, marca como 'respondida' atomicamente. Se já respondida ou inexistente, retorna False (resultando em 409).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM confirmacoes_pendentes WHERE session_id = ? AND id = ?",
            (session_id, conf_id),
        )
        row = cursor.fetchone()
        if not row:
            return False
        if row["status"] != "pendente":
            return False
        cursor.execute(
            "UPDATE confirmacoes_pendentes SET status = 'respondida' WHERE session_id = ? AND id = ?",
            (session_id, conf_id),
        )
        conn.commit()
        return True
