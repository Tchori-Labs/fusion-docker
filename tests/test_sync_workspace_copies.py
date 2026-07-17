import pathlib, subprocess, sys

SCRIPT = pathlib.Path(__file__).parent.parent / "patches" / "sync_workspace_copies.py"

WORKSPACE = """packages:
  - "packages/*"
  - "plugins/*"
"""

DOCKERFILE = """FROM node AS builder
COPY packages/core/package.json ./packages/core/package.json
RUN pnpm install --frozen-lockfile
RUN pnpm build
"""


def run_in(tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                          capture_output=True, text=True)


def make_tree(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text(WORKSPACE)
    (tmp_path / "Dockerfile").write_text(DOCKERFILE)
    for member in ["packages/core", "packages/extra", "plugins/grok-runtime"]:
        d = tmp_path / member
        d.mkdir(parents=True)
        (d / "package.json").write_text("{}")
    # dir NOT in the workspace globs must be ignored
    d = tmp_path / "examples" / "even-cards"
    d.mkdir(parents=True)
    (d / "package.json").write_text("{}")


def test_inserts_missing_workspace_members(tmp_path):
    make_tree(tmp_path)
    r = run_in(tmp_path)
    assert r.returncode == 0, r.stderr
    out = (tmp_path / "Dockerfile").read_text()
    assert "COPY packages/extra/package.json ./packages/extra/package.json\n" in out
    assert "COPY plugins/grok-runtime/package.json ./plugins/grok-runtime/package.json\n" in out
    assert out.count("COPY packages/core/package.json") == 1  # no dupes
    assert "even-cards" not in out                            # non-member excluded
    # inserted lines sit before the install anchor
    assert out.index("packages/extra") < out.index("RUN pnpm install --frozen-lockfile")


def test_fails_loudly_without_anchor(tmp_path):
    make_tree(tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM node\nRUN true\n")
    r = run_in(tmp_path)
    assert r.returncode != 0
