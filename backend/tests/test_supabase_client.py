from app.services.supabase_client import SupabaseClientWrapper


class _Query:
    def __init__(self) -> None:
        self.filters: list[tuple[str, str, object]] = []

    def select(self, *_: object):
        return self

    def eq(self, column: str, value: object):
        self.filters.append(("eq", column, value))
        return self

    def is_(self, column: str, value: object):
        self.filters.append(("is", column, value))
        return self

    def limit(self, _: int):
        return self

    def execute(self):
        return type("Response", (), {"data": []})()


class _Client:
    def __init__(self) -> None:
        self.query = _Query()

    def table(self, _: str) -> _Query:
        return self.query


def test_select_one_supports_null_filters() -> None:
    wrapper = SupabaseClientWrapper.__new__(SupabaseClientWrapper)
    wrapper.client = _Client()

    assert wrapper.select_one("meetings", filters=[("name", "is", "null")]) is None
    assert wrapper.client.query.filters == [("is", "name", "null")]
