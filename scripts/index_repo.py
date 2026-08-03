"""CLI to trigger initial indexing of a target repo into the retrieval
service. Run once per repo before submitting intents against it.

    python scripts/index_repo.py --repo sample_app --path /work/sample_app

--path is resolved inside the retrieval container. With the compose stack,
repos under ./scratch/ are mounted at /work/, so point --path at
/work/<repo-dir> even though the checkout lives at ./scratch/<repo-dir>
on the host.
"""
import argparse

import httpx

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--path", required=True, help="path inside the retrieval container, e.g. /work/sample_app")
    parser.add_argument("--retrieval-url", default="http://localhost:8002")
    args = parser.parse_args()

    resp = httpx.post(
        f"{args.retrieval_url}/index",
        json={"repo": args.repo, "repo_path": args.path},
        timeout=300,
    )
    resp.raise_for_status()
    print(resp.json())
