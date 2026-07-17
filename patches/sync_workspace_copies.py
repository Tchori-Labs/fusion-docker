#!/usr/bin/env python3
"""Insert COPY lines for workspace members upstream's Dockerfile omits.

Upstream hand-lists each workspace package.json and lags pnpm-workspace.yaml
(v0.58.0-v0.60.0 miss grok-runtime), so `pnpm install --frozen-lockfile`
skips those members and the recursive build fails (TS2688). Membership comes
from pnpm-workspace.yaml, NOT the directory tree - dirs excluded from the
workspace are absent from the lockfile and COPYing them would break
--frozen-lockfile.
"""
import glob
import sys

globs, active = [], False
for line in open("pnpm-workspace.yaml"):
    if line.rstrip() == "packages:":
        active = True
    elif active and line.lstrip().startswith("- "):
        globs.append(line.split("- ", 1)[1].strip().strip("\"'"))
    elif active and line.strip() and not line[0].isspace():
        break

pkgs = sorted(p for g in globs for p in glob.glob(f"{g}/package.json"))
lines = open("Dockerfile").readlines()

anchor = "RUN pnpm install --frozen-lockfile\n"
if anchor not in lines:
    sys.exit("sync_workspace_copies: anchor 'RUN pnpm install --frozen-lockfile' "
             "not found - upstream Dockerfile changed shape, refusing to guess")
idx = lines.index(anchor)  # builder stage; runner stage adds --prod

missing = [p for p in pkgs if not any(f"COPY {p}" in l for l in lines)]
for p in missing:
    print(f"patching in: {p}")
    lines.insert(idx, f"COPY {p} ./{p}\n")
    idx += 1
if missing:
    with open("Dockerfile", "w") as f:
        f.writelines(lines)
print(f"sync_workspace_copies: {len(missing)} member(s) inserted")
