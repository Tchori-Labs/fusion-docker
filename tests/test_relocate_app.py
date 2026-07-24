import os, pathlib, subprocess, sys

SCRIPT = pathlib.Path(__file__).parent.parent / "patches" / "relocate_app.py"

# Upstream <= 0.72.0: app installed AT /project, relative ENTRYPOINT.
MOCK_OLD = """FROM node AS builder
WORKDIR /app
RUN pnpm build
FROM node AS runner
WORKDIR /project
COPY --from=builder /project/node_modules/typebox /project/node_modules/typebox
RUN chown node:node /project
USER node
ENTRYPOINT ["node", "packages/cli/dist/bin.js"]
"""

# Upstream >= 0.73.0 (issue #2414): app at /app, absolute ENTRYPOINT, runtime
# cwd relocated to a fresh /workspace mount point.
MOCK_NEW = """FROM node AS builder
WORKDIR /app
RUN pnpm build
FROM node AS runner
WORKDIR /app
COPY --from=builder /app/node_modules/.pnpm/typebox@*/node_modules/typebox /app/node_modules/typebox
RUN chown node:node /app \\
  && mkdir -p /workspace \\
  && chown node:node /workspace
USER node
WORKDIR /workspace
ENTRYPOINT ["node", "/app/packages/cli/dist/bin.js"]
"""

ENV = dict(os.environ, FUSION_VERSION="0.60.0",
           NPM_BEFORE="2026-07-13T17:32:37.000Z")


def run_in(tmp_path, env=ENV):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                          env=env, capture_output=True, text=True)


def assert_container_friendly(out, mock):
    """End-state invariants both upstream shapes must converge to."""
    runner = out[out.index("AS runner"):]
    # build/install steps run at /app; the final image cwd is the /project data
    # dir (upstream roots cwd-relative state at the launch directory).
    assert runner.count("WORKDIR /project") == 1
    assert runner.index("WORKDIR /app") < runner.index("USER node")
    assert runner.index("USER node") < runner.index("WORKDIR /project")
    # /project must exist node-owned so a fresh named volume seeds node perms.
    assert "chown node:node" in runner and "/project" in runner
    assert "chown node:node /workspace /project" in runner \
        or "chown node:node /app /project" in runner
    # HOME on the data volume, and the CLI baked as root (before USER node).
    assert "ENV HOME=/project" in runner
    assert runner.index("ENV HOME=/project") < runner.index("USER node")
    cli = "RUN npm install -g runfusion.ai@0.60.0 --before=2026-07-13T17:32:37.000Z"
    assert cli in runner
    assert runner.index(cli) < runner.index("USER node")  # root-privileged
    # app referenced by absolute path everywhere it matters.
    assert "/app/node_modules/typebox" in runner
    assert 'ENTRYPOINT ["node", "/app/packages/cli/dist/bin.js"]' in runner
    assert "claude-code" not in out  # toolchain belongs to the agents variant
    # builder stage untouched.
    assert out[:out.index("AS runner")] == mock[:mock.index("AS runner")]


def test_relocates_old_shape(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK_OLD)
    r = run_in(tmp_path)
    assert r.returncode == 0, r.stderr
    assert_container_friendly((tmp_path / "Dockerfile").read_text(), MOCK_OLD)


def test_repoints_new_shape(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK_NEW)
    r = run_in(tmp_path)
    assert r.returncode == 0, r.stderr
    out = (tmp_path / "Dockerfile").read_text()
    assert_container_friendly(out, MOCK_NEW)
    # upstream's /workspace scaffolding is preserved (left empty), not deleted.
    assert "mkdir -p /workspace /project" in out


def test_fails_loudly_on_changed_shape(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM node AS runner\nUSER node\n")
    r = run_in(tmp_path)
    assert r.returncode != 0


def test_fails_loudly_without_relative_entrypoint(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK_OLD.replace(
        'ENTRYPOINT ["node", "packages/cli/dist/bin.js"]\n', ""))
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "ENTRYPOINT" in r.stderr


def test_fails_loudly_new_shape_without_absolute_entrypoint(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK_NEW.replace(
        'ENTRYPOINT ["node", "/app/packages/cli/dist/bin.js"]\n', ""))
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "ENTRYPOINT" in r.stderr
