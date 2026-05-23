#!/usr/bin/env python3
"""Build and package eMuleBB-published aMule Windows releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path


DEFAULT_VERSION = "3.0.0-emulebb.1"
PE_MACHINES = {"x64": 0x8664, "ARM64": 0xAA64}
MSYSTEMS = {"x64": "MINGW64", "ARM64": "CLANGARM64"}
PORTABLE_ROOTS = {"x64": "amule-portable-x64", "ARM64": "amule-portable-arm64"}
KEY_BINARIES = ("amule.exe", "amuled.exe", "amulecmd.exe", "amulegui.exe", "ed2k.exe")
REPO_URL = "https://github.com/emulebb/amule"
UPSTREAM_URL = "https://github.com/amule-project/amule"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and package aMule for Windows.")
    parser.add_argument("--version", default=DEFAULT_VERSION, help=f"Release version. Defaults to {DEFAULT_VERSION}.")
    parser.add_argument("--platform", required=True, choices=sorted(PE_MACHINES), help="Windows target platform.")
    parser.add_argument("--configuration", default="Release", choices=["Release"], help="Build configuration.")
    parser.add_argument("--clean", action="store_true", help="Clean the selected portable build outputs before building.")
    parser.add_argument("--output-root", type=Path, default=None, help="Directory where release artifacts are written.")
    parser.add_argument("--msys2-root", type=Path, default=None, help="Optional explicit MSYS2 root.")
    parser.add_argument("--require-clean", action="store_true", help="Fail if the aMule git worktree is dirty.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_root = (args.output_root or repo_root / "dist" / f"amule-{args.version}").resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if args.require_clean and git_dirty(repo_root):
        raise SystemExit("aMule source tree is dirty; commit or clean it before release packaging.")

    if args.clean:
        clean_outputs(repo_root, args.platform)
    build_windows_zip(repo_root, args)
    source_zip = find_built_zip(repo_root, args.platform)
    package = create_release_artifacts(repo_root, output_root, source_zip, args)
    print(f"aMule package: {package['zip_path']}")
    print(f"aMule manifest: {package['manifest_path']}")
    print(f"aMule SHA256: {package['sha256_path']}")
    print(f"SHA256: {package['zip_sha256']}")
    return 0


def clean_outputs(repo_root: Path, platform: str) -> None:
    arch = platform.lower()
    for path in (
        repo_root / f"build-windows-{arch}",
        repo_root / f"amule-portable-{arch}",
        repo_root / "dist",
    ):
        assert_under(path, repo_root)
        if path.exists():
            shutil.rmtree(path)


def build_windows_zip(repo_root: Path, args: argparse.Namespace) -> None:
    msys2_root = resolve_msys2_root(args.msys2_root)
    bash = msys2_root / "usr" / "bin" / "bash.exe"
    build_script = repo_root / "packaging" / "windows" / "build.sh"
    if not build_script.is_file():
        raise SystemExit(f"aMule Windows build script is missing: {build_script}")

    command = (
        "set -euo pipefail; "
        f"cd {sh_quote(windows_path_to_msys(repo_root))}; "
        "./packaging/windows/build.sh build"
    )
    subprocess.run(
        [str(bash), "-lc", command],
        cwd=msys2_root,
        check=True,
        env=msys2_environment(msys2_root, args.platform),
    )


def resolve_msys2_root(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    override = os.environ.get("EMULE_MSYS2_ROOT")
    if override:
        candidates.append(Path(override))
    candidates.extend((Path("C:/msys64"), Path("C:/tools/msys64")))
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if (root / "usr" / "bin" / "bash.exe").is_file():
            return root
    checked = ", ".join(str(path) for path in candidates)
    raise SystemExit(f"MSYS2 bash.exe was not found. Checked: {checked}")


def msys2_environment(msys2_root: Path, platform: str) -> dict[str, str]:
    env = os.environ.copy()
    msystem = MSYSTEMS[platform]
    env["MSYSTEM"] = msystem
    env["WINDOWS_MSYSTEM"] = msystem
    env["CHERE_INVOKING"] = "1"
    env["MSYS2_PATH_TYPE"] = "inherit"
    toolchain_bin = "mingw64" if platform == "x64" else "clangarm64"
    env["PATH"] = f"{msys2_root / toolchain_bin / 'bin'};{msys2_root / 'usr' / 'bin'};{env.get('PATH', '')}"
    return env


def windows_path_to_msys(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        raise SystemExit(f"Cannot convert path without drive to MSYS2 form: {resolved}")
    return f"/{drive}/" + "/".join(resolved.parts[1:])


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def find_built_zip(repo_root: Path, platform: str) -> Path:
    arch = "arm64" if platform == "ARM64" else "x64"
    candidates = sorted((repo_root / "dist").glob(f"aMule-*-Windows-{arch}.zip"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise SystemExit(f"aMule build did not produce dist/aMule-*-Windows-{arch}.zip")
    return candidates[-1]


def create_release_artifacts(
    repo_root: Path,
    output_root: Path,
    source_zip: Path,
    args: argparse.Namespace,
) -> dict[str, Path | str]:
    asset_arch = "arm64" if args.platform == "ARM64" else "x64"
    asset_name = f"emulebb-amule-{args.version}-windows-{asset_arch}.zip"
    zip_path = output_root / asset_name
    manifest_path = output_root / f"emulebb-amule-{args.version}-windows-{asset_arch}.manifest.json"
    sha256_path = output_root / f"emulebb-amule-{args.version}-windows-{asset_arch}.sha256.txt"
    for path in (zip_path, manifest_path, sha256_path):
        assert_under(path, output_root)

    manifest = build_manifest(repo_root, source_zip, asset_name, args)
    shutil.copy2(source_zip, zip_path)
    zip_sha256 = sha256(zip_path)
    manifest["zipSha256"] = zip_sha256
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(manifest_text, encoding="utf-8", newline="\n")
    sha256_path.write_text(f"{zip_sha256}  {asset_name}\n", encoding="utf-8", newline="\n")
    return {
        "zip_path": zip_path,
        "manifest_path": manifest_path,
        "sha256_path": sha256_path,
        "zip_sha256": zip_sha256,
    }


def build_manifest(repo_root: Path, source_zip: Path, asset_name: str, args: argparse.Namespace) -> dict[str, object]:
    with zipfile.ZipFile(source_zip) as archive:
        names = archive.namelist()
        root = find_zip_root(names, args.platform)
        files = []
        for binary in KEY_BINARIES:
            entry = f"{root}/bin/{binary}"
            data = archive.read(entry)
            assert_pe_machine(data, entry, args.platform)
            files.append(
                {
                    "path": entry,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    return {
        "schemaVersion": "emulebb-amule.package.v1",
        "packageName": "emulebb-amule",
        "assetName": asset_name,
        "version": args.version,
        "configuration": args.configuration,
        "platform": args.platform,
        "repository": REPO_URL,
        "upstreamProject": UPSTREAM_URL,
        "sourceBranch": git_output(repo_root, "branch", "--show-current"),
        "sourceCommit": git_output(repo_root, "rev-parse", "HEAD"),
        "sourceDescribe": git_output(repo_root, "describe", "--tags", "--always"),
        "sourceDirty": git_dirty(repo_root),
        "builtAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceZip": source_zip.name,
        "zipEntryCount": len(names),
        "zipRoot": root,
        "keyBinaries": files,
    }


def find_zip_root(names: list[str], platform: str) -> str:
    expected = PORTABLE_ROOTS[platform]
    prefix = f"{expected}/"
    if any(name.startswith(prefix) for name in names):
        return expected
    roots = sorted({name.split("/", 1)[0] for name in names if "/" in name})
    raise SystemExit(f"aMule ZIP root {expected!r} was not found. Roots: {roots}")


def assert_pe_machine(data: bytes, name: str, platform: str) -> None:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise SystemExit(f"Not a PE executable: {name}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise SystemExit(f"Invalid PE header: {name}")
    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
    expected = PE_MACHINES[platform]
    if machine != expected:
        raise SystemExit(f"{name} has PE machine 0x{machine:04x}, expected 0x{expected:04x} for {platform}")


def git_output(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        return ""


def git_dirty(repo_root: Path) -> bool:
    return bool(git_output(repo_root, "status", "--porcelain"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_under(path: Path, root: Path) -> None:
    path.resolve().relative_to(root.resolve())


if __name__ == "__main__":
    sys.exit(main())
