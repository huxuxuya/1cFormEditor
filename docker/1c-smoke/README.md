# FormEditor smoke test in Docker

For the common development and test entry points, see
[Development and checks](../../docs/development.md).

The container provides OneScript, Vanessa Runner, Vanessa-ADD, and a virtual X11 display (Xvfb). On Apple Silicon, OneScript and .NET run natively in an ARM64 container. The Linux 1C platform is x86_64, so Docker Desktop has to emulate it.

## Current Apple Silicon limitation

The toolchain-only check passes. The ARM64 image installs the x86_64 runtime libraries needed by the 1C Linux client under Docker Desktop's QEMU. Vanessa Runner uses a thin client, so file infobases are passed through 1C's standalone server `ibsrv`; the image install therefore includes both client and server components. A matching Linux x86_64 **8.5.1.1343** distribution is still required for the prepared `/tmp/form_ib`. Override `PLATFORM_RELEASE` if the infobase was created with another release; the launcher rejects a package set with a different release.

## Toolchain-only check

This builds the image and checks OneScript, Runner, and Xvfb without needing a 1C platform installer. The build defaults to `linux/arm64` on Apple Silicon and `linux/amd64` on Intel/AMD hosts. Override this with `SMOKE_DOCKER_PLATFORM` if needed:

```sh
./scripts/run-container-smoke.sh --check-toolchain
```

## Run BDD against an existing infobase

Put the full Linux x86_64 `.deb` distribution for the same 1C platform release as the infobase into `docker/1c-smoke/platform/`. It must include `common`, `thin-client`, and `server` (with `ibsrv`); the directory is git-ignored. For the current database:

```sh
ONEC_PLATFORM_DEB_DIR=/path/to/1c-linux-debs \
INFOBASE_DIR=/path/to/file-infobase \
./scripts/run-container-smoke.sh
```

For the current prepared base, use `INFOBASE_DIR=/tmp/form_ib`. The runner copies the infobase into its disposable Linux filesystem before starting Vanessa, so the host copy is not modified.

## Rebuild an infobase from EDT export and test it

Export the EDT project to a directory containing `Configuration.xml`, then run:

```sh
ONEC_PLATFORM_DEB_DIR=/path/to/full-1c-linux-platform \
EDT_EXPORT_DIR=/path/to/edt-export \
./scripts/run-container-smoke.sh
```

This mode needs the 1C Designer packages in addition to the client packages. It creates a fresh temporary file infobase, loads the EDT export, updates the database configuration, and runs the BDD feature.

## Artifacts

Logs, Vanessa status, screenshots, JUnit, Allure, and Cucumber reports are written to `build/container-smoke/`. Set `SMOKE_REPORT_DIR` to place them elsewhere.

The 1C platform packages and licenses are intentionally supplied outside the image and are not committed to Git. Do not copy activation files or license keys into the image.
