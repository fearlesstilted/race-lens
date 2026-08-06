# Automated recorder

The Debian worker records every Formula 1 session from FP1 through the race.
It starts races one hour before the published UTC time and every other session
ten minutes early, resumes an interrupted capture, rejects stale or mismatched
SignalR sessions, and keeps raw recordings for recovery. The extra race lead
time only affects local raw data; published archives still begin at the
isolated session boundary. Raw recordings are retained for 14 days by default.
After the archive becomes available it builds the canonical fixture, merges
captured team radio, transcribes it with Whisper, and generates track telemetry
for sessions selected for publication.

By default every recorded session is published to the demo. Change
`RECORDER_PUBLISH_SESSIONS` in the private env file to narrow that policy.

## Install or update

From the server checkout:

```sh
deploy/recorder/install.sh
```

No Compose or sudo is required. The script replaces only the container named
`race-lens-recorder` and never publishes a port. State lives outside Git:

- `~/.config/race-lens-recorder/recorder.env`
- `~/.local/share/race-lens-recorder/data/`
- `~/.local/share/race-lens-recorder/state/`
- `~/.local/share/race-lens-recorder/raw/`

The installer also adds a two-minute host watchdog. Health requires a recent
worker heartbeat and, during capture, a growing raw feed. An unhealthy
container is restarted and resumes the same recording by appending.

## Publication boundary

The container has no repository or SSH key. It can only write an exact fixture,
track, and positions triplet to the staging directory. `publish.py` runs on the
host, validates names, paths, sizes, and the exact file set, then pushes a
single `capture/*` branch. GitHub Actions validates the archive and runs the
full backend, Rust, and frontend checks before fast-forwarding `main`.

This separation means a parser or media dependency compromised inside the
container cannot use Git credentials. The host publisher must be installed by
the operator with its own write-enabled deploy key and cron entry.

Set `RECORDER_GIT_PUBLICATION=1` during storage migration. It keeps this
CI-gated path in parallel with object storage. Change it to `0` only after a
practice, historical qualifying, historical race, duplicate request, and
failure/retry have all passed through production storage.

## Private object storage

Use one private S3-compatible bucket. The browser never talks to it. Add these
values to both Render's secret environment and
`~/.config/race-lens-recorder/recorder.env`; use different credentials for the
two processes:

```sh
RACELENS_S3_ENDPOINT=https://s3-provider.example
RACELENS_S3_REGION=region
RACELENS_S3_BUCKET=race-lens
RACELENS_S3_ACCESS_KEY_ID=...
RACELENS_S3_SECRET_ACCESS_KEY=...
# RACELENS_S3_SESSION_TOKEN=...  # only for temporary credentials
```

Keep the env file at mode `0600`. The bucket stays private and needs no browser
CORS rule.

Render needs `ListBucket` restricted to `requests/`, `status/`, and `sessions/`;
`GetObject` on those prefixes; and `PutObject` only on `requests/`. The worker
needs list/read on `requests/` and `status/`, write on `status/`, multipart
write/copy on `tmp/` and `sessions/`, and delete only on `tmp/`. It does not
need bucket administration or public access.

Tigris Standard is the preferred free-tier provider for this deployment. Use
endpoint `https://t3.storage.dev` and region `auto`. Its
[free tier](https://www.tigrisdata.com/pricing/) includes 5 GB, 10,000 Class A
requests, 100,000 Class B requests, and free egress; existing Race Lens
triplets are roughly 3–17 MB each. Tigris access keys support custom
[AWS-style IAM policies](https://github.com/tigrisdata/storage/tree/main/packages/cli)
so the two permission sets above can be applied without changing the object
contract or adding a gateway.

Cloudflare R2 has a larger free tier, but its long-lived tokens scope
permissions to buckets rather than mixed per-prefix actions. Its
[prefix-scoped temporary credentials](https://developers.cloudflare.com/r2/api/s3/temporary-credentials/)
expire after at most seven days. Do not silently give Render a permanent
bucket-wide write token: add credential rotation or a gateway before choosing
R2 for the strict one-bucket deployment.

The stable object contract is:

```text
requests/{canonical_session_id}.json
status/{canonical_session_id}.json
sessions/{replay_session_id}/manifest.json
sessions/{replay_session_id}/events.jsonl
sessions/{replay_session_id}/track.json
sessions/{replay_session_id}/positions.json
```

The worker uploads to `tmp/`, reads each object back, copies verified files to
`sessions/`, reads them back again, and writes the final manifest last. A
missing or invalid manifest is never exposed as `WATCH`. Failed work retries
twice with backoff, then becomes a safe terminal failure that the user may
explicitly retry.

## Container security

The worker runs as the caller's non-root UID/GID with all capabilities dropped,
`no-new-privileges`, a read-only root filesystem, a no-exec `/tmp`, and CPU,
memory, PID, and descriptor limits. Only `data`, `state`, and `raw` are writable.
Docker's default seccomp and AppArmor profiles remain active. The bridge network
allows outbound F1/FastF1/model traffic; there are no inbound ports.

Docker daemon access remains root-equivalent on the host. This deployment does
not pretend otherwise.

## Checks

```sh
docker inspect race-lens-recorder --format \
  'image={{.Config.Image}} revision={{index .Config.Labels "org.opencontainers.image.revision"}} user={{.Config.User}} status={{.State.Status}} health={{.State.Health.Status}} readonly={{.HostConfig.ReadonlyRootfs}}'
docker port race-lens-recorder          # must print nothing
docker logs --tail 100 race-lens-recorder
python3 deploy/recorder/publish.py      # normally invoked by cron
```
