"""
Guarded Natural Language Query API Router (Prompt 5.5)
Project: Demand-Decision-Intelligence
"""

from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.core.deps import get_current_user_or_guest
from backend.models.user import User
from backend.models.chat import ChatSession, ChatMessage
from backend.services.nl_query_service import handle_user_natural_language_query

router = APIRouter()


class NaturalLanguageQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Natural language question about supply chain")
    dataset_id: Optional[int] = None
    session_id: Optional[int] = None


@router.post("/query")
def ask_assistant(
    payload: NaturalLanguageQueryRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Guarded Natural Language Q&A over the user's data:
    1. Blocks free-form SQL generation.
    2. Strictly maps query to parameterized templates.
    3. Server-side binds caller's dataset_id scope.
    4. Returns natural language prose AND verifiable tabular/chart data.
    """
    user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    result = handle_user_natural_language_query(
        db=db,
        query_text=payload.query,
        dataset_id=payload.dataset_id,
        user_id=user_id,
        session_id=payload.session_id,
    )
    return result


@router.get("/suggested-prompts")
def get_suggested_prompts():
    """
    Returns verified out-of-the-box prompts that map to whitelisted templates.
    """
    return {
        "status": "success",
        "prompts": [
            {
                "category": "Stockout Risk",
                "prompt": "Which SKUs will stock out before Diwali?",
                "description": "Checks projected stockout dates against upcoming festival surge windows",
            },
            {
                "category": "Dead Stock",
                "prompt": "What's my total capital tied up in dead stock?",
                "description": "Calculates frozen working capital and monthly warehouse storage drag",
            },
            {
                "category": "Replenishment",
                "prompt": "Which items are currently below ROP?",
                "description": "Lists all SKUs operating below their safety reorder buffer",
            },
            {
                "category": "Market Prices",
                "prompt": "Which products should I buy now given prices are rising?",
                "description": "Scans wholesale market price trends for commodity forward-buy opportunities",
            },
            {
                "category": "Top Performers",
                "prompt": "Show me the top 10 SKUs by sales volume",
                "description": "Ranks products by total sales demand and revenue contribution",
            },
        ]
    }


@router.get("/history")
def get_chat_history(
    session_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Returns conversation history for a given chat session or recent sessions.
    """
    user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    if session_id:
        messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
        return {
            "status": "success",
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "sender_role": m.sender_role,
                    "message": m.message,
                    "query_template": m.query_template,
                    "template_params": m.template_params,
                    "execution_ms": m.execution_ms,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }

    # Otherwise list user's sessions
    sess_query = db.query(ChatSession)
    if user_id:
        sess_query = sess_query.filter(ChatSession.user_id == user_id)
    sessions = sess_query.order_by(ChatSession.created_at.desc()).limit(10).all()

    return {
        "status": "success",
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ],
    }


@router.delete("/session/{session_id}")
def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Deletes a specific chat session and all its associated messages.
    """
    sess = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(sess)
    db.commit()
    return {"status": "success", "message": f"Session {session_id} deleted"}


@router.post("/clear")
def clear_all_chat(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Clears all chat history for the user/guest.
    """
    user_id = current_user.id if current_user and getattr(current_user, "id", None) else None
    if user_id:
        sess_ids = [s.id for s in db.query(ChatSession.id).filter(ChatSession.user_id == user_id).all()]
        if sess_ids:
            db.query(ChatMessage).filter(ChatMessage.session_id.in_(sess_ids)).delete(synchronize_session=False)
            db.query(ChatSession).filter(ChatSession.id.in_(sess_ids)).delete(synchronize_session=False)
    else:
        # Clear recent guest sessions
        recent_sessions = db.query(ChatSession).filter(ChatSession.user_id.is_(None)).order_by(ChatSession.created_at.desc()).limit(20).all()
        sess_ids = [s.id for s in recent_sessions]
        if sess_ids:
            db.query(ChatMessage).filter(ChatMessage.session_id.in_(sess_ids)).delete(synchronize_session=False)
            db.query(ChatSession).filter(ChatSession.id.in_(sess_ids)).delete(synchronize_session=False)
    db.commit()
    return {"status": "success", "message": "Chat history cleared"}

