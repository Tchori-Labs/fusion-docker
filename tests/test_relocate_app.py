import os, pathlib, subprocess, sys

SCRIPT = pathlib.Path(__file__).parent.parent / "patches" / "relocate_app.py"

MOCK = """FROM node AS builder
WORKDIR /app
RUN pnpm build
FROM node AS runner
WORKDIR /project
COPY --from=builder /project/node_modules/typebox /project/node_modules/typebox
RUN chown node:node /project
USER node
ENTRYPOINT ["node", "packages/cli/dist/bin.js"]
"""

ENV = dict(os.environ, FUSION_VERSION="0.60.0",
           NPM_BEFORE="2026-07-13T17:32:37.000Z")


def run_in(tmp_path, env=ENV):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                          env=env, capture_output=True, text=True)


def test_relocates_and_bakes_fn(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    r = run_in(tmp_path)
    assert r.returncode == 0, r.stderr
    out = (tmp_path / "Dockerfile").read_text()
    runner = out[out.index("AS runner"):]
    # build steps run at /app; the final image cwd is the /project data dir
    # (upstream roots cwd-relative state at the launch directory)
    assert runner.count("WORKDIR /project") == 1
    assert runner.index("WORKDIR /app") < runner.index("USER node")
    assert runner.index("USER node") < runner.index("WORKDIR /project")
    assert "RUN mkdir -p /project && chown node:node /app /project" in runner
    assert "ENV HOME=/project\nUSER node" in runner
    assert "RUN npm install -g runfusion.ai@0.60.0 --before=2026-07-13T17:32:37.000Z" in runner
    assert "/app/node_modules/typebox" in runner
    assert 'ENTRYPOINT ["node", "/app/packages/cli/dist/bin.js"]' in runner
    assert "claude-code" not in out  # toolchain belongs to the agents variant
    # builder stage untouched
    assert out[:out.index("AS runner")] == MOCK[:MOCK.index("AS runner")]


def test_fails_loudly_on_changed_shape(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM node AS runner\nUSER node\n")
    r = run_in(tmp_path)
    assert r.returncode != 0


def test_fails_loudly_without_relative_entrypoint(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK.replace(
        'ENTRYPOINT ["node", "packages/cli/dist/bin.js"]\n', ""))
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "ENTRYPOINT" in r.stderr
