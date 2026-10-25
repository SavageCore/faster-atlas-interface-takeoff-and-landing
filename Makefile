# Faster Atlas Interface
# Builds the FOMOD installer with the AMUMSS Linux port.
#
# What it does: the game flies your ship into and out of the Atlas Interface
# on its own, and ships that flight slow. This raises the speed, in the
# interface's own outpost data and in the shared ship globals.
#
# Every value this mod patches lives in src/patches.tsv. That table drives
# both the rendered script and the verify step, so a value can never be
# patched without also being checked.
#
# Usage:
#   make release      clean rebuild + verify + pack dist/ zip (default)
#   make verify       sanity-check the built outputs and the installer
#   make clean        remove build/ and dist/
#
# Override the AMUMSS install location if needed:
#   make AMUMSS_HOME=/path/to/AMUMSS release
#
# Game-update playbook (see README.md):
#   1. fetch latest MBINCompiler into AMUMSS_HOME
#   2. re-derive the bases in src/patches.tsv (see README.md)
#   3. bump VERSION below (the mod version, published on Nexus)
#   4. make release, import + deploy + test in game

AMUMSS_HOME ?= $(HOME)/AMUMSS
AMUMSS_LINUX ?= $(HOME)/Git/AMUMSS/linux

# The mod version, published as the version of the Nexus release. An
# unreleased build stays at 0.0.0; the first public release bumps this in the
# same commit that publishes it. The version is deliberately not part of the
# mod name: the artifact is named after the mod alone (see FOMOD_ZIP), because
# a mod manager names the installed mod after the archive file name and shows
# the version in a column of its own.
VERSION      := 0.1.0

MOD_SET      := Faster Atlas Interface

SRC_TEMPLATE := src/atlas.lua.in
SRC_TABLE    := src/patches.tsv

BUILD := build
DIST  := dist
STAMP := $(BUILD)/.built

# Installer variants, fastest first, one per combination of phase and speed.
# Each variant label names the rendered script, the CreatedMODS folder, the
# fomod source folder and the in-game MOD_FILENAME suffix, so it must match
# ModuleConfig.xml exactly.
#
# The landing variants scale the steering forces, the approach speed, the
# bounce and the manoeuvre together, which is what keeps the turn into
# alignment in step with the flight through the gate. The takeoff variants
# scale the flight out and the climb together for the same reason.
VARIANT := both-10x landing-10x takeoff-10x both-5x landing-5x takeoff-5x both-2x landing-2x takeoff-2x

# Diagnostics: built and verified like the others, but not offered in the
# installer, so they never reach a player. Each one answers a single question
# in game, and the answers decide what the shipped variants should carry.
#
#   landing-10x-entity   approach only. Does the fly-in speed up, and does the
#                        ship still land upright? If it does, the shipped
#                        landing variants can drop the globals, and the file
#                        conflict with Faster Space Station Landing goes away.
#   landing-10x-globals  globals only. Does the manoeuvre change at the
#                        interface, or is its capture not the shared dock path?
#   landing-10x-descent  approach and descent. The ship drops onto the pad at
#                        5 here, half the station's 10, so the drop may be the
#                        part that reads slow.
#   takeoff-10x-speed    flight out only, against the shipped takeoff-10x,
#                        which also shortens the climb and raises the handover.
#   probe-capture        the capture starts ten times as far out. If that is
#                        visible in the approach but the speed values are not,
#                        this file is live and the flight itself is driven
#                        from somewhere else.
DIAG_VARIANT := landing-10x-entity landing-10x-globals landing-10x-descent takeoff-10x-speed probe-capture

# The variants that get built and verified.
ALL_VARIANT := $(VARIANT) $(DIAG_VARIANT)

# The scopes each variant patches, each with the factor for that group.
SCOPES_both-10x := forces:10,approach:10,bounce:10,manoeuvre:10,takeoff:10,climb:10,handoff:10
SCOPES_both-5x  := forces:5,approach:5,bounce:5,manoeuvre:5,takeoff:5,climb:5,handoff:5
SCOPES_both-2x  := forces:2,approach:2,bounce:2,manoeuvre:2,takeoff:2,climb:2,handoff:2

SCOPES_landing-10x := forces:10,approach:10,bounce:10,manoeuvre:10
SCOPES_landing-5x  := forces:5,approach:5,bounce:5,manoeuvre:5
SCOPES_landing-2x  := forces:2,approach:2,bounce:2,manoeuvre:2

SCOPES_takeoff-10x := takeoff:10,climb:10,handoff:10
SCOPES_takeoff-5x  := takeoff:5,climb:5,handoff:5
SCOPES_takeoff-2x  := takeoff:2,climb:2,handoff:2

SCOPES_landing-10x-entity  := approach:10
SCOPES_landing-10x-globals := forces:10,bounce:10,manoeuvre:10
SCOPES_landing-10x-descent := forces:10,approach:10,descent:10,bounce:10,manoeuvre:10
SCOPES_takeoff-10x-speed   := takeoff:10
SCOPES_probe-capture       := capture:10

DESC_landing-10x     := 10x faster landing
DESC_landing-5x      := 5x faster landing
DESC_landing-2x      := 2x faster landing
DESC_takeoff-10x     := 10x faster takeoff
DESC_takeoff-5x      := 5x faster takeoff
DESC_takeoff-2x      := 2x faster takeoff

DESC_both-10x        := 10x faster landing and takeoff
DESC_both-5x         := 5x faster landing and takeoff
DESC_both-2x         := 2x faster landing and takeoff

DESC_landing-10x-entity  := diagnostic: approach only
DESC_landing-10x-globals := diagnostic: ship globals only
DESC_landing-10x-descent := diagnostic: approach and descent
DESC_takeoff-10x-speed   := diagnostic: flight out only
DESC_probe-capture       := diagnostic: capture range only

RENDERED := $(addprefix $(BUILD)/,$(addsuffix .lua,$(ALL_VARIANT)))
EXPECTED := $(addprefix $(BUILD)/,$(addsuffix .expected.tsv,$(ALL_VARIANT)))

# clean runs before build runs before verify, so release must not be parallel.
.NOTPARALLEL:

.PHONY: all release build verify clean assets video

all: release

# The artifact is named after the mod and nothing else, for the same reason
# the mod name carries no version: the file name is what a mod manager shows
# as the mod name.
FOMOD_ZIP := $(DIST)/$(MOD_SET).zip

release: clean build verify
	@rm -rf "$(BUILD)/fomodz" && mkdir -p "$(BUILD)/fomodz/fomod" $(addprefix "$(BUILD)/fomodz/",$(VARIANT))
	@set -e; for v in $(VARIANT); do cp -a "$(BUILD)/$(MOD_SET) - $$v/." "$(BUILD)/fomodz/$$v/"; done
	@cp ModuleConfig.xml "$(BUILD)/fomodz/fomod/"
	@mkdir -p "$(DIST)" && rm -f "$(FOMOD_ZIP)" && cd "$(BUILD)/fomodz" && zip -qr "$(shell pwd)/$(FOMOD_ZIP)" fomod $(VARIANT)
	@python3 src/verify_installer.py --config ModuleConfig.xml --archive "$(FOMOD_ZIP)" --variants "$(VARIANT)"
	@echo "packed: $(FOMOD_ZIP) (version $(VERSION))"

# Render one variant: the script and the expected values that verify checks
# the built EXML against. The guard turns a typo in VARIANT into a loud
# failure rather than a script with a blank factor.
$(BUILD)/%.lua $(BUILD)/%.expected.tsv: $(SRC_TEMPLATE) $(SRC_TABLE) src/render_mod.py
	@mkdir -p "$(BUILD)"
	@test -n "$(SCOPES_$*)" -a -n "$(DESC_$*)" || { echo "ERROR: unknown variant '$*' - add SCOPES_$* and DESC_$* to the Makefile" >&2; exit 1; }
	@python3 src/render_mod.py --variant "$*" --factor 1 --desc "$(DESC_$*)" --scopes "$(SCOPES_$*)" \
		--template "$(SRC_TEMPLATE)" --table "$(SRC_TABLE)" \
		--out-script "$(BUILD)/$*.lua" --out-expected "$(BUILD)/$*.expected.tsv"

# One pipeline run builds every variant as an individual mod.
build: $(RENDERED)
	@test -d "$(AMUMSS_HOME)/MODBUILDER" || (echo "ERROR: no AMUMSS install at $(AMUMSS_HOME) (set AMUMSS_HOME=...)" >&2; exit 1)
	@test -x "$(AMUMSS_HOME)/MODBUILDER/MBINCompiler-linux" || (echo "ERROR: run $(AMUMSS_LINUX)/scripts/fetch_mbincompiler.sh with AMUMSS_HOME=$(AMUMSS_HOME) first" >&2; exit 1)
	@mkdir -p "$(BUILD)"
	@set -e; \
	if [ -d "$(AMUMSS_HOME)/ModScript" ]; then mv "$(AMUMSS_HOME)/ModScript" "$(AMUMSS_HOME)/ModScript.makebak"; trap 'rm -rf "$(AMUMSS_HOME)/ModScript"; mv "$(AMUMSS_HOME)/ModScript.makebak" "$(AMUMSS_HOME)/ModScript"' EXIT; fi; \
	mkdir -p "$(AMUMSS_HOME)/ModScript"; \
	cp $(RENDERED) "$(AMUMSS_HOME)/ModScript/"; \
	for v in $(ALL_VARIANT); do rm -rf "$(AMUMSS_HOME)/CreatedMODS/$(MOD_SET) - $$v"; done; \
	AMUMSS_HOME="$(AMUMSS_HOME)" "$(AMUMSS_LINUX)/buildmod.sh" --run-pipeline; \
	rm -rf "$(AMUMSS_HOME)/ModScript"; \
	if [ -d "$(AMUMSS_HOME)/ModScript.makebak" ]; then mv "$(AMUMSS_HOME)/ModScript.makebak" "$(AMUMSS_HOME)/ModScript"; fi; \
	trap - EXIT
	@set -e; for v in $(ALL_VARIANT); do \
		rm -rf "$(BUILD)/$(MOD_SET) - $$v"; \
		mkdir -p "$(BUILD)/$(MOD_SET) - $$v"; \
		cp -a "$(AMUMSS_HOME)/CreatedMODS/$(MOD_SET) - $$v"/* "$(BUILD)/$(MOD_SET) - $$v/"; \
	done
	@touch "$(STAMP)"
	@echo "built: $(foreach v,$(ALL_VARIANT),$(BUILD)/$(MOD_SET) - $(v) )"

# verify_build.py checks the built EXML against the rendered table.
# verify_installer.py checks that ModuleConfig.xml offers exactly the shipped
# variants, one folder per plugin, and that every offered folder was built.
# It also rejects conditional file installs: Amethyst applies every pattern in
# one regardless of the flags, which installed all nine variants at once.
verify: build
	@for n in "$$(sed -n 's:.*<moduleName>\(.*\)</moduleName>.*:\1:p' ModuleConfig.xml)" "$(MOD_SET)"; do \
		if printf '%s' "$$n" | grep -qE '[vV]?[0-9]+(\.[0-9]+)+'; then \
			echo "ERROR: the mod name must not carry a version: '$$n'" >&2; exit 1; \
		fi; \
	done
	@python3 src/verify_build.py --build "$(BUILD)" --mod-set "$(MOD_SET)" --variants "$(ALL_VARIANT)"
	@python3 src/verify_installer.py --config ModuleConfig.xml --build "$(BUILD)" --mod-set "$(MOD_SET)" --variants "$(VARIANT)" --diag "$(DIAG_VARIANT)"

# Nexus page images from the source screenshot in assets/src. The generated
# images are build artifacts and are not tracked; the screenshot and the
# typeface are.
assets: assets/src/gallery-atlas-interface.jpg assets/generate.py
	python3 assets/generate.py

# The demo video, joined from the recordings in assets/. The generated videos
# are build artifacts and are not tracked.
video:
	python3 assets/combine.py
	python3 assets/combine.py --web

clean:
	rm -rf "$(BUILD)" "$(DIST)"
