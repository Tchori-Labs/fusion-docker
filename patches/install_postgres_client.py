#!/usr/bin/env python3
"""Install the PostgreSQL client tools in the runtime image.

Fusion's backup/restore shells out to pg_dump/pg_restore, which the embedded
server package does NOT ship (embedded-postgres bundles the server binaries
only). Upstream's resolveClientBinary() (packages/core/src/postgres/pg-backup.ts)
looks on PATH and then in /usr/lib/postgresql/{15,16,17}/bin, so with no client
installed every `fn backup` fails on an image that is otherwise fine.

The embedded server major is 15 (embedded-postgres@15.18.0-beta.17). On the
node:22-slim base (Debian bookworm) `postgresql-client` resolves to the v15
client, which lands in /usr/lib/postgresql/15/bin - the first path upstream
probes - and puts pg_dump/pg_restore on PATH via the postgresql-client-common
wrappers.

Runtime ("AS runner") stage only: the builder stage never runs backups, so its
apt line is left alone. Idempotent.
"""
import re
import sys

PKG = "postgresql-client"

# The runner-stage package list, with any line-continuation backslash split off
# so the package can be appended without breaking the RUN chain.
APT_RE = re.compile(
    r"^(?P<lead>[^\n]*?apt-get install -y --no-install-recommends[ \t]+)"
    r"(?P<pkgs>[^\n\\]*?)"
    r"(?P<cont>[ \t]*\\?)$",
    re.M,
)

src = open("Dockerfile").read()
i = src.find("AS runner")  # runtime stage only; builder needs no pg client
if i < 0:
    sys.exit("install_postgres_client: no 'AS runner' stage found, refusing to guess")
head, tail = src[:i], src[i:]

if re.search(rf"apt-get install[^\n]*\b{PKG}\b", tail):
    print("install_postgres_client: already present, no-op")
    sys.exit(0)

matches = [m for m in APT_RE.finditer(tail) if "git" in m.group("pkgs").split()]
if len(matches) != 1:
    sys.exit(
        f"install_postgres_client: expected exactly 1 runner-stage 'apt-get "
        f"install -y --no-install-recommends ... git' line, found "
        f"{len(matches)} - upstream Dockerfile changed shape, refusing to guess"
    )

m = matches[0]
patched = f"{m.group('lead')}{m.group('pkgs')} {PKG}{m.group('cont')}"
tail = tail[: m.start()] + patched + tail[m.end():]

with open("Dockerfile", "w") as f:
    f.write(head + tail)
print(f"install_postgres_client: {PKG} added to the runner-stage apt install")
