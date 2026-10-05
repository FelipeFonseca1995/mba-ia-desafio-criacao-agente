from typing import Any
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from ..database import inserir_visitante, listar_visitantes_apartamento

def listar_meus_visitantes(tool_context: ToolContext) -> list[dict[str, Any]]:
    """
    Lista todos os visitantes autorizados para o apartamento autenticado nesta sessão.
    Garantia 2: O apartamento vem exclusivamente do estado da sessão, nunca de parâmetros do modelo.
    """
    apartamento = tool_context.state.get("apartamento", "")
    return listar_visitantes_apartamento(apartamento)

def autorizar_visitante(tool_context: ToolContext, nome: str, data: str) -> dict[str, Any]:
    """
    Autoriza a entrada de um visitante no condomínio para uma data específica.
    Regra 3 / Garantia 1: Libera acesso ao prédio e SEMPRE requer confirmação prévia pelo sistema.
    Garantia 2: O apartamento vem exclusivamente do estado da sessão.

    Args:
        nome: Nome completo do visitante.
        data: Data da visita no formato AAAA-MM-DD.
    """
    apartamento = tool_context.state.get("apartamento", "")
    sucesso, msg = inserir_visitante(apartamento, nome, data)
    return {
        "status": "sucesso" if sucesso else "erro",
        "nome": nome.strip(),
        "data": data.strip(),
        "mensagem": msg,
    }

# Ferramentas registradas no ADK
tool_listar_meus_visitantes = FunctionTool(listar_meus_visitantes)
tool_autorizar_visitante = FunctionTool(
    autorizar_visitante,
    require_confirmation=True,  # Libera acesso: confirmação mandatória
)
