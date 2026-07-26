import pathlib, subprocess, sys

SCRIPT = pathlib.Path(__file__).parent.parent / "patches" / "install_postgres_client.py"

MOCK = """FROM node:22-slim AS builder
WORKDIR /app
RUN apt-get update \\
  && apt-get install -y --no-install-recommends git build-essential python3 \\
  && rm -rf /var/lib/apt/lists/*
RUN pnpm build

FROM node:22-slim AS runner
RUN apt-get update \\
  && apt-get install -y --no-install-recommends git \\
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app
USER node
"""


def run_in(tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                          capture_output=True, text=True)


def test_installs_client_in_runner_only(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    r = run_in(tmp_path)
    assert r.returncode == 0, r.stderr
    out = (tmp_path / "Dockerfile").read_text()
    assert out.count("postgresql-client") == 1
    runner = out[out.index("AS runner"):]
    assert "--no-install-recommends git postgresql-client \\\n" in runner
    # builder stage (which also apt-installs git) untouched.
    assert out[:out.index("AS runner")] == MOCK[:MOCK.index("AS runner")]
    # the RUN chain still continues into the apt-lists cleanup.
    assert "&& rm -rf /var/lib/apt/lists/*" in runner


def test_idempotent(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    assert run_in(tmp_path).returncode == 0
    once = (tmp_path / "Dockerfile").read_text()
    assert run_in(tmp_path).returncode == 0
    twice = (tmp_path / "Dockerfile").read_text()
    assert once == twice
    assert twice.count("postgresql-client") == 1


def test_fails_loudly_without_runner_stage(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM node AS builder\nRUN apt-get install -y --no-install-recommends git\n")
    r = run_in(tmp_path)
    assert r.returncode != 0
    # builder-only Dockerfile must come out byte-identical.
    assert "postgresql-client" not in (tmp_path / "Dockerfile").read_text()


def test_fails_loudly_on_single_line_apt_chain(tmp_path):
    # No trailing continuation: the package list is followed by more shell
    # commands, so appending to it would make postgresql-client an operand of
    # whatever ran last (`rm -rf ...`) instead of a package to install.
    single_line = MOCK.replace(
        "RUN apt-get update \\\n"
        "  && apt-get install -y --no-install-recommends git \\\n"
        "  && rm -rf /var/lib/apt/lists/*\n"
        "WORKDIR /app\n",
        "RUN apt-get update && apt-get install -y --no-install-recommends git"
        " && rm -rf /var/lib/apt/lists/*\n"
        "WORKDIR /app\n",
        1,
    )
    assert single_line != MOCK
    (tmp_path / "Dockerfile").write_text(single_line)
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "refusing to guess" in r.stderr
    assert (tmp_path / "Dockerfile").read_text() == single_line


def test_fails_loudly_without_runner_apt_line(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK.replace(
        "  && apt-get install -y --no-install-recommends git \\\n", "", 1))
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "refusing to guess" in r.stderr
