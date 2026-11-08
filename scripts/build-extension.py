#!/usr/bin/env python3
"""Build FormEditor.cfe using a Designer XML export and the 1C ibcmd utility."""

import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile


def build(platform: Path, source: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    spec = importlib.util.spec_from_file_location(
        "prepare_extension", Path(__file__).with_name("prepare-extension.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ibcmd = platform if platform.stem == "ibcmd" else platform.with_name(
        "ibcmd.exe" if platform.suffix.lower() == ".exe" else "ibcmd")
    if not ibcmd.is_file():
        raise FileNotFoundError("ibcmd is required alongside the platform executable")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="formeditor-extension-") as temporary:
        work = Path(temporary)
        module.prepare(source, work / "xml")
        database = work / "infobase"

        def run(*arguments):
            result = subprocess.run([str(ibcmd), *arguments], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=False)
            details = result.stdout.decode("utf-8-sig", errors="replace")
            if result.returncode:
                raise RuntimeError(f"1C exited with code {result.returncode}\n{details}")
            if details:
                print(details)

        connection = f"--db-path={database}"
        run("infobase", "create", connection)
        run("config", "extension", "create", connection, "--name=FormEditor",
            "--name-prefix=рф_", "--purpose=add-on")
        run("config", "import", connection, "--extension=FormEditor", str(work / "xml"))
        run("config", "check", connection, "--extension=FormEditor")
        artifact = work / "FormEditor.cfe"
        run("config", "save", connection, "--extension=FormEditor", str(artifact))
        if not artifact.is_file() or not artifact.stat().st_size:
            raise RuntimeError("1C did not produce FormEditor.cfe")
        # Exclusive creation also protects against an output created during the build.
        with output.open("xb") as destination:
            destination.write(artifact.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", type=Path, required=True, help="Path to ibcmd or 1cv8 (with ibcmd alongside)")
    parser.add_argument("--source", type=Path, required=True, help="Designer XML export from EDT")
    parser.add_argument("--output", type=Path, default=Path("build/FormEditor.cfe"))
    args = parser.parse_args()
    build(args.platform.resolve(), args.source.resolve(), args.output.resolve())
