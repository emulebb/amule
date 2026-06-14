# Rules

- Read `EMULEBB_WORKSPACE_ROOT\repos\emulebb-tooling\docs\WORKSPACE-POLICY.md`
  first; it is authoritative for workspace-wide rules.
- Start from
  `EMULEBB_WORKSPACE_ROOT\repos\emulebb-tooling\docs\reference\AGENT-CHECKLIST.md`
  for the repeatable operating path.

Everything below is this repo's local deltas only:

- This is the aMule compatibility client used by mixed-client live suites, not a
  shipped eMuleBB product. Treat it as a stock-compatible reference peer and keep
  protocol behavior aligned with stock eD2K/Kad semantics.
- BUILD OUTPUT: orchestrated builds land under
  `%EMULEBB_WORKSPACE_OUTPUT_ROOT%\builds\amule`; never write build output into
  this source tree or anywhere under `c:\prj`. Drive builds through
  `python -m emule_workspace`, not ad-hoc CMake.
- ENV: read machine-level `EMULEBB_*` variables; never assign
  `EMULEBB_WORKSPACE_ROOT` or `EMULEBB_WORKSPACE_OUTPUT_ROOT`. The Windows client
  build may consult the `EMULEBB_MSYS2_ROOT` toolchain knob at a shell/CI boundary.
- aMule is NOT long-path capable. In mixed-client local live suites keep its
  profiles, incoming, temp, and shared directories on short paths (throwaway VHD
  drive-letter roots), per WORKSPACE-POLICY.md "Live Test Storage And Path
  Capability Policy".
- LAN live tests bind through `X_LOCAL_IP` / `--lan-bind-addr`; never bind or
  connect via `127.0.0.1` or `localhost` for harness control on the operator
  split-tunnel machine.