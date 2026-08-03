from app.policies.sensitive_paths import _diff_paths, touches_sensitive_path


def test_diff_paths_from_git_headers():
    diff = "diff --git a/foo bar.py b/foo bar.py\nindex 123..456 100644\n"
    assert _diff_paths(diff) == ["foo bar.py"]


def test_diff_paths_fallback_from_plus_minus():
    diff = "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n"
    assert _diff_paths(diff) == ["src/auth.py"]


def test_diff_paths_skips_dev_null():
    diff = "--- /dev/null\n+++ b/new.py\n"
    assert _diff_paths(diff) == ["new.py"]


def test_diff_paths_empty():
    assert _diff_paths("no diff headers here") == []


def test_touches_sensitive_path_auth():
    assert touches_sensitive_path("--- a/auth/views.py\n+++ b/auth/views.py\n")


def test_touches_sensitive_path_env():
    assert touches_sensitive_path("--- a/.env\n+++ b/.env\n")


def test_touches_sensitive_path_infra_and_k8s():
    assert touches_sensitive_path("--- a/infra/deploy.py\n+++ b/infra/deploy.py\n")
    assert touches_sensitive_path("--- a/k8s/gateway.yaml\n+++ b/k8s/gateway.yaml\n")


def test_touches_sensitive_path_payment():
    assert touches_sensitive_path("--- a/payments/checkout.py\n+++ b/payments/checkout.py\n")


def test_touches_sensitive_path_migrations():
    assert touches_sensitive_path("--- a/migrations/0001_init.py\n+++ b/migrations/0001_init.py\n")


def test_added_secret_looking_content_detected():
    diff = (
        "--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,3 @@\n def x():\n+    api_key = \"sk-1234567890abcdef\"\n"
    )
    assert touches_sensitive_path(diff)


def test_added_private_key_detected():
    diff = (
        "--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,3 @@\n def x():\n+    -----BEGIN RSA PRIVATE KEY-----\n+    MIIEpA==\n"
    )
    assert touches_sensitive_path(diff)


def test_added_aws_credentials_detected():
    diff = (
        "--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,3 @@\n def x():\n+    aws_secret_access_key = \"AKIAIOSFODNN7EXAMPLE\"\n"
    )
    assert touches_sensitive_path(diff)


def test_clean_diff_not_sensitive():
    diff = (
        "--- a/src/math_utils.py\n+++ b/src/math_utils.py\n@@ -1,2 +1,3 @@\n def add(a, b):\n     return a + b\n+def double(n):\n+    return 2 * n\n"
    )
    assert touches_sensitive_path(diff) is False
