import os, pathlib, subprocess, sys

SCRIPT = pathlib.Path(__file__).parent.parent / "patches" / "full_cli_package.py"

MOCK = """FROM node:22-slim AS builder
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/cli/package.json ./packages/cli/package.json
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM node:22-slim AS runner
WORKDIR /app
RUN pnpm install --frozen-lockfile --prod --filter @runfusion/fusion
COPY --from=builder /app/packages/cli/dist ./packages/cli/dist
USER node
"""


def run_in(tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                          env=dict(os.environ), capture_output=True, text=True)


def test_enables_full_package_in_builder_before_build(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    r = run_in(tmp_path)
    assert r.returncode == 0, r.stderr
    out = (tmp_path / "Dockerfile").read_text()

    assert out.count("ENV FUSION_CLI_FULL_PACKAGE=1") == 1
    # the env must be in effect when the build runs
    assert out.index("FUSION_CLI_FULL_PACKAGE") < out.index("RUN pnpm build")
    # and it must be the builder's build, not anything in the runner stage
    assert out.index("FUSION_CLI_FULL_PACKAGE") < out.index("AS runner")


def test_seeds_desktop_dist_after_source_copy(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    assert run_in(tmp_path).returncode == 0
    out = (tmp_path / "Dockerfile").read_text()

    assert "mkdir -p packages/desktop/dist" in out
    # a later `COPY . .` would wipe the seeded directory
    assert out.index("COPY . .") < out.index("mkdir -p packages/desktop/dist")
    # and it must exist before the packaging step consults it
    assert out.index("mkdir -p packages/desktop/dist") < out.index("RUN pnpm build")


def test_staged_cli_dist_is_copied_as_node(tmp_path):
    """The plugin loader writes .bundled.reload-N.js next to each bundled.js,
    and upstream's `chown node:node /app` is not recursive - without this the
    staged plugins fail at runtime with EACCES instead of ENOENT."""
    (tmp_path / "Dockerfile").write_text(MOCK)
    assert run_in(tmp_path).returncode == 0
    out = (tmp_path / "Dockerfile").read_text()

    assert "COPY --from=builder --chown=node:node /app/packages/cli/dist" in out
    # the un-owned form must be gone, not duplicated
    assert "COPY --from=builder /app/packages/cli/dist" not in out


def test_runner_otherwise_untouched(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    assert run_in(tmp_path).returncode == 0
    out = (tmp_path / "Dockerfile").read_text()
    runner = out[out.index("AS runner"):]
    expected = MOCK[MOCK.index("AS runner"):].replace(
        "COPY --from=builder /app/packages/cli/dist ./packages/cli/dist\n",
        "COPY --from=builder --chown=node:node /app/packages/cli/dist ./packages/cli/dist\n",
    )
    # only the ownership flag changed; comment lines are the patch's own
    assert [l for l in runner.splitlines() if not l.startswith("#")] == expected.splitlines()


def test_fails_loudly_without_cli_dist_copy(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM node:22-slim AS builder\nCOPY . .\nRUN pnpm build\n"
        "FROM node:22-slim AS runner\nCOPY --from=builder /app/packages/core/dist ./x\n"
    )
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "refusing to guess" in r.stderr


def test_idempotent(tmp_path):
    (tmp_path / "Dockerfile").write_text(MOCK)
    assert run_in(tmp_path).returncode == 0
    once = (tmp_path / "Dockerfile").read_text()
    assert run_in(tmp_path).returncode == 0
    twice = (tmp_path / "Dockerfile").read_text()
    assert once == twice
    assert twice.count("ENV FUSION_CLI_FULL_PACKAGE=1") == 1


def test_fails_loudly_without_build_step(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM node:22-slim AS builder\nCOPY . .\nRUN pnpm build:full\n"
    )
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "refusing to guess" in r.stderr


def test_fails_loudly_when_build_precedes_source_copy(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM node:22-slim AS builder\nRUN pnpm build\nCOPY . .\n"
    )
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "refusing to guess" in r.stderr


def test_fails_loudly_on_duplicate_build_steps(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM node:22-slim AS builder\nCOPY . .\nRUN pnpm build\nRUN pnpm build\n"
    )
    r = run_in(tmp_path)
    assert r.returncode != 0
    assert "refusing to guess" in r.stderr
