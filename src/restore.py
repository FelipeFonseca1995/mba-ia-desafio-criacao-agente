import json
import os
from pathlib import Path
from .config import DADOS_DIR, DB_PATH, SESSIONS_DB_PATH
from .database import get_connection, init_db

def restaurar_dados() -> None:
    """Restaura o estado inicial do banco de dados relacional e limpa as sessões."""
    # Garante a estrutura das tabelas
    init_db()

    # Carrega os arquivos JSON originais de dados/
    with open(DADOS_DIR / "apartamentos.json", "r", encoding="utf-8") as f:
        apartamentos = json.load(f)

    with open(DADOS_DIR / "areas.json", "r", encoding="utf-8") as f:
        areas = json.load(f)

    with open(DADOS_DIR / "reservas.json", "r", encoding="utf-8") as f:
        reservas = json.load(f)

    with open(DADOS_DIR / "visitantes.json", "r", encoding="utf-8") as f:
        visitantes = json.load(f)

    with get_connection() as conn:
        conn.execute("DELETE FROM apartamentos")
        conn.execute("DELETE FROM areas")
        conn.execute("DELETE FROM reservas")
        conn.execute("DELETE FROM visitantes")
        conn.execute("DELETE FROM historico_codigos")
        conn.execute("DELETE FROM confirmacoes_pendentes")

        for ap in apartamentos:
            conn.execute(
                "INSERT INTO apartamentos (numero, morador) VALUES (?, ?)",
                (ap["numero"], ap["morador"]),
            )

        for ar in areas:
            conn.execute(
                "INSERT INTO areas (id, nome, taxa) VALUES (?, ?, ?)",
                (ar["id"], ar["nome"], float(ar["taxa"])),
            )

        for r in reservas:
            conn.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data) VALUES (?, ?, ?, ?)",
                (r["codigo"], r["apartamento"], r["area"], r["data"]),
            )
            conn.execute(
                "INSERT INTO historico_codigos (codigo) VALUES (?)",
                (r["codigo"],),
            )

        for v in visitantes:
            conn.execute(
                "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
                (v["apartamento"], v["nome"], v["data"]),
            )

        conn.commit()

    # Remove o banco de sessões do ADK para restaurar o estado limpo
    for ext in ["", "-journal", "-wal", "-shm"]:
        p = Path(f"{SESSIONS_DB_PATH}{ext}")
        if p.exists():
            try:
                os.remove(p)
            except OSError:
                pass

    print("Dados do Residencial Aurora restaurados com sucesso para o estado inicial!")

if __name__ == "__main__":
    restaurar_dados()
