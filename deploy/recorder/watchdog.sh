#!/bin/sh
set -eu

container=race-lens-recorder
health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container")
[ "$health" != unhealthy ] || docker restart "$container"
