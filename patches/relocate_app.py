#!/usr/bin/env python3
"""Make upstream's image container-friendly.

Upstream installs the app AT /project (runtime WORKDIR /project, ENTRYPOINT
relative to it). A persistent volume mounted at /project seeds-then-shadows
the app, silently defeating image updates. Move the app to /app; /project
becomes an empty node-owned HOME/data mount. Also bake the fn/fusion CLI:
USER node can't write /usr/local at runtime (the dashboard self-installer
always EACCES-fails in a container), and runfusion.ai's loose ^ deps must be
resolved as of the release publish moment (--before) or newer transitive
releases break the CLI (pi-coding-agent 0.80.10 vs v0.60.0).
All edits are confined to the runtime ("AS runner") stage.
"""
import os
import sys

fusion_ver = os.environ["FUSION_VERSION"]
npm_before = os.environ["NPM_BEFORE"]

src = open("Dockerfile").read()
try:
    i = src.index("AS runner")  # runtime stage only; builder is /app already
    head, tail = src[:i], src[i:]
    assert "WORKDIR /project" in tail, "runtime WORKDIR /project not found"
    tail = tail.replace("WORKDIR /project", "WORKDIR /app")
    tail = tail.replace("/project/node_modules/typebox", "/app/node_modules/typebox")
    tail = tail.replace(
        "RUN chown node:node /project\n",
        "RUN mkdir -p /project && chown node:node /app /project\n",
    )
    assert "USER node\n" in tail, "runtime USER node not found"
    tail = tail.replace("USER node\n", "ENV HOME=/project\nUSER node\n", 1)

    cli = (
        "# fusion-docker: fn CLI pinned to the server version; dep tree "
        "resolved as of release publish (--before)\n"
        f"RUN npm install -g runfusion.ai@{fusion_ver} --before={npm_before}\n"
    )
    assert "WORKDIR /app\n" in tail, "runtime WORKDIR /app not found after rename"
    tail = tail.replace("WORKDIR /app\n", cli + "WORKDIR /app\n", 1)
except (ValueError, AssertionError) as e:
    sys.exit(f"relocate_app: upstream Dockerfile changed shape ({e}), refusing to guess")

with open("Dockerfile", "w") as f:
    f.write(head + tail)
print(f"relocate_app: /app relocation + HOME=/project + fn@{fusion_ver} (--before={npm_before})")
