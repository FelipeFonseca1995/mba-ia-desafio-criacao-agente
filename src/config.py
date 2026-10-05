import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

# Configuração de chaves de API (Google AI Studio)
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
if API_KEY:
    os.environ["GOOGLE_API_KEY"] = API_KEY
    # Evita warning do client quando ambas estão setadas
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]

# Modelo padrão do Gemini para os agentes
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# Caminhos dos bancos de dados e arquivos de dados iniciais
BASE_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = BASE_DIR / "dados"
DB_PATH = str(BASE_DIR / "aurora.db")
SESSIONS_DB_PATH = str(BASE_DIR / "aurora_sessions.db")
APP_NAME = "residencial_aurora"
