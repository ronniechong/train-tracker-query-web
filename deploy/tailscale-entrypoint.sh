#!/bin/sh
# Brings up tailscaled, authenticates, then publishes the shared network
# namespace's Caddy port via Funnel. Written by hand rather than relying on
# the image's built-in `TS_*` env-var handling because that covers
# `tailscale up` but not `tailscale funnel` — this just runs the steps
# directly.
#
# Requires Funnel enabled for this node in the tailnet's admin console
# first (a one-time, out-of-band step this script cannot perform).
set -eu

tailscaled --state=/var/lib/tailscale/tailscaled.state \
	--socket=/var/run/tailscale/tailscaled.sock &

until tailscale status --json >/dev/null 2>&1; do
	sleep 1
done

tailscale up --authkey="${TS_AUTHKEY}" --hostname="${TS_HOSTNAME}" --accept-dns=false

tailscale funnel --bg "${TARGET_PORT}"

# Gives `service` (on the internal-only `ingress` network, reachable here
# because `tailscale` shares Caddy's netns, which is also on `ingress`) a
# route to train-tracker's tailnet-only API. Bound to all interfaces in
# this shared namespace, not just loopback, on purpose -- `service`
# connects to it as caddy:1055. Deliberately separate from Funnel above:
# this proxy is never exposed publicly, only used outbound from inside
# this host.
tailscale set --outbound-http-proxy-listen=:1055

wait
