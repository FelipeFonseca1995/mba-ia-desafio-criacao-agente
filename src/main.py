from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from .database import (
    init_db,
    listar_reservas_apartamento,
    listar_visitantes_apartamento,
)
from .runner_manager import (
    criar_nova_sessao,
    obter_eventos_sessao,
    obter_user_id_da_sessao,
    processar_mensagem_usuario,
    processar_resposta_confirmacao,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa o esquema de tabelas do banco relacional na inicialização
    init_db()
    yield

app = FastAPI(
    title="Assistente Virtual do Residencial Aurora",
    description="API com Google ADK para atendimento dos moradores do Residencial Aurora",
    lifespan=lifespan,
)

# Modelos Pydantic para requisições e respostas

class CriarSessaoRequest(BaseModel):
    apartamento: str = Field(..., description="Número do apartamento do morador")

class CriarSessaoResponse(BaseModel):
    session_id: str

class EnviarMensagemRequest(BaseModel):
    texto: str = Field(..., description="Texto da mensagem enviada pelo morador")

class ConfirmacaoPendenteItem(BaseModel):
    id: str
    acao: str
    detalhes: dict[str, Any]

class ConversaResponse(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[ConfirmacaoPendenteItem]

class ResponderConfirmacaoRequest(BaseModel):
    id: str = Field(..., description="Identificador da confirmação pendente")
    confirmado: bool = Field(..., description="Aprovação (True) ou rejeição (False)")

# ----------------- Rotas da Aplicação -----------------

@app.post(
    "/sessoes",
    status_code=status.HTTP_201_CREATED,
    response_model=CriarSessaoResponse,
    summary="Cria uma nova sessão vinculada a um apartamento",
)
async def criar_sessao(req: CriarSessaoRequest):
    """
    Garantia 2: O apartamento é definido uma única vez, na criação da sessão,
    e representa o morador autenticado.
    """
    session_id = await criar_nova_sessao(req.apartamento.strip())
    return {"session_id": session_id}

@app.post(
    "/sessoes/{session_id}/mensagens",
    status_code=status.HTTP_200_OK,
    response_model=ConversaResponse,
    summary="Envia uma mensagem de texto para o assistente",
)
async def enviar_mensagem(session_id: str, req: EnviarMensagemRequest):
    user_id = await obter_user_id_da_sessao(session_id)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada",
        )

    resultado = await processar_mensagem_usuario(session_id, user_id, req.texto)
    return resultado

@app.post(
    "/sessoes/{session_id}/confirmacoes",
    status_code=status.HTTP_200_OK,
    response_model=ConversaResponse,
    summary="Responde formalmente a uma confirmação pendente",
)
async def responder_confirmacao(session_id: str, req: ResponderConfirmacaoRequest):
    """
    Garantia 1: Cobrança ou acesso só com confirmação formal do sistema.
    Retorna 409 caso o ID não corresponda a uma confirmação pendente ativa nesta sessão.
    """
    user_id = await obter_user_id_da_sessao(session_id)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada",
        )

    resultado = await processar_resposta_confirmacao(
        session_id=session_id,
        user_id=user_id,
        conf_id=req.id,
        confirmado=req.confirmado,
    )
    if resultado is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não existe confirmação pendente com o ID '{req.id}' nesta sessão.",
        )

    return resultado

@app.get(
    "/sessoes/{session_id}/eventos",
    status_code=status.HTTP_200_OK,
    summary="Recupera todo o histórico de eventos gravados da sessão",
)
async def ver_eventos_sessao(session_id: str):
    user_id = await obter_user_id_da_sessao(session_id)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada",
        )

    eventos = await obter_eventos_sessao(session_id, user_id)
    if eventos is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada",
        )
    return eventos

# ----------------- Rotas de Verificação Administrativas -----------------

@app.get(
    "/apartamentos/{apartamento}/reservas",
    status_code=status.HTTP_200_OK,
    summary="Consulta administrativa das reservas de um apartamento",
)
async def ver_reservas_apartamento(apartamento: str):
    """Lê diretamente os dados do condomínio, sem passar pelo modelo."""
    return listar_reservas_apartamento(apartamento.strip())

@app.get(
    "/apartamentos/{apartamento}/visitantes",
    status_code=status.HTTP_200_OK,
    summary="Consulta administrativa dos visitantes de um apartamento",
)
async def ver_visitantes_apartamento(apartamento: str):
    """Lê diretamente os dados do condomínio, sem passar pelo modelo."""
    return listar_visitantes_apartamento(apartamento.strip())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)
