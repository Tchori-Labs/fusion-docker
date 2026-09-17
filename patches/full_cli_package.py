#!/usr/bin/env python3
"""Build the complete CLI package surface, minus the Electron desktop runtime.

Upstream's tsup CLI packaging has two modes (packages/cli/tsup.config.ts,
wantsFullCliPackage): a "fast" default that emits only bin.js/extension.js +
PG migrations, and a "full" mode that additionally stages the pi extensions
(dist/pi-claude-cli, dist/droid-cli, dist/pi-llama-cpp) and every bundled
plugin (dist/plugins/*). Full mode turns on via FUSION_CLI_FULL_PACKAGE=1,
CI=true, or npm_lifecycle_event=prepack.

`docker build` propagates none of those - GitHub Actions' CI=true lives on the
runner, not inside the build - so our image shipped fast-mode output. The
runner stage's `COPY --from=builder /app/packages/cli/dist` then faithfully
copied a dist that had no extensions and no plugins, which the dashboard
surfaces as:

  - "Extension load failed: not-installed" on the Claude CLI / Droid CLI /
    llama.cpp provider cards (resolveClaudeCliExtensionFromModuleUrl finds no
    pi-claude-cli/package.json and returns {status: "not-installed"}), and
    ready:false on GET /api/providers/claude-cli/status;
  - every bundled plugin stuck at state:"error" with
    "Plugin entry does not exist: .../dist/plugins/<id>/bundled.js".

Setting the env is half the fix. Full mode also calls
ensureDesktopRuntimeAssetsBuilt(), which shells out to
`pnpm --filter @fusion/desktop build` (Electron + a ~1300-package `pnpm deploy`
closure, 30-minute budget) whenever packages/desktop/dist is absent - and it is
ALWAYS absent here, on two independent counts: the root build excludes
@fusion/desktop (scripts/build-workspace.mjs ROOT_BUILD_EXCLUDED_PACKAGES) and
upstream's .dockerignore strips dist/ from the build context. That sub-build is
both the slowest thing in the image and pointless: this image is a headless
node server on :4040 that never launches Electron, and skip_electron_download.py
deliberately keeps the Electron binary out of every stage.

So pre-seed packages/desktop/dist inside the builder. ensureDesktopRuntimeAssets
Built() short-circuits on existsSync, the staged dist/desktop stays an inert
placeholder, and everything else full mode produces is staged for real. The
seeding must happen in the Dockerfile rather than in the checked-out tree
precisely because .dockerignore would drop it.

The runner's existing wholesale COPY of packages/cli/dist then carries the
result over, but it needs one adjustment: upstream's `RUN chown node:node /app`
is NOT recursive, so everything COPYed from the builder stays root-owned, and
the plugin loader hot-reloads by copying <plugin>/bundled.js to a sibling
.bundled.reload-N.js inside that same root-owned directory. Staging the plugins
therefore just moves their failure from ENOENT to
"EACCES: permission denied, copyfile ...". Setting ownership on the COPY itself
fixes it for free; a recursive chown would fork a second ~2 GB layer.

Idempotent.
"""
import sys

BUILD_ANCHORS = (
    "RUN pnpm build\n",
    "RUN NODE_OPTIONS=--max-old-space-size=6144 pnpm build\n",
)

CLI_DIST_COPY = "COPY --from=builder /app/packages/cli/dist ./packages/cli/dist\n"
CLI_DIST_COPY_OWNED = (
    "# fusion-docker: the runtime user must own the staged CLI dist - the plugin\n"
    "# loader writes .bundled.reload-N.js siblings next to each bundled.js, and\n"
    "# upstream's `chown node:node /app` is not recursive.\n"
    "COPY --from=builder --chown=node:node /app/packages/cli/dist ./packages/cli/dist\n"
)

BLOCK = """# fusion-docker: stage the full CLI package surface (pi extensions + bundled
# plugins). Upstream defaults to fast packaging unless CI/prepack/this env is
# set, and docker build inherits none of those -> dist/pi-claude-cli and
# dist/plugins would be missing from the image.
ENV FUSION_CLI_FULL_PACKAGE=1
# fusion-docker: full packaging otherwise shells out to an Electron desktop
# build (~1300-package closure) that this headless image never launches. The
# ensure-step short-circuits on an existing packages/desktop/dist, so seed an
# inert one here - .dockerignore strips dist/, so it cannot come from the
# build context.
RUN mkdir -p packages/desktop/dist \\
  && echo 'fusion-docker placeholder: headless image, Electron desktop runtime intentionally not built' \\
     > packages/desktop/dist/README.fusion-docker
"""

src = open("Dockerfile").read()
if "FUSION_CLI_FULL_PACKAGE" in src:
    print("full_cli_package: already present, no-op")
    sys.exit(0)

build_count = sum(src.count(anchor) for anchor in BUILD_ANCHORS)
if build_count != 1:
    sys.exit(f"full_cli_package: expected exactly one supported pnpm build line, "
             f"found {build_count} - upstream Dockerfile changed shape, refusing to guess")

ANCHOR = next(anchor for anchor in BUILD_ANCHORS if src.count(anchor) == 1)

idx = src.index(ANCHOR)

# The seeding RUN must land after the full source tree is in the image, or the
# mkdir is clobbered by a later `COPY . .`.
copy_all = src.find("COPY . .\n")
if copy_all == -1 or copy_all > idx:
    sys.exit("full_cli_package: no 'COPY . .' before the build step - upstream "
             "Dockerfile changed shape, refusing to guess")

# Builder stage only: nothing after 'AS runner' may be touched.
runner = src.find("AS runner")
if runner != -1 and idx > runner:
    sys.exit("full_cli_package: build step sits in the runner stage - upstream "
             "Dockerfile changed shape, refusing to guess")

if src.count(CLI_DIST_COPY) != 1:
    sys.exit("full_cli_package: expected exactly one wholesale COPY of "
             "packages/cli/dist in the runner, found "
             f"{src.count(CLI_DIST_COPY)} - upstream Dockerfile changed shape, "
             "refusing to guess")

out = src[:idx] + BLOCK + src[idx:]
out = out.replace(CLI_DIST_COPY, CLI_DIST_COPY_OWNED, 1)

with open("Dockerfile", "w") as f:
    f.write(out)
print("full_cli_package: FUSION_CLI_FULL_PACKAGE=1 + inert packages/desktop/dist "
      "seeded in builder; staged CLI dist COPYed as node:node")
