#!/usr/bin/env python3
"""Make upstream's image container-friendly.

The problem: a persistent volume mounted where the app is installed
seeds-then-shadows the app, silently defeating image updates; and the app
must run with its cwd on that persistent volume, because upstream roots
cwd-relative state there (the unregistered-project fallback writes
.fusion/tasks + .fusion/agents under process.cwd(), and the SQLite->PG
migration_key embeds the launch dir). Our Coolify prod mounts the data volume
at /project, so the final image must: install the app OUTSIDE /project (at
/app), keep the RUNTIME cwd on /project, use an absolute ENTRYPOINT, set
HOME=/project, and bake the fn/fusion CLI (USER node can't write /usr/local at
runtime, and runfusion.ai's loose ^ deps must be resolved as of the release
publish moment via --before, or newer transitive releases break the CLI).

Two upstream shapes are handled:

- Upstream >= 0.73.0 (issue #2414) already installs the app at /app, uses an
  absolute ENTRYPOINT, and relocated the runtime cwd to a fresh /workspace mount
  point. So we only repoint that runtime cwd /workspace -> /project, create
  /project node-owned alongside upstream's /workspace prep, set HOME, and bake
  the CLI. This keeps our /project data-volume convention (and its embedded-PG
  state) unchanged across the upgrade.

- Upstream <= 0.72.0 installs the app AT /project (runtime WORKDIR /project,
  relative ENTRYPOINT). We do the full relocation to /app ourselves. Kept so a
  manual backfill of an old immutable tag still builds.

All edits are confined to the runtime ("AS runner") stage.
"""
import os
import sys

fusion_ver = os.environ["FUSION_VERSION"]
npm_before = os.environ["NPM_BEFORE"]

CLI = (
    "# fusion-docker: fn CLI pinned to the server version; dep tree "
    "resolved as of release publish (--before)\n"
    f"RUN npm install -g runfusion.ai@{fusion_ver} --before={npm_before}\n"
)
CWD_NOTE = (
    "# fusion-docker: runtime cwd on the /project data volume — upstream roots\n"
    "# cwd-relative state (.fusion/tasks, .fusion/agents, embedded-PG migration\n"
    "# key) at the launch dir, so it must live on the persistent mount.\n"
)

src = open("Dockerfile").read()
try:
    i = src.index("AS runner")  # runtime stage only; builder is /app already
    head, tail = src[:i], src[i:]

    if "WORKDIR /workspace" in tail:
        # Upstream >= 0.73.0: app already at /app, ENTRYPOINT already absolute,
        # runtime cwd = /workspace. Repoint cwd to /project, create /project
        # node-owned, set HOME, bake the CLI (root, before USER node).
        assert 'ENTRYPOINT ["node", "/app/packages/cli/dist/bin.js"]' in tail, \
            "expected absolute /app ENTRYPOINT in the >=0.73.0 shape"
        assert "mkdir -p /workspace" in tail, "runtime /workspace mkdir not found"
        tail = tail.replace(
            "mkdir -p /workspace", "mkdir -p /workspace /project", 1
        )
        assert "chown node:node /workspace" in tail, "runtime /workspace chown not found"
        tail = tail.replace(
            "chown node:node /workspace", "chown node:node /workspace /project", 1
        )
        assert "USER node\n" in tail, "runtime USER node not found"
        tail = tail.replace(
            "USER node\n", "ENV HOME=/project\n" + CLI + "USER node\n", 1
        )
        assert "WORKDIR /workspace\n" in tail, "runtime WORKDIR /workspace not found"
        tail = tail.replace(
            "WORKDIR /workspace\n", CWD_NOTE + "WORKDIR /project\n", 1
        )
    else:
        # Upstream <= 0.72.0: app installed AT /project; relocate it to /app.
        assert "WORKDIR /project" in tail, "runtime WORKDIR /project not found"
        tail = tail.replace("WORKDIR /project", "WORKDIR /app")
        tail = tail.replace("/project/node_modules/typebox", "/app/node_modules/typebox")
        tail = tail.replace(
            "RUN chown node:node /project\n",
            "RUN mkdir -p /project && chown node:node /app /project\n",
        )
        assert "USER node\n" in tail, "runtime USER node not found"
        tail = tail.replace(
            "USER node\n",
            "ENV HOME=/project\n"
            "USER node\n"
            + CWD_NOTE
            + "WORKDIR /project\n",
            1,
        )

        entrypoint = 'ENTRYPOINT ["node", "packages/cli/dist/bin.js"]'
        assert entrypoint in tail, "relative ENTRYPOINT not found"
        tail = tail.replace(
            entrypoint, 'ENTRYPOINT ["node", "/app/packages/cli/dist/bin.js"]', 1
        )

        assert "WORKDIR /app\n" in tail, "runtime WORKDIR /app not found after rename"
        tail = tail.replace("WORKDIR /app\n", CLI + "WORKDIR /app\n", 1)
except (ValueError, AssertionError) as e:
    sys.exit(f"relocate_app: upstream Dockerfile changed shape ({e}), refusing to guess")

with open("Dockerfile", "w") as f:
    f.write(head + tail)
print(f"relocate_app: /app app + /project cwd + HOME=/project + fn@{fusion_ver} (--before={npm_before})")
