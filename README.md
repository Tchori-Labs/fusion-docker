# fusion-docker

Auto-built multi-arch (amd64/arm64) Docker images for
[Runfusion/Fusion](https://github.com/Runfusion/Fusion) — rebuilt
automatically on every upstream release. Upstream ships no image; its
Dockerfile is patched here to fix workspace COPY drift and to make the image
actually updateable under a persistent data volume.

## Tags

| Tag | Contents |
|-----|----------|
| `X.Y.Z`, `latest` | Fusion server + `fn` CLI (pinned to the server version) |
| `X.Y.Z-agents`, `latest-agents` | the above + `gh`, `claude`, `codex`, `bubblewrap` — for boards whose coding agents run inside the container |

`latest*` tags only advance after both variants pass smoke tests on both
architectures.

## Layout (differs from upstream on purpose)

- App code lives in `/app` (inside the image — replaced on every update).
- `/project` is the container user's `$HOME` and the data directory —
  mount your persistent volume there. Fusion state lands in
  `/project/.fusion`.
- Runs as user `node` (uid/gid 1000). The `fn`/`fusion` CLI is preinstalled;
  the dashboard's "install global CLI" self-installer cannot work in a
  container (non-root can't write `/usr/local`) and isn't needed.

## Quick start

```yaml
services:
  fusion:
    image: ghcr.io/tchori-labs/fusion:latest
    restart: unless-stopped
    ports:
      - "4040:4040"
    environment:
      FUSION_SKIP_ONBOARDING: "1"
      FUSION_DASHBOARD_TOKEN: "change-me"   # dashboard/API auth
    volumes:
      - fusion_data:/project
      - /var/run/docker.sock:/var/run/docker.sock   # only if agents use docker
volumes:
  fusion_data: {}
```

Health check: `GET :4040/api/health` (unauthenticated by design).

## How it works

`watch.yml` polls upstream releases every 6 h and dispatches `build.yml`,
which checks out the upstream tag, applies `patches/*.py`, builds both
variants natively per arch, smoke-tests them (health endpoint + every
bundled CLI), and pushes multi-arch manifests. Build breakage auto-files an
issue here.

## License

MIT (this repo and upstream — see LICENSE).
