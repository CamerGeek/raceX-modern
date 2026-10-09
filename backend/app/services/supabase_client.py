from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.core.config import get_settings


class SupabaseClientWrapper:
    def __init__(self, client: Client | None = None):
        settings = get_settings()
        self.client = client or create_client(settings.supabase_url, settings.supabase_key)

    def table(self, name: str):
        return self.client.table(name)

    def select_one(self, table: str, *, filters: list[tuple[str, str, Any]] | None = None, order_by: tuple[str, str] | None = None) -> dict[str, Any] | None:
        query = self.client.table(table).select("*")
        for column, operator, value in filters or []:
            if operator == "eq":
                query = query.eq(column, value)
            elif operator == "is":
                query = query.is_(column, value)
            elif operator == "in":
                query = query.in_(column, value)
            elif operator == "gt":
                query = query.gt(column, value)
            else:
                raise ValueError(f"Unsupported filter operator: {operator}")
        if order_by:
            column, direction = order_by
            query = query.order(column, desc=(direction.lower() == "desc"))
        result = query.limit(1).execute()
        return result.data[0] if result.data else None

    def list(self, table: str, *, filters: list[tuple[str, str, Any]] | None = None, limit: int = 100, order_by: tuple[str, str] | None = None) -> list[dict[str, Any]]:
        query = self.client.table(table).select("*")
        for column, operator, value in filters or []:
            if operator == "eq":
                query = query.eq(column, value)
            else:
                raise ValueError(f"Unsupported filter operator: {operator}")
        if order_by:
            column, direction = order_by
            query = query.order(column, desc=(direction.lower() == "desc"))
        return query.limit(limit).execute().data or []

    def insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table(table).insert(payload).execute()
        return result.data[0] if result.data else {}

    def upsert_many(self, table: str, rows: list[dict[str, Any]], *, on_conflict: str) -> list[dict[str, Any]]:
        if not rows:
            return []
        result = self.client.table(table).upsert(rows, on_conflict=on_conflict).execute()
        return result.data or []

    def update(self, table: str, *, id_value: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table(table).update(payload).eq("id", id_value).execute()
        return result.data[0] if result.data else {}

    def upsert(self, table: str, *, key: str, key_value: Any, payload: dict[str, Any], on_conflict: str | None = None) -> dict[str, Any]:
        request = {key: key_value, **payload}
        if on_conflict:
            result = self.client.table(table).upsert(request, on_conflict=on_conflict).execute()
        else:
            result = self.client.table(table).upsert(request).execute()
        return result.data[0] if result.data else {}

    def rpc(self, function: str, parameters: dict[str, Any]) -> Any:
        return self.client.rpc(function, parameters).execute().data
