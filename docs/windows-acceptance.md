# Native Windows acceptance

The dedicated [Windows acceptance workflow](../.github/workflows/windows-acceptance.yml)
runs on GitHub's `windows-2025` host with Python 3.11.5 and Node 24.4.1. It installs
the Python and frontend lockfiles, prepares and verifies the real local embedding
model, runs the complete backend/frontend suites, builds the frontend, and exercises
both direct service startup and the actual `startup.bat` wrapper.

The native runners use fresh temporary storage, require 500 synthetic products,
exercise HTTP previews and real local upload/retrieval, and compare final prices
and versions with the initial snapshot. They require zero price writes, stopped
owned processes, free service ports and removed temporary storage. The batch runner
also requires a delivered CTRL_BREAK_EVENT and a fully drained Windows Job Object;
forced cleanup fails acceptance.

## November 17, 2026 verification

Commit `ff89acd543cb90c3524df2c72b7ec70f02be8549` was pushed to
`codex/windows-acceptance`, starting
[run 43998968639](https://github.com/arndutta/gpt-video/actions/runs/43998968639).
Checkout, Python/Node setup, locked dependency installation and real local embedding
preparation/verification passed. The backend step continued beyond its normal local
duration, so no Windows acceptance is inferred from that partial result.

Commit `ec2b7e3f084b7a11c5aec2155b3794bc45dc48f3` adds verbose backend progress,
a 120-second faulthandler stack dump and a 10-minute backend-step timeout, retaining
every test and the 30-minute overall bound. Its
[diagnostic run](https://github.com/arndutta/gpt-video/actions/runs/43999467233)
is being evaluated. Native acceptance remains open until both JSON reports pass.

All four action pins were checked directly against their upstream Git tags:

| Action | Version | Verified commit |
| --- | --- | --- |
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-python | v7.1.0 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| actions/setup-node | v7.1.0 | `949feb2413d6458794dcd2491c4babbbce0c15c1` |
| actions/upload-artifact | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |

## Native frontend defect and rerun

[Run 44102071674](https://github.com/arndutta/gpt-video/actions/runs/44102071674)
reached the frontend suite and exposed `ERR_UNSUPPORTED_ESM_URL_SCHEME`: Node's
`--import` received a Windows drive path instead of a file URL. Commit `befd7fc`
uses `pathToFileURL(...).href`; the unchanged 67 DOM cases pass locally after the fix.
[Run 44102963955](https://github.com/arndutta/gpt-video/actions/runs/44102963955)
is exercising the corrected loader. Earlier canceled backend attempts have no
passing result or usable progress artifact and remain recorded as incomplete.

Native startup and graceful batch checks now run before the longer backend suite,
with separate native artifact upload. They retain their original zero-write,
owned-cleanup and CTRL_BREAK requirements. Frontend failure does not count as native
service evidence; the corresponding skipped native steps are explicitly incomplete.

## Repeating the check

Push the reviewed commit to `codex/windows-acceptance` or dispatch the workflow for
that branch. Inspect every step and download `windows-acceptance-RUN_ID-ATTEMPT`.
The artifact contains `windows-unit.junit.xml`, `windows-native-acceptance.json`
and `windows-batch-acceptance.json`, retained for seven days. A passing unit suite
alone does not establish native service or graceful batch-wrapper acceptance.

Windows results do not establish browser visual behavior, corporate gateway/model
performance or human/business effectiveness. Those evidence gates are independent.
