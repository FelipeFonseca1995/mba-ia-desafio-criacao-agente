import asyncio
import logging
import uuid
import aiosqlite
from typing import Any, Optional
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types
from google.genai.errors import APIError

from .config import APP_NAME, SESSIONS_DB_PATH
from .agents.agente_principal import agente_principal
from .database import (
    listar_confirmacoes_pendentes,
    normalize_area_id,
    registrar_confirmacao_pendente,
    validar_e_consumir_confirmacao,
)

logger = logging.getLogger(__name__)

# Configura o serviço de sessão persistida em SQLite e o App com suporte a retomada
session_service = SqliteSessionService(db_path=SESSIONS_DB_PATH)
app_adk = App(
    name=APP_NAME,
    root_agent=agente_principal,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
runner = Runner(app=app_adk, session_service=session_service)

async def obter_user_id_da_sessao(session_id: str) -> Optional[str]:
    """Busca o user_id (apartamento) diretamente no banco de sessões."""
    try:
        async with aiosqlite.connect(SESSIONS_DB_PATH) as db:
            async with db.execute(
                "SELECT user_id FROM sessions WHERE app_name = ? AND id = ?",
                (APP_NAME, session_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
    except Exception:
        pass
    return None

async def criar_nova_sessao(apartamento: str) -> str:
    """
    Garantia 2: Cria a sessão vinculando o apartamento único de forma imutável no estado.
    """
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=apartamento,
        state={"apartamento": apartamento},
        session_id=session_id,
    )
    return session_id

def _extrair_tempo_espera(msg: str, tentativa: int) -> float:
    """Extrai o tempo de espera informado pelo Google na mensagem de erro 429."""
    import re
    match = re.search(r"retry\s+(?:in|delay)?[^\d]*([0-9]+(?:\.[0-9]+)?)s", msg, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1)) + 1.5
        except ValueError:
            pass
    return tentativa * 5.0

async def _executar_com_retry(session_id: str, user_id: str, message: types.Content) -> list[Any]:
    """Executa o runner com retry inteligente respeitando a cota da API Gemini."""
    max_tentativas = 6
    for tentativa in range(1, max_tentativas + 1):
        try:
            eventos = []
            async for ev in runner.run_async(
                session_id=session_id,
                user_id=user_id,
                new_message=message,
            ):
                eventos.append(ev)
            return eventos
        except Exception as e:
            msg = str(e)
            if ("429" in msg or "503" in msg or "RESOURCE_EXHAUSTED" in msg or "UNAVAILABLE" in msg) and tentativa < max_tentativas:
                espera = _extrair_tempo_espera(msg, tentativa)
                logger.warning(f"Quota/disponibilidade temporária na API Gemini. Aguardando {espera:.1f}s para retentar...")
                await asyncio.sleep(espera)
                continue
            raise

def _processar_confirmacoes_de_eventos(session_id: str, eventos: list[Any]) -> None:
    """Varre eventos gerados e registra confirmações pendentes no banco de dados."""
    for ev in eventos:
        fcs = ev.get_function_calls()
        if not fcs:
            continue
        for fc in fcs:
            if fc.name == "adk_request_confirmation":
                conf_id = fc.id
                orig = fc.args.get("originalFunctionCall", {})
                acao = orig.get("name", "")
                args = orig.get("args", {})
                detalhes = {}
                if acao == "solicitar_reserva":
                    detalhes = {
                        "area": normalize_area_id(args.get("area", "")),
                        "data": str(args.get("data", "")),
                    }
                elif acao == "autorizar_visitante":
                    detalhes = {
                        "nome": str(args.get("nome", "")),
                        "data": str(args.get("data", "")),
                    }
                else:
                    detalhes = args

                registrar_confirmacao_pendente(
                    conf_id=conf_id,
                    session_id=session_id,
                    acao=acao,
                    detalhes=detalhes,
                    original_fc_id=orig.get("id", ""),
                )

def _extrair_resposta_de_eventos(eventos: list[Any]) -> str:
    """Extrai a resposta em texto gerada pelo modelo."""
    for ev in reversed(eventos):
        if ev.content and ev.content.role == "model" and ev.content.parts:
            for part in ev.content.parts:
                if part.text:
                    return part.text.strip()
    return ""

async def processar_mensagem_usuario(session_id: str, user_id: str, texto: str) -> dict[str, Any]:
    """Processa uma mensagem de texto do usuário na sessão."""
    msg = types.Content(role="user", parts=[types.Part(text=texto)])
    eventos = await _executar_com_retry(session_id, user_id, msg)
    _processar_confirmacoes_de_eventos(session_id, eventos)

    resposta = _extrair_resposta_de_eventos(eventos)
    confirmacoes = listar_confirmacoes_pendentes(session_id)
    return {
        "resposta": resposta,
        "confirmacoes_pendentes": confirmacoes,
    }

async def processar_resposta_confirmacao(
    session_id: str, user_id: str, conf_id: str, confirmado: bool
) -> Optional[dict[str, Any]]:
    """
    Garantia 1: Processa resposta formal de confirmação.
    Retorna None caso a confirmação não esteja pendente nesta sessão (409 Conflict).
    """
    valido = validar_e_consumir_confirmacao(session_id, conf_id)
    if not valido:
        return None

    conf_msg = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=conf_id,
                    name="adk_request_confirmation",
                    response={"confirmed": confirmado},
                )
            )
        ],
    )
    eventos = await _executar_com_retry(session_id, user_id, conf_msg)
    _processar_confirmacoes_de_eventos(session_id, eventos)

    resposta = _extrair_resposta_de_eventos(eventos)
    confirmacoes = listar_confirmacoes_pendentes(session_id)
    return {
        "resposta": resposta,
        "confirmacoes_pendentes": confirmacoes,
    }

async def obter_eventos_sessao(session_id: str, user_id: str) -> Optional[list[dict[str, Any]]]:
    """Retorna todos os eventos registrados para a sessão."""
    sess = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if not sess:
        return None
    return [ev.model_dump(mode="json") for ev in sess.events]
