#!/usr/bin/env python3
"""Skip Electron's postinstall binary download during the image build.

electron is a transitive dependency in upstream's lockfile (and reachable via
the fn CLI). Its postinstall downloads a ~100 MB platform binary from an
external CDN, which intermittently 504s / times out on CI runners and fails the
build — seen on both the builder `pnpm install --frozen-lockfile` and our runner
`npm install -g runfusion.ai`. The Fusion board runs headless as a node server
on :4040 and never launches Electron, so the binary is dead weight. Setting
ELECTRON_SKIP_BINARY_DOWNLOAD=1 in every build stage makes the image build
immune to that CDN (it downloads nothing), turning a recurring transient failure
into a non-event.

Idempotent; inserts one ENV per `FROM ... AS <stage>` declaration.
"""
import re
import sys

ENV_LINE = "ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1\n"

src = open("Dockerfile").read()
if "ELECTRON_SKIP_BINARY_DOWNLOAD" in src:
    print("skip_electron_download: already present, no-op")
    sys.exit(0)

stages = list(re.finditer(r"^FROM .+? AS \S+\n", src, re.M))
if not stages:
    sys.exit("skip_electron_download: no 'FROM ... AS <stage>' lines found, refusing to guess")

# Insert right after each stage's FROM (walk backwards so earlier offsets hold).
out = src
for m in reversed(stages):
    out = out[: m.end()] + ENV_LINE + out[m.end():]

with open("Dockerfile", "w") as f:
    f.write(out)
print(f"skip_electron_download: ENV added to {len(stages)} stage(s)")
