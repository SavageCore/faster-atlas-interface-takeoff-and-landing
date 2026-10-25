#!/usr/bin/env python3
"""Render one variant of the Faster Atlas Interface mod.

Reads the patch table in src/patches.tsv, applies the variant factor to every
base value, writes the rendered Lua script and the expected values that
make verify checks the built EXML against.

The table drives both, so a value can never be patched without also being
checked, and the two can never drift apart.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def read_table(path):
    """Return the patch rows as (file, prop, base, op, limit, scopes) tuples."""
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 6:
                raise SystemExit("bad patch row (need 6 tab separated fields): %r" % line)
            file_path, prop, base, op, limit, scopes = parts
            rows.append(
                (
                    file_path.strip(),
                    prop.strip(),
                    float(base),
                    op.strip(),
                    float(limit),
                    scopes.strip(),
                )
            )
    return rows


def parse_scopes(spec):
    """Parse "scope:factor,scope:factor" into {scope: factor}."""
    wanted = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise SystemExit("bad scope spec %r, want scope:factor" % part)
        scope, factor = part.split(":", 1)
        wanted[scope.strip()] = float(factor)
    return wanted


def in_scope(scopes, wanted):
    """A row is patched when any one of its scope tags is asked for."""
    tags = {s.strip() for s in scopes.split(",") if s.strip()}
    return bool(tags & set(wanted))


def compute(base, op, limit, factor):
    """Apply the factor to one base value, clamped to the limit."""
    if op == "mul":
        value = base * factor
        if value > limit:
            value = limit
    elif op == "div":
        value = base / factor
        if value < limit:
            value = limit
    else:
        raise SystemExit("unknown op %r" % op)
    return value


def render_value(value):
    """Format a value the way MBINCompiler writes it."""
    return "%.6f" % value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--factor", required=True, type=float)
    parser.add_argument("--desc", required=True)
    parser.add_argument("--scopes", default="forces:1,approach:1")
    parser.add_argument("--template", default=os.path.join(HERE, "landing.lua.in"))
    parser.add_argument("--table", default=os.path.join(HERE, "patches.tsv"))
    parser.add_argument("--out-script", required=True)
    parser.add_argument("--out-expected", required=True)
    args = parser.parse_args()

    rows = read_table(args.table)
    wanted = parse_scopes(args.scopes)

    # Group the rows by file, keeping the order the table lists them in, so
    # the rendered script patches each file once.
    order = []
    grouped = {}
    for file_path, prop, base, op, limit, scopes in rows:
        if not in_scope(scopes, wanted):
            continue
        # A row can be tagged with more than one scope. The factor comes
        # from the scope the variant asked for, so a variant can give one
        # group a different factor than another.
        factor = next(wanted[tag] for tag in scopes.split(",") if tag.strip() in wanted)
        if file_path not in grouped:
            grouped[file_path] = []
            order.append(file_path)
        grouped[file_path].append((prop, compute(base, op, limit, factor)))

    patch_lines = []
    expected_lines = []
    for file_path in order:
        for prop, value in grouped[file_path]:
            patch_lines.append(
                '    { file = "%s", prop = "%s", value = "%s" },'
                % (file_path, prop, render_value(value))
            )
            expected_lines.append("%s\t%s\t%s" % (file_path, prop, render_value(value)))

    with open(args.template, encoding="utf-8") as handle:
        template = handle.read()

    rendered = (
        template.replace("@VARIANT_LABEL@", args.variant)
        .replace("@DESC@", args.desc)
        .replace("@PATCHES@", "\n".join(patch_lines))
    )

    if "@" in rendered:
        leftover = [line for line in rendered.split("\n") if "@" in line]
        raise SystemExit("unsubstituted placeholder left in the script: %r" % leftover)

    with open(args.out_script, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    with open(args.out_expected, "w", encoding="utf-8") as handle:
        handle.write("\n".join(expected_lines) + "\n")

    print(
        "rendered %s: %d files, %d values (factor %g, scopes %s)"
        % (args.variant, len(order), len(expected_lines), args.factor, args.scopes)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
