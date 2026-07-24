import os, pathlib, subprocess, sys

SCRIPT = pathlib.Path(__file__).parent.parent / "patches" / "skip_electron_download.py"

MOCK = """FROM node:22-slim AS builder
WORKDIR /app
RUN pnpm install --frozen-lockfile
FROM node:22-slim AS runner
WORKDIR /app
RUN npm install -g runfusion.ai@0.73.0
USER node
"""


def run_in(tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                          env=dict(os.environ), capture_output=True, text=True)


def test_adds_env_to_every_stage_before_installs(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    r = run_in(tmp_path)
    assert r.returncode == 0, r.stderr
    out = (tmp_path / "Dockerfile").read_text()
    # one ENV per stage
    assert out.count("ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1") == 2
    # and each ENV precedes that stage's install command
    b = out.index("AS builder")
    r_ = out.index("AS runner")
    builder = out[b:r_]
    runner = out[r_:]
    assert builder.index("ELECTRON_SKIP_BINARY_DOWNLOAD") < builder.index("pnpm install")
    assert runner.index("ELECTRON_SKIP_BINARY_DOWNLOAD") < runner.index("npm install")


def test_idempotent(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    assert run_in(tmp_path).returncode == 0
    once = (tmp_path / "Dockerfile").read_text()
    assert run_in(tmp_path).returncode == 0
    twice = (tmp_path / "Dockerfile").read_text()
    assert once == twice
    assert twice.count("ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1") == 2


def test_fails_loudly_without_named_stages(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM node\nRUN pnpm install\n")
    r = run_in(tmp_path)
    assert r.returncode != 0
