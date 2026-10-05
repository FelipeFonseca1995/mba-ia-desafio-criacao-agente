import re
import unicodedata
from pathlib import Path
from google.adk.tools import FunctionTool
from ..config import DADOS_DIR

def _normalize_text(text: str) -> str:
    """Remove acentos e converte para minúsculas."""
    text = text.lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )

def _load_chapters() -> list[dict]:
    """Carrega e segmenta os capítulos de dados/regulamento.md."""
    reg_file = DADOS_DIR / "regulamento.md"
    with open(reg_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Divide por capítulos (## Capítulo ...)
    raw_parts = re.split(r"\n(?=## Capítulo )", content)
    chapters = []
    for part in raw_parts:
        part = part.strip()
        if not part.startswith("## Capítulo"):
            continue
        first_line = part.split("\n", 1)[0]
        # Ex: "## Capítulo IV: Piscina"
        title = first_line.replace("##", "").strip()
        chapters.append({
            "titulo": title,
            "texto": part,
            "tokens": set(_normalize_text(part).split())
        })
    return chapters

_CHAPTERS = _load_chapters()

# Mapeamento semântico direto de palavras-chave críticas para capítulos
_KEYWORD_MAP = {
    "piscina": "Capítulo IV: Piscina",
    "deck": "Capítulo IV: Piscina",
    "dermatologico": "Capítulo IV: Piscina",
    "traje": "Capítulo IV: Piscina",
    "boia": "Capítulo IV: Piscina",
    "silencio": "Capítulo III: Silêncio e boa convivência",
    "barulho": "Capítulo III: Silêncio e boa convivência",
    "ruido": "Capítulo III: Silêncio e boa convivência",
    "som": "Capítulo III: Silêncio e boa convivência",
    "salao": "Capítulo VI: Salão de festas, churrasqueira e quadra",
    "churrasqueira": "Capítulo VI: Salão de festas, churrasqueira e quadra",
    "quadra": "Capítulo VI: Salão de festas, churrasqueira e quadra",
    "festa": "Capítulo VI: Salão de festas, churrasqueira e quadra",
    "academia": "Capítulo V: Academia, brinquedoteca e playground",
    "brinquedoteca": "Capítulo V: Academia, brinquedoteca e playground",
    "playground": "Capítulo V: Academia, brinquedoteca e playground",
    "portaria": "Capítulo VII: Portaria e segurança",
    "seguranca": "Capítulo VII: Portaria e segurança",
    "encomenda": "Capítulo VII: Portaria e segurança",
    "animal": "Capítulo VIII: Animais de estimação",
    "animais": "Capítulo VIII: Animais de estimação",
    "pet": "Capítulo VIII: Animais de estimação",
    "cachorro": "Capítulo VIII: Animais de estimação",
    "gato": "Capítulo VIII: Animais de estimação",
    "mudanca": "Capítulo IX: Mudanças",
    "mudancas": "Capítulo IX: Mudanças",
    "obra": "Capítulo X: Obras e reformas",
    "obras": "Capítulo X: Obras e reformas",
    "reforma": "Capítulo X: Obras e reformas",
    "reformas": "Capítulo X: Obras e reformas",
    "garagem": "Capítulo XI: Garagem e veículos",
    "veiculo": "Capítulo XI: Garagem e veículos",
    "veiculos": "Capítulo XI: Garagem e veículos",
    "vaga": "Capítulo XI: Garagem e veículos",
    "lixo": "Capítulo XII: Coleta de lixo e reciclagem",
    "reciclagem": "Capítulo XII: Coleta de lixo e reciclagem",
    "multa": "Capítulo XIII: Infrações e penalidades",
    "infracao": "Capítulo XIII: Infrações e penalidades",
    "penalidade": "Capítulo XIII: Infrações e penalidades",
}

def consultar_regulamento(assunto: str) -> str:
    """
    Consulta o regulamento interno do condomínio sobre um assunto específico.
    Retorna estritamente o capítulo aplicável à dúvida, sem incluir capítulos sobre outros assuntos.

    Args:
        assunto: O assunto ou termo a pesquisar (ex: 'piscina', 'silencio', 'mudança', 'animais').
    """
    norm_assunto = _normalize_text(assunto)
    words = [w for w in re.findall(r"\w+", norm_assunto) if len(w) > 2]

    # 1. Verifica no mapa de palavras-chave prioritárias
    for word in words:
        if word in _KEYWORD_MAP:
            target_title = _KEYWORD_MAP[word]
            for chap in _CHAPTERS:
                if target_title.lower() in chap["titulo"].lower():
                    return chap["texto"]

    # 2. Busca por overlap de termos no título e conteúdo do capítulo
    best_chap = None
    best_score = -1
    for chap in _CHAPTERS:
        score = 0
        chap_title_norm = _normalize_text(chap["titulo"])
        for word in words:
            if word in chap_title_norm:
                score += 10
            elif word in chap["tokens"]:
                score += 1

        if score > best_score:
            best_score = score
            best_chap = chap

    if best_chap and best_score > 0:
        return best_chap["texto"]

    # Se não encontrar capítulo específico, lista os capítulos existentes para orientação
    titulos = [c["titulo"] for c in _CHAPTERS]
    return f"Não foi encontrado capítulo específico para '{assunto}'. Capítulos disponíveis: {', '.join(titulos)}."

# Tool registrada no ADK
tool_consultar_regulamento = FunctionTool(consultar_regulamento)
