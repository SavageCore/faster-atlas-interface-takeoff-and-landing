#!/usr/bin/env python3
"""Check the Faster Atlas Interface installer.

Every option is a plain plugin with one folder in its own file list: pick one
of the nine and that one folder is copied. There is deliberately no
conditional file install, where a plugin sets flags and a pattern elsewhere
decides what to copy.

That is not a style choice. A conditional install was tried and shipped, and
Amethyst applied every pattern in it regardless of the flags, copying all nine
variants into the same folder with the last one winning. The result was a mod
that installed cleanly, looked right in the manager, and was not the option
the player picked. So this script treats a conditional install as an error,
and checks, in the build tree before packing and again against the packed zip:

  1. the wizard has exactly one step, SelectExactlyOne
  2. every plugin copies exactly one folder, always into the one mod folder
  3. every plugin's folder is one of the shipped variants - never a
     diagnostic - and no variant is offered twice
  4. every shipped variant is offered, and every offered folder was built
     with its script and at least one EXML in it

Job 4 is the one that covers the AMUMSS failure mode: a variant whose script
stops matching produces no EXML, the copy out of CreatedMODS fails, and
without this check the installer would still look valid.

The mods here are unpacked mods: the installer copies the EXML tree and the
lua script, not a pak, so the checks look for those.
"""

import argparse
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

VERSION = re.compile(r"[vV]?[0-9]+(\.[0-9]+)+")


def check_config(config_path, mod_set, variants, diag, failures):
    """Check the wizard and return the folders it offers."""
    root = ET.parse(config_path).getroot()

    if root.tag != "config":
        failures.append("ModuleConfig.xml: root is %s, want config" % root.tag)
        return []

    name = (root.findtext("moduleName") or "").strip()
    if name != mod_set:
        failures.append("moduleName is %r, want %r" % (name, mod_set))
    if VERSION.search(name):
        failures.append("moduleName carries a version: %r" % name)

    if root.find("conditionalFileInstalls") is not None:
        failures.append(
            "ModuleConfig.xml uses conditionalFileInstalls - Amethyst applies "
            "every pattern regardless of its flags, so the installer would "
            "copy more than the picked option"
        )

    steps = root.findall("./installSteps/installStep")
    if len(steps) != 1:
        failures.append("installer has %d steps, want 1" % len(steps))

    sources = []
    names = set()
    for step in steps:
        step_name = step.get("name", "?")
        groups = step.findall("./optionalFileGroups/group")
        if len(groups) != 1:
            failures.append("step %r has %d groups, want 1" % (step_name, len(groups)))
            continue
        group = groups[0]
        if group.get("type") != "SelectExactlyOne":
            failures.append(
                "step %r is %r, want SelectExactlyOne" % (step_name, group.get("type"))
            )

        plugins = group.findall("plugins/plugin")
        if not plugins:
            failures.append("step %r offers no plugins" % step_name)
        for plugin in plugins:
            plugin_name = plugin.get("name", "?")
            if VERSION.search(plugin_name):
                failures.append("plugin name carries a version: %r" % plugin_name)
            if plugin_name in names:
                failures.append("two plugins are called %r" % plugin_name)
            names.add(plugin_name)

            files = plugin.find("files")
            folders = [] if files is None else files.findall("folder")
            if len(folders) != 1:
                failures.append(
                    "plugin %r copies %d folders, want exactly one"
                    % (plugin_name, len(folders))
                )
                continue
            for other in list(files):
                if other.tag != "folder":
                    failures.append(
                        "plugin %r copies a %s, want a folder" % (plugin_name, other.tag)
                    )
            folder = folders[0]
            destination = folder.get("destination", "")
            if destination != mod_set:
                failures.append(
                    "plugin %r copies into %r, want %r"
                    % (plugin_name, destination, mod_set)
                )
            source = folder.get("source", "")
            if source not in variants:
                failures.append(
                    "plugin %r copies %r, which is not a shipped variant"
                    % (plugin_name, source)
                )
            if source in diag:
                failures.append(
                    "plugin %r offers the diagnostic variant %r" % (plugin_name, source)
                )
            sources.append(source)

    if len(sources) != len(set(sources)):
        failures.append("a variant is offered by more than one plugin")

    missing = sorted(set(variants) - set(sources))
    extra = sorted(set(sources) - set(variants))
    if missing:
        failures.append("no plugin offers the shipped variant: %s" % ", ".join(missing))
    if extra:
        failures.append("a plugin offers a variant that is not shipped: %s" % ", ".join(extra))

    return sources


def tree(folder):
    """Yield every file under a folder as a slash separated relative path."""
    for base, _, files in os.walk(folder):
        for name in files:
            full = os.path.join(base, name)
            yield os.path.relpath(full, folder).replace(os.sep, "/"), full


def check_built(source, names, sizes, failures):
    """One offered folder must hold its script and a non-empty EXML."""
    if "%s.lua" % source not in names:
        failures.append("%s: holds no %s.lua" % (source, source))
    exml = [name for name in names if name.lower().endswith(".exml")]
    if not exml:
        failures.append("%s: holds no EXML" % source)
    for name in exml:
        if sizes[name] == 0:
            failures.append("%s: %s is empty" % (source, name))


def check_build(sources, build, mod_set, failures):
    """Every offered folder must have been built."""
    for source in sources:
        folder = os.path.join(build, "%s - %s" % (mod_set, source))
        if not os.path.isdir(folder):
            failures.append("%s: %s was not built" % (source, folder))
            continue
        names = set()
        sizes = {}
        for rel, full in tree(folder):
            names.add(rel)
            sizes[rel] = os.path.getsize(full)
        check_built(source, names, sizes, failures)


def check_archive(sources, archive, mod_set, failures):
    """The packed zip must hold the installer and every offered folder."""
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
    names = {info.filename for info in infos}
    sizes = {info.filename: info.file_size for info in infos}

    if "fomod/ModuleConfig.xml" not in names:
        failures.append("%s: fomod/ModuleConfig.xml is not at the zip root" % archive)

    roots = {name.split("/", 1)[0] for name in names if name}
    for source in sources:
        if source not in roots:
            failures.append("%s: the zip has no %s/ folder" % (archive, source))
            continue
        inner = {
            name[len(source) + 1:]: sizes[name]
            for name in names
            if name.startswith(source + "/")
        }
        check_built(source, inner, inner, failures)

    for root in sorted(roots - {"fomod"} - set(sources)):
        failures.append("%s: the zip ships an unoffered folder %r" % (archive, root))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--mod-set", default="Faster Atlas Interface")
    parser.add_argument("--variants", required=True)
    parser.add_argument("--diag", default="")
    parser.add_argument("--build")
    parser.add_argument("--archive")
    args = parser.parse_args()

    variants = args.variants.split()
    diag = args.diag.split()
    failures = []

    sources = check_config(args.config, args.mod_set, variants, diag, failures)

    if args.build:
        check_build(sources, args.build, args.mod_set, failures)
    if args.archive:
        check_archive(sources, args.archive, args.mod_set, failures)

    if failures:
        for failure in failures:
            print("BAD " + failure, file=sys.stderr)
        return 1

    where = args.archive or args.build
    print(
        "installer: OK (%d options, each one folder, all offered and built, checked against %s)"
        % (len(sources), where)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
