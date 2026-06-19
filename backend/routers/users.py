# backend/routers/users.py << 'EOF'

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.db.queries.users import create_user, get_user, list_users, deactivate_user

router = APIRouter(prefix="/users", tags=["users"])

class CreateUserRequest(BaseModel):
    name: str

@router.post("", status_code=201)
def create_user_endpoint(body: CreateUserRequest):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name cannot be empty")
    row = create_user(body.name.strip())
    row["created_at"] = str(row["created_at"])
    return row

@router.get("")
def list_users_endpoint():
    rows = list_users()
    for r in rows:
        r["created_at"] = str(r["created_at"])
    return rows

@router.get("/{user_id}")
def get_user_endpoint(user_id: str):
    row = get_user(user_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found")
    row["created_at"] = str(row["created_at"])
    return row

@router.delete("/{user_id}", status_code=204)
def deactivate_user_endpoint(user_id: str):
    found = deactivate_user(user_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found")
