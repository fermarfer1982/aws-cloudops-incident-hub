from __future__ import annotations

import argparse
from pathlib import Path


AARCH64_ELF_MACHINE = 183


def read_elf_machine(path: Path) -> int:
    with path.open("rb") as handle:
        header = handle.read(20)

    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise ValueError("not a valid ELF binary")

    data_encoding = header[5]

    if data_encoding == 1:
        byteorder = "little"
    elif data_encoding == 2:
        byteorder = "big"
    else:
        raise ValueError(f"unknown ELF data encoding: {data_encoding}")

    return int.from_bytes(header[18:20], byteorder=byteorder)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that native libraries bundled for Lambda "
            "use the AArch64 instruction set."
        )
    )
    parser.add_argument(
        "cdk_out",
        type=Path,
        help="Path to the synthesized CDK output directory",
    )
    args = parser.parse_args()

    root = args.cdk_out.resolve()

    if not root.is_dir():
        raise SystemExit(f"ERROR: CDK output directory not found: {root}")

    native_libraries = sorted(
        path
        for path in root.rglob("*.so")
        if path.is_file()
    )

    if not native_libraries:
        raise SystemExit(
            "ERROR: no native shared libraries were found in the Lambda asset"
        )

    errors: list[str] = []

    for library in native_libraries:
        try:
            machine = read_elf_machine(library)
        except ValueError as exc:
            errors.append(f"{library}: {exc}")
            continue

        if machine != AARCH64_ELF_MACHINE:
            errors.append(
                f"{library}: ELF machine={machine}, expected "
                f"{AARCH64_ELF_MACHINE} (AArch64)"
            )

    if errors:
        print("ERROR: incompatible Lambda native libraries found:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "OK: "
        f"{len(native_libraries)} native Lambda libraries "
        "are compiled for AArch64"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
