from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _load_backfill_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / (
        "0033_backfill_legacy_learning_runtime.py"
    )
    spec = spec_from_file_location("migration_0033_backfill", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Rows:
    def __init__(self, rows):
        self.rows = rows
        self.read = False

    def fetchmany(self, _size):
        if self.read:
            return []
        self.read = True
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql.lstrip().startswith("SELECT"):
            return _Rows(self.rows)
        self.statements.append((sql, params))
        return None


def test_legacy_runtime_migration_preserves_known_state_and_marks_unknowns() -> None:
    migration = _load_backfill_migration()
    row = SimpleNamespace(
        id="01J00000000000000000000001",
        user_id="01J00000000000000000000002",
        course_id="01J00000000000000000000003",
        material_version_id="01J00000000000000000000004",
        chapter_object_id=None,
        state="paused",
        hint_level=2,
        status="paused",
        version=7,
        created_at="2026-09-01T00:00:00+00:00",
    )
    connection = _Connection([row])
    with (
        patch.object(migration.op, "get_bind", return_value=connection),
        patch.object(
            migration,
            "new_ulid",
            side_effect=["01J00000000000000000000005", "01J00000000000000000000006"],
        ),
    ):
        migration.upgrade()

    assert len(connection.statements) == 3
    task_sql, task_params = connection.statements[0]
    teaching_sql, teaching_params = connection.statements[1]
    episode_sql, episode_params = connection.statements[2]
    assert "release_snapshot, completion" in task_sql
    assert "release_snapshot, completion" in task_sql and "NULL" in task_sql
    assert task_params["id"] == row.id
    assert task_params["status"] == "paused"
    assert '"source": "legacy_state"' in task_params["completion"]
    assert teaching_params["state"] == "paused"
    assert teaching_params["state_version"] == 7
    assert teaching_params["hint_budget"] == 1
    assert episode_params["status"] == "paused"
    assert episode_params["summary"].find('"turn_count": "unknown"') >= 0
    assert episode_params["teaching_session_id"] == teaching_params["id"]
    assert "CAST(:context AS JSON)" in teaching_sql
    assert "CAST(:summary AS JSON)" in episode_sql
