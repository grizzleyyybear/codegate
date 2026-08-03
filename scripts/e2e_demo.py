"""Runs the MVP end to end against the local compose stack:

  1. creates + commits the sample repo in ./scratch/sample_app
  2. indexes it into pgvector via the retrieval service
  3. submits a good intent (expect auto_merge) and a bad one (expect not)
  4. prints the git log as proof of the merged commit

Prereqs: `docker compose up --build -d` with .env copied from
.env.example, including a free OPENROUTER_API_KEY (https://openrouter.ai).

    python scripts/e2e_demo.py [--gateway http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx

REPO_DIR = Path(__file__).resolve().parent.parent / "scratch"
REPO_NAME = "sample_app"

GOOD_PROMPT = (
    f"add a function double(n: int) -> int to {REPO_NAME}/math_utils.py that "
    f"returns 2 * n, and a pytest test for it in tests/test_math_utils.py"
)
BAD_PROMPT = (
    "add a pytest test that imports a module named totally_missing_module_xyz, "
    "which does not exist in the repo"
)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def submit_intent(gateway: str, intent_id: str, prompt: str) -> dict:
    resp = httpx.post(
        f"{gateway}/intents",
        json={
            "intent_id": intent_id,
            "repo": REPO_NAME,
            "prompt": prompt,
            "submitted_by": "e2e-demo",
        },
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://localhost:8000")
    args = parser.parse_args()

    # Reset the scratch repo so every run starts from the pristine initial
    # commit (a previous run may have auto-merged changes into it). The
    # delete runs as root inside a container: files the containers wrote
    # into the bind mount are root-owned and undeletable from Windows.
    reset = _run(
        [
            "docker", "compose", "exec", "-T", "validator",
            "sh", "-c", f"rm -rf /work/{REPO_NAME}",
        ],
        check=False,
    )
    if reset.returncode != 0:
        print(f"  warning: could not reset {REPO_NAME}: {reset.stderr.strip()}", file=sys.stderr)

    create = _run([sys.executable, "scripts/create_scratch_repo.py", "--path", str(REPO_DIR / REPO_NAME)], check=False)
    if create.returncode != 0:
        print(f"create_scratch_repo failed: {create.stderr}", file=sys.stderr)
        sys.exit(1)

    index = httpx.post(
        f"{args.gateway.replace('8000', '8002')}/index",
        json={"repo": REPO_NAME, "repo_path": f"/work/{REPO_NAME}"},
        timeout=600,
    )
    index.raise_for_status()
    print(f"indexed: {index.json()}")

    print("\n--- good intent ---")
    good = submit_intent(args.gateway, "e2e-good", GOOD_PROMPT)
    print(f"action: {good['decision']['action']} ({good['decision']['reason']})")
    print(f"confidence: {good['validation']['confidence']}  tests_passed: {good['validation']['tests_passed']}")
    print(f"outcome: {json.dumps(good['outcome'], indent=2)}")

    print("\n--- bad intent ---")
    bad = submit_intent(args.gateway, "e2e-bad", BAD_PROMPT)
    print(f"action: {bad['decision']['action']} ({bad['decision']['reason']})")
    print(f"confidence: {bad['validation']['confidence']}  tests_passed: {bad['validation']['tests_passed']}")

    print("\n--- git log of the scratch repo ---")
    log = _run(["git", "-C", str(REPO_DIR / REPO_NAME), "log", "--oneline", "-5"])
    print(log.stdout or log.stderr)

    good_ok = good["decision"]["action"] == "auto_merge"
    bad_ok = bad["decision"]["action"] != "auto_merge"
    print(f"\nRESULT: good intent auto-merged: {good_ok} | bad intent kept out: {bad_ok}")
    sys.exit(0 if (good_ok and bad_ok) else 1)


if __name__ == "__main__":
    main()
