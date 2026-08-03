import asyncio
from types import SimpleNamespace

from app import agent
from app.agent import _read_files, generate_patch

from shared.schemas import Plan, PlanStep, RetrievedChunk


def _plan(tmp_path, prompt="bump the version"):
    repo_dir = tmp_path / "myrepo"
    repo_dir.mkdir(exist_ok=True)
    (repo_dir / "a.py").write_text("x = 1\n")
    win = repo_dir / "win.py"
    win.write_text("w = 0\n")
    context = [
        RetrievedChunk(file_path=str(repo_dir / "a.py"), content="x = 1", similarity=0.9),
        RetrievedChunk(file_path=str(repo_dir / "a.py"), content="dup", similarity=0.5),
        RetrievedChunk(file_path=str(repo_dir / "missing.py"), content="", similarity=0.4),
        RetrievedChunk(file_path=str(tmp_path / "other" / "c.py"), content="", similarity=0.3),
        RetrievedChunk(
            file_path=str(win).replace("/", "\\"), content="w = 0", similarity=0.2
        ),
    ]
    return Plan(
        intent_id="i1",
        repo="myrepo",
        steps=[PlanStep(step_id="1", description=prompt)],
        context=context,
    )


def test_read_files_filters_by_repo_and_dedupes(tmp_path):
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "c.py").write_text("z = 3")
    files = _read_files(_plan(tmp_path))
    rels = {rel for rel, _ in files}
    assert rels == {"a.py", "win.py"}
    assert dict(files)["a.py"] == "x = 1\n"
    assert dict(files)["win.py"] == "w = 0\n"


class FakeClient:
    def __init__(self, text):
        self.text = text
        self.prompt = None
        self.system = None
        self.temperature = None

    async def complete(self, prompt, system=None, temperature=0.3):
        self.prompt = prompt
        self.system = system
        self.temperature = temperature
        return SimpleNamespace(
            text=self.text,
            model="model-x",
            prompt_tokens=3,
            completion_tokens=4,
            latency_ms=1.0,
        )


def _patch_from(tmp_path, text="=== a.py ===\nx = 2\n"):
    return asyncio.run(generate_patch(_plan(tmp_path), feedback=None))


def test_generate_patch_default_route(monkeypatch, tmp_path):
    fake = FakeClient("=== a.py ===\nx = 2\n")
    captured = {}

    def fake_get_client(name):
        captured["name"] = name
        return fake

    monkeypatch.setattr(agent, "get_client", fake_get_client)
    patch = asyncio.run(generate_patch(_plan(tmp_path)))

    assert captured["name"] == "codegen-default"
    assert patch.intent_id == "i1"
    assert patch.repo == "myrepo"
    assert patch.model_used == "model-x"
    assert patch.prompt_tokens == 3
    assert patch.completion_tokens == 4
    assert "x = 2" in patch.diff
    assert "--- a/a.py" in patch.diff
    assert "bump the version" in fake.prompt
    assert fake.system is not None


def test_generate_patch_escalates(monkeypatch, tmp_path):
    fake = FakeClient("=== a.py ===\nx = 2\n")
    captured = {}

    def fake_get_client(name):
        captured["name"] = name
        return fake

    monkeypatch.setattr(agent, "get_client", fake_get_client)
    asyncio.run(generate_patch(_plan(tmp_path), escalate=True))
    assert captured["name"] == "codegen-escalation"


def test_generate_patch_model_override_wins(monkeypatch, tmp_path):
    fake = FakeClient("=== a.py ===\nx = 2\n")
    captured = {}

    def fake_get_client(name):
        captured["name"] = name
        return fake

    monkeypatch.setattr(agent, "get_client", fake_get_client)
    asyncio.run(generate_patch(_plan(tmp_path), model_override="custom/model:free", escalate=True))
    assert captured["name"] == "custom/model:free"


def test_generate_patch_passes_feedback(monkeypatch, tmp_path):
    fake = FakeClient("=== a.py ===\nx = 2\n")
    monkeypatch.setattr(agent, "get_client", lambda name: fake)
    asyncio.run(generate_patch(_plan(tmp_path), feedback="tests failed"))
    assert "Previous attempt failed" in fake.prompt
    assert "tests failed" in fake.prompt


def test_generate_patch_empty_rewrite_yields_empty_diff(monkeypatch, tmp_path):
    fake = FakeClient("no sections here")
    monkeypatch.setattr(agent, "get_client", lambda name: fake)
    patch = asyncio.run(generate_patch(_plan(tmp_path)))
    assert patch.diff == ""
