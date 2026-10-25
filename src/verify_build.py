#!/usr/bin/env python3
"""Check the built Faster Atlas Interface variants.

For every variant this asserts, per patched file:

  1. the EXML exists and was produced by this run, not carried over from a
     previous one
  2. every expected property carries the expected value
  3. the patch touches nothing else - the self closing properties in the
     EXML are exactly the expected set
  4. there are no marker tags, which would leave the patch visibly
     annotated in game

Job 1 covers the failure mode the others cannot see. The build copies out of
the AMUMSS CreatedMODS directory, which is a persistent directory this mod
does not own. When a script changes nothing AMUMSS creates nothing and
leaves the previous build's file sitting there, and the copy then succeeds
and the other jobs happily validate last week's output.
"""

import argparse
import os
import re
import sys

LEAF = re.compile(r'<Property\s+name="([^"]*)"\s+value="([^"]*)"\s*/>')


def read_expected(path):
    """Return the expected rows as (file, prop, value) tuples."""
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            file_path, prop, value = line.split("\t")
            rows.append((file_path, prop, value))
    return rows


def check_variant(build, mod_set, variant, expected_path, failures):
    """Check one variant, appending any problems to failures."""
    script = os.path.join(build, "%s.lua" % variant)
    rows = read_expected(expected_path)

    per_file = {}
    order = []
    for file_path, prop, value in rows:
        if file_path not in per_file:
            per_file[file_path] = []
            order.append(file_path)
        per_file[file_path].append((prop, value))

    for file_path in order:
        # AMUMSS drops the .MBIN suffix and writes the patch next to the
        # source tree, so the EXML path is the MBIN path with the suffix
        # swapped and the file name turned into a directory.
        rel = file_path[:-len(".MBIN")] + ".EXML"
        exml = os.path.join(build, "%s - %s" % (mod_set, variant), rel.replace("/", os.sep))

        if not os.path.isfile(exml):
            failures.append("%s: MISSING %s" % (variant, rel))
            continue

        if os.path.getmtime(exml) < os.path.getmtime(script):
            failures.append(
                "%s: STALE %s - older than the script that should have produced it"
                % (variant, rel)
            )
            continue

        with open(exml, encoding="utf-8") as handle:
            text = handle.read()

        if "!#" in text:
            failures.append("%s: marker tags present in %s" % (variant, rel))

        leaves = LEAF.findall(text)
        found = {}
        for name, value in leaves:
            found.setdefault(name, []).append(value)

        for prop, value in per_file[file_path]:
            if prop not in found:
                failures.append("%s: %s is missing %s" % (variant, rel, prop))
            elif value not in found[prop]:
                failures.append(
                    "%s: %s has %s = %s, want %s"
                    % (variant, rel, prop, found[prop][0], value)
                )

        # Job 3: nothing outside the expected set may be in the patch.
        expected_props = {prop for prop, _ in per_file[file_path]}
        for name in found:
            if name not in expected_props:
                failures.append(
                    "%s: %s patches %s too - the patch is not minimal" % (variant, rel, name)
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True)
    parser.add_argument("--mod-set", required=True)
    parser.add_argument("--variants", required=True)
    args = parser.parse_args()

    failures = []
    for variant in args.variants.split():
        expected = os.path.join(args.build, "%s.expected.tsv" % variant)
        if not os.path.isfile(expected):
            failures.append("%s: missing expected values file %s" % (variant, expected))
            continue
        check_variant(args.build, args.mod_set, variant, expected, failures)

    if failures:
        for failure in failures:
            print("BAD " + failure, file=sys.stderr)
        return 1

    print(
        "verify: OK (%d variants, fresh this run, minimal patches, no marker tags)"
        % len(args.variants.split())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
