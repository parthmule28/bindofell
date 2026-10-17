"""Acquire the reviewed OMOP release locally, or verify an existing acquisition offline."""

import argparse
from pathlib import Path

from bindofell.metadata.acquisition import acquire_omop, verify_acquisition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(".data/omop-v5.5.0"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    operation = verify_acquisition if args.verify_only else acquire_omop
    manifest = operation(args.output_dir)
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
