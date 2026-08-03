from app.patch_builder import (
    build_patch_from_rewrites,
    extract_diff,
    parse_rewritten_files,
)


def test_extract_diff_strips_fence():
    raw = "Here is the patch:\n```diff\n--- a/x\n+++ b/x\n```"
    assert extract_diff(raw) == "--- a/x\n+++ b/x"


def test_parse_rewritten_files_splits_sections():
    raw = (
        "=== math_utils.py ===\n"
        "def add(a, b):\n    return a + b\n\n"
        "=== tests/test_math_utils.py ===\n"
        "from math_utils import add\n\ndef test_add():\n    assert add(1, 2) == 3"
    )
    rewrites = parse_rewritten_files(raw)
    assert rewrites == {
        "math_utils.py": "def add(a, b):\n    return a + b",
        "tests/test_math_utils.py": "from math_utils import add\n\ndef test_add():\n    assert add(1, 2) == 3",
    }


def test_parse_rewritten_files_empty_without_markers():
    assert parse_rewritten_files("no sections here") == {}


def test_build_patch_ignores_unchanged_files():
    files = [("a.py", "x = 1")]
    rewrites = {"a.py": "x = 1"}
    assert build_patch_from_rewrites(files, rewrites) == ""


def test_build_patch_produces_applyable_hunk():
    files = [("math_utils.py", "def add(a, b):\n    return a + b\n")]
    rewrites = {"math_utils.py": "def add(a, b):\n    return a + b\n\n\ndef double(n):\n    return 2 * n\n"}
    diff = build_patch_from_rewrites(files, rewrites)
    assert diff.startswith("--- a/math_utils.py")
    assert "+++ b/math_utils.py" in diff
    assert "def double" in diff
    assert "-0,0" not in diff
