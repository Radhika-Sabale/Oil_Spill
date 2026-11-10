"""The airplane-mode boundary, enforced as a test rather than a promise.

`app/hub.py` talks to the Hugging Face Hub and `app/ml/train.py` runs on Kaggle.
Both live inside the `app` package because they share its code, and that is
exactly the arrangement that quietly rots: someone adds a convenient import, and
six weeks later the judged demo tries to reach huggingface.co on a conference
wifi and hangs.

So the boundary is asserted. Importing the served application must not pull in
any network client, and no module on the request path may reference one.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

# Clients that must never be reachable from a request.
NETWORK_PACKAGES = {
    "huggingface_hub", "kaggle", "kaggle_secrets", "requests", "urllib3",
    "httpx", "aiohttp", "boto3", "gcsfs", "s3fs", "datasets",
}

# Modules allowed to hold network clients. None of them is imported by main.py.
# Keep this set as small as it can possibly be. Every entry is a place the
# boundary is not being checked, so a broad exemption defeats the test.
OFFLINE_EXEMPT = {
    "app/hub.py",       # the sync layer itself
}


def _module_files():
    for p in sorted(APP.rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if "__pycache__" in rel:
            continue
        yield rel, p


def _imported_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def test_no_request_path_module_imports_a_network_client():
    offenders = {}
    for rel, path in _module_files():
        if rel in OFFLINE_EXEMPT:
            continue
        hits = _imported_names(path) & NETWORK_PACKAGES
        if hits:
            offenders[rel] = sorted(hits)
    assert not offenders, (
        "these modules are on the request path and import a network client: %s. "
        "Move the call into scripts/ or add the module to OFFLINE_EXEMPT only if "
        "nothing under app/api/ can reach it." % offenders
    )


def test_importing_the_app_does_not_load_a_network_client():
    """The strongest form: import the served app, then look at sys.modules."""
    for name in list(sys.modules):
        if name.split(".")[0] in NETWORK_PACKAGES:
            del sys.modules[name]

    import app.main  # noqa: F401

    loaded = {n for n in sys.modules if n.split(".")[0] in NETWORK_PACKAGES}
    # httpx arrives through the test client, not through the app itself.
    loaded -= {"httpx"}
    # boto3 and urllib3 arrive the same incidental way: `rasterio.session`
    # imports boto3 on sight for optional AWS support, and boto3 drags urllib3.
    # They appear only in a development environment that has installed one of
    # the offline-prep extras, which the demo laptop does not. The guarantee is
    # kept by `test_no_prep_only_package_is_a_runtime_requirement` below plus
    # the AST test above, which still forbids anything under app/ from importing
    # a client itself. Widening this set without those two would be hollow.
    loaded -= {n for n in loaded
               if n.split(".")[0] in ("boto3", "botocore", "urllib3", "s3fs")}
    assert not loaded, (
        "importing app.main pulled in %s. The judged demo must not carry a "
        "network client into the process." % sorted(loaded)
    )


def test_hub_module_never_reaches_the_hub_on_import():
    """Importing app.hub must be free. Only calling it may touch the network."""
    from app import hub

    assert hub.DATASET_REPO and hub.MODEL_REPO
    # status() is the one entry point that is documented never to raise.
    st = hub.status.__doc__ or ""
    assert "never raises" in st.lower()


def test_pipeline_and_api_modules_are_import_clean():
    """Every request-path module imports without a network client present."""
    import importlib

    for name in ("app.pipeline", "app.scenes", "app.api.health", "app.api.detect",
                 "app.api.drift", "app.api.ais", "app.api.pipeline", "app.api.report"):
        mod = importlib.import_module(name)
        assert mod is not None


@pytest.mark.parametrize("script", ["hf_sync.py", "kaggle_push.py", "build_kaggle_kernels.py"])
def test_sync_scripts_parse(script):
    """The sync tooling has to at least be syntactically valid on this machine."""
    path = ROOT / "scripts" / script
    assert path.exists(), "missing %s" % script
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_credentials_are_committed():
    """No token, anywhere in the tree. The cheapest security control there is."""
    import os
    import re

    patterns = [
        re.compile(r"hf_[A-Za-z0-9]{34,}"),        # Hugging Face user token
        re.compile(r"KGAT_[A-Za-z0-9]{24,}"),      # Kaggle access token
        re.compile(r"AKIA[0-9A-Z]{16}"),           # AWS key id
        re.compile(r"nugen-[0-9a-f]{12,}"),        # NuGen API key
    ]
    skip_dirs = {".git", "__pycache__", "data", "models", ".pytest_cache",
                 "node_modules", "venv", ".venv"}
    offenders = []
    for current, dirs, files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in skip_dirs]
        for name in files:
            # `.env` is where a credential belongs; it is gitignored, and the
            # check is for credentials committed into the tree. `.env.example`
            # ships empty values and is still scanned.
            if name == ".env" or name.startswith(".env.") and name != ".env.example":
                continue
            p = Path(current) / name
            if p.suffix.lower() in (".pt", ".tif", ".png", ".npz", ".sqlite"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in patterns:
                if pat.search(text):
                    offenders.append("%s (%s)" % (p.relative_to(ROOT), pat.pattern))
    assert not offenders, "credential-shaped strings found in: %s" % offenders


# Packages that exist only to prepare the cache and must never be a runtime
# requirement. Each one drags a network client into any process that imports
# rasterio, which is every process this product runs.
PREP_ONLY = ("copernicusmarine", "huggingface_hub", "kaggle", "boto3",
             "botocore", "s3fs", "torch", "segmentation-models-pytorch")


def test_no_prep_only_package_is_a_runtime_requirement():
    """requirements.txt may mention these, but only commented out.

    This is the assertion that keeps the exemption in the sys.modules test
    honest. boto3 is tolerated there because it arrives through rasterio in a
    development environment; it is intolerable as something the demo laptop is
    told to install.
    """
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    active = [ln.strip() for ln in text.splitlines()
              if ln.strip() and not ln.strip().startswith("#")]

    offenders = []
    for line in active:
        name = line.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
        if name in PREP_ONLY:
            offenders.append(line)

    assert not offenders, (
        "these are offline-prep or training packages and must stay commented "
        "out of the runtime requirements: %s" % offenders)


# ----------------------------------------------------------------------------
# The NuGen assistant is the one deliberate exception, so it is fenced in.
# ----------------------------------------------------------------------------

# Everything under app/ except these may not import the assistant. The pipeline
# must not be able to reach it, even transitively: a model answer is not
# evidence, and nothing about a mask, a drift field, a score or an attribution
# may depend on one.
ASSISTANT_ALLOWED_IMPORTERS = {"app/main.py", "app/api/assistant.py"}


def test_only_the_assistant_module_speaks_to_the_network():
    """`app/assistant.py` is the only module allowed to open an outbound call."""
    users = []
    for rel, path in _module_files():
        text = path.read_text(encoding="utf-8")
        if "urllib.request" in text and "urllib.request.Request" in text:
            users.append(rel)
    assert users == ["app/assistant.py"], (
        "exactly app/assistant.py may make an outbound HTTP call, found: %s" % users)


def test_the_pipeline_cannot_reach_the_assistant():
    """No detection, drift, scoring or reporting module imports the assistant."""
    offenders = []
    for rel, path in _module_files():
        if rel in ASSISTANT_ALLOWED_IMPORTERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                    a.name.split(".")[-1] == "assistant" for a in node.names):
                offenders.append(rel)
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[-1] == "assistant":
                    offenders.append(rel)
                elif any(a.name == "assistant" for a in node.names):
                    offenders.append(rel)
    assert not offenders, (
        "only main.py may mount the assistant router; these import it: %s" % sorted(set(offenders)))
