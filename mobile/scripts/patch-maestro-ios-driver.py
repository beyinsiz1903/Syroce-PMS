"""Pin the upstream iOS snapshot fix until Maestro ships it in a CLI release.

Upstream source a2e7e6e (#3773), official rebuilt drivers 46ebef7a.
Only simulator resources are replaced; CLI classes and smoke assertions stay intact.
"""
import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import zipfile

COMMIT = "46ebef7a844e3d75ce64f2689cb44e3aab8bf0e3"
PREFIX = "driver-iPhoneSimulator/Debug-iphonesimulator/"
PINS = {
    "maestro-driver-ios.zip": "1ecd80866efcff696dc27ab9e15588c59427a12bf5b588e0f6f8ae3a13418e1f",
    "maestro-driver-iosUITests-Runner.zip": "abca81a33462269421cc8ec4c829303b5b32832c17feff30349284e88cd49cf6",
}


def verified(data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Upstream simulator driver checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip():
            raise ValueError("Upstream simulator driver archive is corrupt")
    return data


def patch(home, resources):
    targets = []
    for path in (home / "lib").glob("*.jar"):
        with zipfile.ZipFile(path) as jar:
            if all(PREFIX + name in jar.namelist() for name in resources):
                targets.append(path)
    if len(targets) != 1:
        raise ValueError("Expected exactly one Maestro JAR containing simulator drivers")
    target = targets[0]
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        replacement = Path(temporary) / target.name
        with zipfile.ZipFile(target) as source, zipfile.ZipFile(replacement, "w") as output:
            for entry in source.infolist():
                payload = resources.get(entry.filename.removeprefix(PREFIX)) if entry.filename.startswith(PREFIX) else None
                output.writestr(entry, payload if payload is not None else source.read(entry))
        replacement.chmod(target.stat().st_mode)
        replacement.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maestro-home", type=Path, required=True)
    args = parser.parse_args()
    resources = {}
    with tempfile.TemporaryDirectory() as temporary:
        for name, checksum in PINS.items():
            download = Path(temporary) / name
            url = f"https://raw.githubusercontent.com/mobile-dev-inc/Maestro/{COMMIT}/maestro-ios-driver/src/main/resources/{PREFIX}{name}"
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https", "--retry", "3", "--output", str(download), url], check=True)
            resources[name] = verified(download.read_bytes(), checksum)
    patch(args.maestro_home, resources)
    print(f"Pinned official Maestro simulator drivers: {COMMIT} (SHA-256 verified)")


if __name__ == "__main__":
    main()
