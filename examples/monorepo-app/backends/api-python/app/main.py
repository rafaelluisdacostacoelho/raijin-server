"""
API Python - Backend de exemplo usando FastAPI.
Substitua/expanda conforme necessidade do projeto.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone
import os

app = FastAPI(
    title="Meu App - API Python",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


class ItemCreate(BaseModel):
    name: str
    description: str = ""
    price: float


class Item(ItemCreate):
    id: int
    created_at: str


# In-memory store
items_db: list[Item] = []
next_id = 1


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="healthy",
        service="api-python",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.get("/api/v1/items", response_model=list[Item])
def list_items():
    return items_db


@app.post("/api/v1/items", response_model=Item, status_code=201)
def create_item(item: ItemCreate):
    global next_id
    new_item = Item(
        id=next_id,
        name=item.name,
        description=item.description,
        price=item.price,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    items_db.append(new_item)
    next_id += 1
    return new_item


@app.get("/api/v1/items/{item_id}", response_model=Item)
def get_item(item_id: int):
    for item in items_db:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


@app.delete("/api/v1/items/{item_id}", status_code=204)
def delete_item(item_id: int):
    global items_db
    items_db = [i for i in items_db if i.id != item_id]
