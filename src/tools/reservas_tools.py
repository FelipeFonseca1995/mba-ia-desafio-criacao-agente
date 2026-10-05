from typing import Any
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from ..database import (
    cancelar_reserva,
    get_taxa_area,
    inserir_reserva,
    listar_reservas_apartamento,
    normalize_area_id,
    verificar_disponibilidade,
)

def listar_areas_comuns() -> list[dict[str, Any]]:
    """
    Lista as áreas comuns disponíveis no Residencial Aurora e suas respectivas taxas de reserva.
    Taxa 0 significa área sem cobrança.
    """
    return [
        {"id": "salao-de-festas", "nome": "Salão de festas", "taxa": 150.0},
        {"id": "churrasqueira", "nome": "Churrasqueira", "taxa": 80.0},
        {"id": "quadra", "nome": "Quadra poliesportiva", "taxa": 0.0},
    ]

def consultar_disponibilidade(area: str, data: str) -> dict[str, Any]:
    """
    Consulta se uma determinada área comum está livre em uma data específica (AAAA-MM-DD).
    Garantia 2: Informa apenas se a data está livre ou ocupada, nunca de quem é a reserva nem o código.

    Args:
        area: Identificador da área ('salao-de-festas', 'churrasqueira', 'quadra').
        data: Data pretendida no formato AAAA-MM-DD.
    """
    area_norm = normalize_area_id(area)
    livre = verificar_disponibilidade(area_norm, data)
    return {
        "area": area_norm,
        "data": data,
        "disponivel": livre,
        "mensagem": "A área está disponível para esta data." if livre else "A área já se encontra reservada para esta data.",
    }

def listar_minhas_reservas(tool_context: ToolContext) -> list[dict[str, Any]]:
    """
    Lista todas as reservas ativas do apartamento autenticado nesta sessão.
    Garantia 2: O apartamento vem exclusivamente do estado da sessão, nunca de parâmetros do modelo.
    """
    apartamento = tool_context.state.get("apartamento", "")
    return listar_reservas_apartamento(apartamento)

def cancelar_minha_reserva(tool_context: ToolContext, area: str, data: str) -> dict[str, Any]:
    """
    Cancela uma reserva existente do próprio apartamento autenticado.
    Regra 4: O morador cancela reservas do próprio apartamento sem necessidade de confirmação.
    Garantia 2: Nunca altera reservas de outros apartamentos nem revela seus códigos.

    Args:
        area: Identificador da área ('salao-de-festas', 'churrasqueira', 'quadra').
        data: Data da reserva a ser cancelada (AAAA-MM-DD).
    """
    apartamento = tool_context.state.get("apartamento", "")
    area_norm = normalize_area_id(area)
    sucesso, msg = cancelar_reserva(apartamento, area_norm, data)
    return {"status": "sucesso" if sucesso else "erro", "mensagem": msg}

def _precisa_confirmacao_reserva(area: str, **kwargs) -> bool:
    """
    Garantia 1: Reservar uma área com taxa maior que zero gera cobrança e exige confirmação.
    Área com taxa zero (como a quadra) não gera cobrança e não pede confirmação.
    """
    area_norm = normalize_area_id(area)
    taxa = get_taxa_area(area_norm)
    return taxa > 0.0

def solicitar_reserva(tool_context: ToolContext, area: str, data: str) -> dict[str, Any]:
    """
    Efetua a reserva de uma área comum para o apartamento autenticado.
    Garantia 1: Se a área tiver taxa > 0, esta ferramenta requer confirmação prévia pelo sistema.
    Garantia 2: O apartamento é extraído do estado da sessão.
    Garantia 5: A exclusividade é validada atomicamente no banco no instante da gravação.

    Args:
        area: Identificador da área comum ('salao-de-festas', 'churrasqueira', 'quadra').
        data: Data desejada no formato AAAA-MM-DD.
    """
    apartamento = tool_context.state.get("apartamento", "")
    area_norm = normalize_area_id(area)

    sucesso, codigo, msg = inserir_reserva(apartamento, area_norm, data)
    if sucesso:
        return {
            "status": "sucesso",
            "codigo": codigo,
            "area": area_norm,
            "data": data,
            "mensagem": msg,
        }
    else:
        return {
            "status": "erro",
            "area": area_norm,
            "data": data,
            "mensagem": msg,
        }

# Ferramentas registradas no ADK
tool_listar_areas = FunctionTool(listar_areas_comuns)
tool_consultar_disponibilidade = FunctionTool(consultar_disponibilidade)
tool_listar_minhas_reservas = FunctionTool(listar_minhas_reservas)
tool_cancelar_minha_reserva = FunctionTool(cancelar_minha_reserva)
tool_solicitar_reserva = FunctionTool(
    solicitar_reserva,
    require_confirmation=_precisa_confirmacao_reserva,
)
