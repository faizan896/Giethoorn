# Deployment candidate and lifecycle ownership

For a local Intel Mac, use [the Docker-based Mac setup](local-mac.md). It keeps
recordings in a host directory and holds a macOS sleep assertion during a finite
run. The systemd candidate below is for a separate Linux system-manager host;
buying a VPS is not required for current local research/collection.

These are reviewable operations artifacts. No service was installed, enabled,
started through systemd, published or deployed during development.

## Prepared files

- `ops/run-collector-service`: validates its binary/state paths, uses a private
  umask, creates fresh per-start artifacts, then replaces itself with `supervise`.
- `ops/giethoorn.service.in`: a system-manager service template for a dedicated
  account, process-group ownership and finite collection.
- `ops/render_service.py`: renders a new unit file without installing it. Requires
  Python 3; checks existing executable paths and quotes systemd values correctly.
- `ops/test_operations.py`: standard-library tests for process/argument/exit-code
  behavior, fresh paths, renderer inputs and essential unit policy.

The wrapper never resumes, deletes or prunes recordings. It propagates the
supervisor's exit status. A failed collector cannot be hidden by the wrapper.

## Policy

The unit uses `KillMode=control-group`, SIGTERM followed by a bounded forced-stop
deadline, a dedicated service account, private temporary storage, read-only system
paths and a writable state directory. A 256 MiB memory cap, 512-FD limit and
32-task limit are candidate defaults, not validated production capacity claims.

`Restart=no` is intentional. The application already has bounded transient retry
policy; restarting the entire unit after an integrity/recording failure would
mask fail-stop behavior. The example runs a finite 24-hour window and then stops.
Any daily scheduling or automatic whole-service recovery needs a separate policy
that does not bypass failure review.

For the default `/var/lib/giethoorn` state path, systemd's `StateDirectory` manages
creation/ownership. Custom directories must be provisioned by the operator. Paths
must be absolute; state paths with edge whitespace/backslashes are rejected.
Dollar signs are rejected to prevent `ExecStart` environment expansion from
changing paths. Internal spaces and literal percent signs are handled. Template
tokens occurring inside a binary path are preserved, not substituted recursively.

## Target-host preparation

On an actual systemd host, an operator must provision the account and install the
tested release binary/runner at stable readable/executable paths, such as
`/opt/giethoorn/bin/`. Render a new candidate unit there:

```sh
python3 ops/render_service.py \
  --binary /opt/giethoorn/bin/giethoorn \
  --runner /opt/giethoorn/bin/run-collector-service \
  --output ./giethoorn.service
systemd-analyze verify ./giethoorn.service
```

Review the resolved paths/account, state capacity, network route and service
limits before installation. Public data requires no keys. If needed, the optional
`/etc/giethoorn/collector.env` supplies the host's normal proxy/CA bindings; keep
verification enabled and CA files accessible despite `ProtectHome`. Do not copy
credentials into the unit, scripts or repository.

Enabling boot startup and exercising real cgroup/account/signal/reboot behavior
remain target-host actions. No such actions were performed in this cloud task.

## Evidence in this environment

This container's PID 1 is `tail`, not systemd. System-scope verification could not
create `/run/systemd` because that filesystem is read-only. No permission or
infrastructure settings were changed to work around it.

A user-scope **offline** `systemd-analyze verify` with an isolated writable
`XDG_RUNTIME_DIR` successfully parsed the rendered candidate and resolved its
executable. It caught a real renderer bug: `WorkingDirectory` is a scalar path,
so wrapping it in literal quotes made it nonabsolute. The corrected template and
a regression assertion preserve the proper form.

This validates syntax in the available context; it does not prove system-manager
installation, service account setup, cgroup enforcement, boot activation or reboot
recovery. Those remain unrun. The native launcher separately completed a real
60-second public BTC check using an optimized release binary, with three finalized
runs and exact replay matches. See `status.md` for artifact paths/fingerprints.
