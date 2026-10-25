# Faster Atlas Interface

Speeds up the scripted flight that carries your ship into the Atlas Interface
and back out again. Built natively on Linux with the
[AMUMSS Linux port](https://github.com/SavageCore/AMUMSS/tree/feat/linux-support).

## Usage

Install it and pick one of the nine options.

| Option | What it does |
| --- | --- |
| `10x - landing and takeoff` | the default, and the fastest |
| `10x - landing only` | capture sped up, departure left as the game ships it |
| `10x - takeoff only` | departure sped up, capture left as the game ships it |
| `5x - ...` | the same three choices at five times |
| `2x - ...` | the same three choices at twice |

Each option is one self-contained patch of the same files at one factor, so
what you pick is exactly what is installed. The factor is applied to every
base value in `src/patches.tsv` for the phase you picked, so one number scales
the whole sequence. 10x is the ceiling: past that the ship no longer flies the
sequence right.

One option per install is deliberate. Picking a phase and then a speed on
separate pages needs a conditional file install, where the picked flags decide
what is copied, and Amethyst applies every one of those patterns regardless of
the flags. That installs all nine variants over each other, and the mod ends
up with whichever files were written last rather than the ones you chose.

It cannot remove the sequence itself, only compress it. The capture, the
manoeuvre that turns the ship upright and the handover at the end all still
happen.

## What it patches

The Atlas Interface keeps its whole sequence in one outpost component, unlike
the space stations, which split it across a dock node and six location
entities. So the approach, the landing and the departure all come from
`AtlasStation.Entity.MBIN`.

| Part | Where | What it governs |
| --- | --- | --- |
| the flight in | `ApproachSpeed` in the interface entity | how fast the ship flies through the gate to the pad |
| the turn | `OutpostDock*Force` in `GCAISPACESHIPGLOBALS` | how fast the ship turns into alignment on the way in |
| the manoeuvre | the `DockingLandingTime`, `DockingRotateStartTime` and `LandingManuevre*` values | how long the ship spends lining up with the pad |
| the touchdown | the `DockingSpringTime` and `DockingLandingBounce*` values | how long the ship takes to settle onto the pad |
| the flight out | `TakeOffSpeed` and `TakeOffBoost` | how fast the ship flies out of the gate, and how fast it boosts on the way |
| the climb | `TakeOffTime` and `TakeOffAlignTime` | how long the ship spends rising off the pad and turning to face out |
| the handover | `PostTakeOffExtraPlayerSpeed` | how fast the ship is going when you get control back |

The flight and the turn are scaled together, which is what keeps the parts in
step. The ship lines up with the pad in a manoeuvre of fixed length, so a
faster flight only stays upright if the manoeuvre is shortened by the same
factor. Speeding up the flight alone leaves the ship arriving at the pad while
it is still turning, and it lands upside down.

The departure is scaled the same way: the flight out and the climb move
together so the ship keeps turning while it flies and leaves the way it
should.

Two things are left alone on purpose. The descent speed, because a faster
descent shortens the same window the manoeuvre has to fit in. And the tip
geometry, because raising the length of the tip or the angle the ship may tip
up to makes it fly on past the pad and over rotate.

Every value lives in `src/patches.tsv`, which is also what `make verify`
checks the build against. A value cannot be patched without also being
checked, and the two cannot drift apart.

The interface files the game ships:

| Value | Atlas Interface | Space station |
| --- | --- | --- |
| `ApproachSpeed` | 250 | 300 |
| `LandingSpeed` | 5 | 10 |
| `TakeOffSpeed` | 200 | 500 |
| `TakeOffBoost` | 100 | 120 |

## Compatibility

Modifies `AtlasStation.Entity.MBIN` and `GCAISPACESHIPGLOBALS.GLOBAL.MBIN`.
Nothing else.

The forces, the manoeuvre and the touchdown times are shared ship settings,
so the landing half carries the same `GCAISPACESHIPGLOBALS` changes as
Faster Space Station Landing.
Install both at the same factor and the two agree value for value. At
different factors the file the game loads last wins for both mods, so pick one
factor across the pair. If you only want the departure compressed, choose
`Takeoff only` and the mod does not touch the globals at all.

It does not patch the six dock entities of the space stations or the anomaly,
so it shares no file with Faster Space Station Landing or
Faster Space Station Takeoff,
and the station traffic those mods speed up is left to them.

The docking rotation is a different phase again, and that knob belongs to
[Faster Spaceship Docking Rotation Reloaded](https://www.nexusmods.com/nomanssky/mods/4569).
That mod writes `GCSPACESHIPGLOBALS.GLOBAL.MBIN`; this one never does, so the
two have no file in common.

The entity file lives in `NMSARC.Precache.pak`, the globals file in
`NMSARC.globals.pak`.

## Build (on Linux)

Requires a full AMUMSS install at `~/AMUMSS` (override with
`AMUMSS_HOME=...`) with `MBINCompiler-linux` fetched
(`linux/scripts/fetch_mbincompiler.sh` in the AMUMSS repo).

```sh
make release      # clean rebuild + verify + pack dist/ zip (default)
make verify       # sanity-check the built outputs and the installer
make clean        # remove build/ and dist/

make assets       # regenerate the Nexus page images
make video        # join the demo recordings
```

`make build` clears this mod's folders out of
`$(AMUMSS_HOME)/CreatedMODS`, temporarily stages the variant scripts into
`$(AMUMSS_HOME)/ModScript` (existing content moved aside and restored), runs one
`buildmod.sh --run-pipeline`, and collects the outputs.

`make assets` rebuilds the Nexus page images from the source screenshot in
`assets/src`. The generated images are build artifacts and are not tracked;
the screenshot and the typeface are.

### The demo video

`assets/combine.py` joins the six recordings in `assets/` into one video with
the phase and the speed labelled on every segment, and a timer per segment
that runs from the moment the game takes the ship over to the moment it is
down, or from the moment the ship leaves the pad to the moment the player gets
control back.

```sh
python3 assets/combine.py            # lossless master, 2560x1440, a couple of GB
python3 assets/combine.py --web      # browser friendly, crf 18
```

Both ends of the timer are found in the footage rather than by hand. A landing
starts on the frame the game prints the landing message and ends on the cut to
black once the ship is down. A takeoff starts when the centre console stops
saying the ignition has started, once the ship has left the pad, and ends on
the frame the scripted flight stops driving the ship: the flight moves most of
the screen every frame, and once control is back the ship coasts and the
picture barely changes.

The video is re-encoded losslessly by default, so it is bit identical to the
recordings apart from the overlay. The audio is re-encoded, because the
segments have to be joined and the sources are AAC.

### `make verify` is the load-bearing step

For every variant and every patched file it asserts that the EXML was
produced by *this* run, that each expected property carries the expected
value, that the patch touches nothing else, and that there are no marker
tags.

The freshness check exists because of how AMUMSS fails: a change that stops
matching does not error, it silently applies nothing, creates no file, and
leaves the previous build's file sitting in `CreatedMODS`. The copy then
succeeds and every other check happily validates last week's output.

The installer is verified the same way. Each option copies one folder, and
`make verify` parses `ModuleConfig.xml` and asserts that every plugin copies
exactly one folder into the one mod folder, that every plugin's folder is a
shipped variant, that every shipped variant is offered once, that no
diagnostic variant is offered, and that every offered folder was built with
its script and an EXML in it. The packed zip is checked against the same list.
A conditional file install is rejected outright, for the reason in the
installer section above.

## Release

`make release` creates `dist/Faster Atlas Interface.zip`. It is a FOMOD
installer: `fomod/` sits at the zip root, which is how mod managers detect an
installer, and each option is a folder beside it. Import it into
[Amethyst](https://github.com/ChrisDKN/Amethyst-Mod-Manager)/[Vortex](https://github.com/Nexus-Mods/Vortex)
or upload it to Nexus.

The zip is named after the mod and carries no version, because a mod manager
names the installed mod after the archive file name and shows the version in a
column of its own. The version travels as the version of the Nexus release
instead.

## Game updates / versioning

The mod version is `VERSION` in the `Makefile`. The game version the script
targets is `GameVersion` in `src/atlas.lua.in`.

When No Man's Sky updates:

1. Fetch the new matching compiler from the AMUMSS repo (use
   `MBINCOMPILER_TAG=vX` to pin):
   `AMUMSS_HOME=~/AMUMSS linux/scripts/fetch_mbincompiler.sh`
   If the AMUMSS core itself changed, re-run the pipeline once so the
   linux patches re-verify (`apply_linux_patches.sh --verify`).
2. Re-derive the bases in `src/patches.tsv` (see below).
3. Bump `GameVersion` in `src/atlas.lua.in` and `VERSION` in the `Makefile`.
4. `make release`, install, test.

### Re-deriving the bases

The base values are game data, not constants this mod owns. To re-derive them:

```sh
PAK=~/.local/share/Steam/steamapps/common/"No Man's Sky"/GAMEDATA/PCBANKS/NMSARC.Precache.pak
hgpaktool -O /tmp/probe -f "*atlasstation/shared/entities/*" "$PAK"

GLOBALS=~/.local/share/Steam/steamapps/common/"No Man's Sky"/GAMEDATA/PCBANKS/NMSARC.globals.pak
hgpaktool -O /tmp/probe -f "GCAISPACESHIPGLOBALS.GLOBAL.MBIN" "$GLOBALS"
```

Then decompile each MBIN with `MBINCompiler-linux` and read the values in
`GcOutpostComponentData` in `AtlasStation.Entity.MBIN`, and the
`OutpostDock*Force`, `Docking*` and `LandingManuevre*` values in the shared
ship globals. Update the `BASE` column in `src/patches.tsv` to match. If a
property is renamed, `make verify` fails on the missing property rather than
shipping a patch that does nothing.
