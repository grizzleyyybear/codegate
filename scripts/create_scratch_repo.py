"""Creates the small sample repo the MVP pipeline runs against, at
./scratch/sample_app (mounted into every container as /work/sample_app).

It's a tiny, ruff/mypy/bandit-clean Python package with real pytest tests
and an initial git commit — enough surface for retrieval to index and for
the validator to run meaningful checks on a generated patch.

    python scripts/create_scratch_repo.py [--path scratch/sample_app]
"""
from __future__ import annotations

import argparse
import os
import subprocess

MATH_UTILS = '''"""Basic arithmetic helpers used by the sample app."""


def add(a: float, b: float) -> float:
    return a + b


def multiply(a: float, b: float) -> float:
    return a * b


def is_even(n: int) -> bool:
    return n % 2 == 0
'''

STRING_UTILS = '''"""Small string helpers."""


def title_case(text: str) -> str:
    return text.strip().title()


def word_count(text: str) -> int:
    return len(text.split())
'''

TEST_MATH = '''from math_utils import add, is_even, multiply


def test_add():
    assert add(2, 3) == 5


def test_multiply():
    assert multiply(4, 5) == 20


def test_is_even():
    assert is_even(4)
    assert not is_even(3)
'''

TEST_STRING = '''from string_utils import title_case, word_count


def test_title_case():
    assert title_case("  hello world ") == "Hello World"


def test_word_count():
    assert word_count("one two three") == 3
'''

MYPY_INI = """[mypy]
ignore_missing_imports = True
"""

README = """# Sample App

A deliberately tiny repo used to exercise the Codegate pipeline end to
end: indexing, codegen, validation, and the guardrail gate.
"""

FILES = {
    "math_utils.py": MATH_UTILS,
    "string_utils.py": STRING_UTILS,
    "tests/test_math_utils.py": TEST_MATH,
    "tests/test_string_utils.py": TEST_STRING,
    "mypy.ini": MYPY_INI,
    "README.md": README,
}


def create(repo_path: str) -> None:
    # Write files with LF endings and commit with core.autocrlf=false so
    # the working tree is LF everywhere - on Windows, on the bind mounts,
    # and in the containers' clones. Mixed CRLF/LF causes git apply to
    # fail inside the Linux containers (they have no autocrlf to convert).
    for rel, content in FILES.items():
        target = os.path.join(repo_path, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.exists(target):
            with open(target, "w", newline="\n") as fh:
                fh.write(content)

    if not os.path.isdir(os.path.join(repo_path, ".git")):
        subprocess.run(["git", "init", "-q", repo_path], check=True)
        subprocess.run(
            ["git", "-C", repo_path, "config", "core.autocrlf", "false"], check=True
        )
        subprocess.run(["git", "-C", repo_path, "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", repo_path, "commit", "-q", "-m", "initial sample app"],
            check=True,
        )
    print(f"sample repo ready at {repo_path} (committed)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="scratch/sample_app")
    args = parser.parse_args()
    create(args.path)
