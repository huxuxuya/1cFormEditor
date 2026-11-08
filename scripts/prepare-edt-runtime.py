#!/usr/bin/env python3
"""Prepare an isolated Linux Equinox configuration from an installed EDT."""

import argparse
from pathlib import Path
import re
import zipfile


def prepare(installation, destination, swt):
    installation, destination, swt = installation.resolve(), destination.resolve(), swt.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    source = installation / "configuration/org.eclipse.equinox.simpleconfigurator/bundles.info"
    for row in source.read_text().splitlines():
        if row.startswith("#"):
            rows.append(row)
            continue
        fields = row.split(",")
        artifact = Path(fields[2])
        artifact = artifact if artifact.is_absolute() else (installation / artifact).resolve()
        if not artifact.exists():
            raise FileNotFoundError(artifact)
        fields[2] = "/pool/" + artifact.name
        rows.append(",".join(fields))
    with zipfile.ZipFile(swt) as archive:
        manifest = archive.read("META-INF/MANIFEST.MF").decode().replace("\r\n ", "")
    name = re.search(r"Bundle-SymbolicName: ([^;\s]+)", manifest)[1]
    version = re.search(r"Bundle-Version: (\S+)", manifest)[1]
    if name not in {"org.eclipse.swt.gtk.linux.aarch64", "org.eclipse.swt.gtk.linux.x86_64"}:
        raise ValueError("A Linux SWT fragment is required")
    rows.append(f"{name},{version},/work/{swt.name},4,false")
    (destination / "bundles.info").write_text("\n".join(rows) + "\n")
    framework = next(row.split(",")[2] for row in rows if row.startswith("org.eclipse.osgi,"))
    configurator = next(row.split(",")[2] for row in rows if row.startswith("org.eclipse.equinox.simpleconfigurator,"))
    (destination / "config.ini").write_text(
        f"osgi.framework={framework}\n"
        f"osgi.bundles=reference:file:{configurator}@1:start\n"
        "osgi.bundles.defaultStartLevel=4\n"
        "org.eclipse.equinox.simpleconfigurator.configUrl=file:/work/edt-config/bundles.info\n"
        "osgi.configuration.cascaded=false\n"
        "eclipse.p2.data.area=/work/edt-config/p2\n")
    (destination / "startup.txt").write_text((installation / "1cedtcli-startup.txt").read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installation", type=Path, help="EDT directory containing configuration/ and 1cedtcli")
    parser.add_argument("destination", type=Path, help="New directory, mounted at /work/edt-config")
    parser.add_argument("swt", type=Path, help="Linux SWT fragment, mounted under /work")
    args = parser.parse_args()
    prepare(args.installation, args.destination, args.swt)
