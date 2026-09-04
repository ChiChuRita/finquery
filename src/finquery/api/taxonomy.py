"""The profile's category taxonomy, one level deep."""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from finquery.api.profiles import get_profile_or_404
from finquery.db import Category

router = APIRouter()


class SubcategoryOut(BaseModel):
    id: str
    name: str


class CategoryOut(BaseModel):
    id: str
    name: str
    subcategories: list[SubcategoryOut]


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(request: Request, profile_id: str) -> list[CategoryOut]:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = session.scalars(
            select(Category)
            .options(selectinload(Category.subcategories))
            .where(Category.profile_id == profile_id)
            .order_by(Category.position)
        ).all()
        return [
            CategoryOut(
                id=row.id,
                name=row.name,
                subcategories=[SubcategoryOut(id=sub.id, name=sub.name) for sub in row.subcategories],
            )
            for row in rows
        ]
