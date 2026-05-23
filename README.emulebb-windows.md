# eMuleBB aMule Windows packaging

This repository is the eMuleBB-maintained Windows packaging fork of aMule.
The upstream aMule project remains `https://github.com/amule-project/amule`.

## Repeatable package command

From a Windows shell with MSYS2 installed:

```powershell
python tools\package_windows.py --platform x64 --configuration Release --clean --require-clean
```

The script launches the existing `packaging/windows/build.sh` recipe in the
matching MSYS2 environment, copies the produced portable ZIP to a stable
eMuleBB release asset name, and writes manifest and SHA256 sidecar files.

Default output is written under:

```text
dist\amule-3.0.0-emulebb.1\
```

The workspace-level equivalent is:

```powershell
python -m emule_workspace package-amule --config Release --platform x64 --clean --release-version 3.0.0-emulebb.1
```

That command writes artifacts under the canonical workspace state release
directory.

## Architectures

- `x64` uses MSYS2 `MINGW64`.
- `ARM64` uses MSYS2 `CLANGARM64`.

Both paths use the same wrapper, but the matching MSYS2 toolchain and aMule
dependencies must be installed before the build can run.

## Release contents

Each package run produces:

- `emulebb-amule-VERSION-windows-ARCH.zip`
- `emulebb-amule-VERSION-windows-ARCH.manifest.json`
- `emulebb-amule-VERSION-windows-ARCH.sha256.txt`

The manifest records the source commit, `git describe` value, dirty state,
source ZIP name, ZIP root, entry count, and SHA256 hashes for the main Windows
executables.
