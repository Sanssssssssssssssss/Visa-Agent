"""Offline backup/restore of the whole case directory, with hashes and path checks."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile

from visa_agent.worker import mail_worker_lock

MANIFEST = "visa-agent-backup.json"
OPERATIONAL = {"worker.lock", "worker.json", "qq-stop", "worker.stdout.log", "worker.stderr.log"}


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup(data, output):
    data, output = Path(data).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(data):
        raise ValueError("Use a new backup path outside the data directory")
    if not (data / "cases.sqlite3").exists():
        raise ValueError("No case database found; nothing to back up")
    # The same OS lock as the poller refuses a backup while it is processing.
    # Other local CLI writers must also be stopped by the operator.
    with mail_worker_lock(data):
        files = [p for p in sorted(data.rglob("*")) if p.is_file() and p.name not in OPERATIONAL]
        if any(p.is_symlink() or not p.resolve().is_relative_to(data) for p in files):
            raise ValueError("Data contains links outside the backup boundary")
        manifest = {"version": 1, "source_root": str(data), "uid": data.stat().st_uid, "gid": data.stat().st_gid,
                    "files": {p.relative_to(data).as_posix(): file_hash(p) for p in files}}
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".partial")
        if temporary.exists():
            raise ValueError("A partial backup exists; inspect it before continuing")
        with tarfile.open(temporary, "w:gz") as archive:
            content = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
            info = tarfile.TarInfo(MANIFEST)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
            for path in files:
                archive.add(path, arcname="data/" + path.relative_to(data).as_posix(), recursive=False)
        temporary.replace(output)
    return {"backup": str(output), "files": len(files), "sha256": file_hash(output)}


def restore(data, source):
    data, source = Path(data).resolve(), Path(source).resolve()
    if data.exists() and any(p.name not in OPERATIONAL for p in data.iterdir()):
        raise ValueError("Restore requires an empty data directory; preserve the existing one first")
    with tarfile.open(source, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive entries")
        for member in members:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or ".." in path.parts
                    or "\\" in member.name or (member.name != MANIFEST and not member.name.startswith("data/"))):
                raise ValueError("Unsafe backup archive entry")
        with archive.extractfile(MANIFEST) as stream:
            manifest = json.load(stream)
        if manifest.get("version") != 1 or manifest["source_root"] != str(data):
            raise ValueError("Restore to the same data path; container backups use /data on every host")
        expected = {"data/" + name for name in manifest["files"]} | {MANIFEST}
        if set(names) != expected:
            raise ValueError("Archive file set differs from manifest")
        # Verify every payload before writing any case data.
        for name, checksum in manifest["files"].items():
            with archive.extractfile("data/" + name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                    raise ValueError("Backup payload hash mismatch")
        owner = (data.stat().st_uid, data.stat().st_gid) if data.exists() else (manifest["uid"], manifest["gid"])
        with mail_worker_lock(data):
            for name in manifest["files"]:
                member = archive.getmember("data/" + name)
                member.name = name
                archive.extract(member, path=data, filter="data")
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                # Maintenance may run as root to read an imported archive; return
                # the named volume to its existing service owner afterwards.
                for path in [data, *data.rglob("*")]:
                    os.chown(path, *owner)
    return {"restored": str(data), "files": len(manifest["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    result = backup(args.data, args.archive) if args.action == "backup" else restore(args.data, args.archive)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
