#!/usr/bin/env python3
"""Join the Atlas Interface recordings into one comparison video.

The recordings live next to this script, one per phase and speed:

    <speed> - Landing.mp4   the ship captured through the gate
    <speed> - Takeoff.mp4   the ship leaving the interface

The output holds every pair, slowest speed first, landing before takeoff in
each pair. Each segment is labelled with its phase and speed and carries a
timer that runs from the frame the game takes the ship over to the frame the
ship is down, or from the frame the ship leaves the pad to the frame the
player gets control back.

Both ends of each timer are found automatically, and the two phases use
different signals.

A landing starts on the frame the game prints the landing message across the
screen. The message is white text on a dark background, so the band that
carries it is scanned for the number of bright runs: glyphs make hundreds of
runs, a lit wall makes a few. The message fades in, so the timer starts once
the text has faded halfway in, which is the same point in every recording.
It ends on the cut to black once the ship is down and the pilot is put out.

A takeoff starts on the frame the console stops saying the ignition has
started, which is when the ship leaves the pad. It ends on the frame the
scripted flight stops driving the ship: the flight moves most of the screen
every frame, and once control is back the ship coasts and the picture barely
changes.

The video is re-encoded losslessly, so the result is bit identical to the
recordings apart from the overlay. The audio is re-encoded, because the
segments have to be joined and the sources are AAC.

Usage:
    python3 assets/combine.py            # lossless master
    python3 assets/combine.py --web      # browser friendly instead
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "fonts", "GeosansLight-NMS.ttf")
OUT_DIR = os.path.join(HERE, "video")

# The pairs, slowest speed first.
SPEEDS = ["2x", "5x", "10x"]
CASES = [("Landing", "LANDING"), ("Takeoff", "TAKEOFF")]

FPS = 60
WIDTH, HEIGHT = 2560, 1440

# The band of the screen that carries the landing message, and how the
# message is told apart from the scene behind it.
TEXT_X, TEXT_Y, TEXT_W, TEXT_H = 1090, 381, 378, 18
TEXT_LEVEL = 200  # the text is white, the interface is not that bright
TEXT_FADE = 0.5  # the timer starts when the text has faded this far in
TEXT_HOLD = 30  # frames the message has to stay up to count as shown

# The screen is black once the landing has ended and the pilot is put out.
DARK_LEVEL = 2.0
DARK_HOLD = 3

# The centre console, where the game prints the ignition message while the
# ship is still on the pad.
CONSOLE_X, CONSOLE_Y, CONSOLE_W, CONSOLE_H = 1120, 1075, 320, 30
CONSOLE_LEVEL = 150  # the text is white, the console is not
CONSOLE_TEXT = 1000  # bright pixels that mean the message is up
CONSOLE_DARK = 200  # bright pixels that mean the console is empty
CONSOLE_HOLD = 12  # frames the console has to stay empty to count

# How much of the picture changes between one frame and the next. The
# scripted flight moves most of the screen; coasting on your own does not.
# The Atlas flight crosses dark space, so it moves fewer pixels than the
# bright station interior (which uses 15000 for the same test).
MOTION_W, MOTION_H = 640, 360
MOTION_LEVEL = 10  # how far a pixel has to move to count as changed
MOTION_FLIGHT = 2000  # changed pixels that mean the ship is being flown
MOTION_HOLD = 12  # frames the picture has to hold still to count

# Overlay layout.
SPEED_X, SPEED_Y, SPEED_SIZE = 60, 44, 72
CASE_X, CASE_Y, CASE_SIZE = 64, 140, 30
TIMER_X, TIMER_Y, TIMER_SIZE = 64, 190, 52
TIMER_W = 119  # the width of "00.00" at the timer size
UNIT_SIZE = 32
AMBER = "0xFFC878"
WHITE = "0xFFFFFF"
GREY = "0x9AA0A6"
EDGE = "borderw=2:bordercolor=0x000000@0.8"


def run(cmd):
    """Run a command, raising with its output on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("%s failed:\n%s" % (" ".join(cmd[:3]), proc.stderr[-4000:]))
    return proc.stdout


def frame_count(clip):
    """Return the number of frames a recording holds."""
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
               "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", clip])
    return int(out.strip().split(",")[0])


def decode(clip, vf, width, height):
    """Decode a clip to raw greyscale frames of the given size.

    Every frame the file holds is passed through, so the frame numbers here
    are the frame numbers of the recording.
    """
    cmd = ["ffmpeg", "-v", "error", "-i", clip, "-vf", vf,
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit("ffmpeg failed on %s:\n%s" % (clip, proc.stderr[-2000:]))
    data = proc.stdout
    frame = width * height
    return [data[i * frame:(i + 1) * frame] for i in range(len(data) // frame)]


def text_runs(frame):
    """Count the bright runs in a band of the landing message.

    A line of glyphs breaks into many runs, a lit wall into a few.
    """
    runs = 0
    for y in range(TEXT_H):
        row = frame[y * TEXT_W:(y + 1) * TEXT_W]
        previous = False
        for value in row:
            bright = value > TEXT_LEVEL
            if bright and not previous:
                runs += 1
            previous = bright
    return runs


def find_takeover(clip):
    """Return the frame the game takes the ship over on, or None."""
    frames = decode(clip, "crop=%d:%d:%d:%d" % (TEXT_W, TEXT_H, TEXT_X, TEXT_Y),
                    TEXT_W, TEXT_H)
    counts = [text_runs(f) for f in frames]
    if not counts:
        return None

    # The message sits at full strength for most of the clip, so the top of
    # the counts is the text and half of it is the text half faded in.
    top = sorted(counts, reverse=True)[:max(1, len(counts) // 5)]
    threshold = sorted(top)[len(top) // 2] * TEXT_FADE

    for i in range(len(counts) - TEXT_HOLD):
        if all(c >= threshold for c in counts[i:i + TEXT_HOLD]):
            return i
    return None


def find_down(clip):
    """Return the frame the ship is down on, or None."""
    width, height = 320, 180
    frames = decode(clip, "scale=%d:%d" % (width, height), width, height)
    levels = [sum(f) / float(len(f)) for f in frames]
    for i in range(len(levels) - DARK_HOLD):
        if all(v < DARK_LEVEL for v in levels[i:i + DARK_HOLD]):
            return i
    return None


def find_liftoff(clip):
    """Return the frame the ship leaves the pad on, or None."""
    frames = decode(clip, "crop=%d:%d:%d:%d" % (CONSOLE_W, CONSOLE_H, CONSOLE_X, CONSOLE_Y),
                    CONSOLE_W, CONSOLE_H)
    counts = [sum(1 for v in f if v > CONSOLE_LEVEL) for f in frames]
    if not counts:
        return None

    up = next((i for i, c in enumerate(counts) if c > CONSOLE_TEXT), None)
    if up is None:
        return None
    for i in range(up + 1, len(counts) - CONSOLE_HOLD):
        if counts[i] < CONSOLE_DARK and all(c < CONSOLE_DARK for c in counts[i:i + CONSOLE_HOLD]):
            return i
    return None


def find_handover(clip, liftoff):
    """Return the frame the player gets control back on, or None.

    The search starts at the lift-off, because before it the ship is still
    on the pad and the picture is just as still as it is after the flight.
    """
    frames = decode(clip, "scale=%d:%d" % (MOTION_W, MOTION_H), MOTION_W, MOTION_H)
    motion = [0]
    for i in range(1, len(frames)):
        motion.append(sum(1 for a, b in zip(frames[i - 1], frames[i])
                          if abs(a - b) > MOTION_LEVEL))
    for i in range(liftoff, len(motion) - MOTION_HOLD):
        if all(v < MOTION_FLIGHT for v in motion[i:i + MOTION_HOLD]):
            return i
    return None


def timer_text(start, end):
    """The drawtext text that shows the elapsed time as SS.hh."""
    span = end - start
    elapsed = "(min(max(t-%.6f,0),%.6f))" % (start, span)
    hundredths = "(floor(%s*100+0.5))" % elapsed
    return (
        "%{eif\\:floor(" + hundredths + "/1000)\\:d}"
        "%{eif\\:mod(floor(" + hundredths + "/100)\\,10)\\:d}."
        "%{eif\\:floor(mod(" + hundredths + "\\,100)/10)\\:d}"
        "%{eif\\:mod(" + hundredths + "\\,10)\\:d}"
    )


def draw(text, x, y, size, colour, enable=None):
    """A drawtext that draws the given text in the game's font."""
    opts = ["fontfile=%s" % FONT, "text='%s'" % text,
            "x=%s" % x, "y=%d" % y, "fontsize=%d" % size,
            "fontcolor=%s" % colour, EDGE]
    if enable:
        opts.append("enable='%s'" % enable)
    return "drawtext=" + ":".join(opts)


def build_graph(segments):
    """Build the filter graph for the segments."""
    lines = []
    for index, segment in enumerate(segments):
        start = segment["start"]
        end = segment["end"]
        # The timer only runs once the game has taken the ship over.
        after = "gte(t,%.6f)" % start

        parts = [
            draw(segment["speed"], SPEED_X, SPEED_Y, SPEED_SIZE, AMBER),
            draw(segment["label"], CASE_X, CASE_Y, CASE_SIZE, WHITE),
            draw(timer_text(start, end), TIMER_X, TIMER_Y, TIMER_SIZE, WHITE, after),
            draw("s", TIMER_X + TIMER_W + 12, TIMER_Y + 16, UNIT_SIZE, GREY, after),
        ]
        # The frames are put back on a plain 60 fps timeline so that the
        # timer counts seconds and not the jitter of the recording.
        lines.append("[%d:v]setpts=N/(%d*TB),scale=%d:%d,setsar=1,%s[v%d];"
                     % (index, FPS, WIDTH, HEIGHT, ",".join(parts), index))
        lines.append("[%d:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     "apad,atrim=end=%.6f,asetpts=N/SR/TB[a%d];"
                     % (index, segment["frames"] / float(FPS), index))
    chains = "".join("[v%d][a%d]" % (i, i) for i in range(len(segments)))
    lines.append("%sconcat=n=%d:v=1:a=1[outv][outa]" % (chains, len(segments)))
    return "\n".join(lines)


def find_bounds(clip, case):
    """Return the start and end frame of the scripted sequence in a clip."""
    if case == "Landing":
        start = find_takeover(clip)
        end = find_down(clip)
        return start, end, "takeover", "down"
    start = find_liftoff(clip)
    end = find_handover(clip, start) if start is not None else None
    return start, end, "off the pad", "control back"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", action="store_true",
                        help="encode for the web instead of losslessly")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.out is None:
        name = ("atlas-interface-comparison-web.mp4" if args.web
                else "atlas-interface-comparison-lossless.mp4")
        args.out = os.path.join(OUT_DIR, name)

    segments = []
    for speed in SPEEDS:
        for case, label in CASES:
            clip = os.path.join(HERE, "%s - %s.mp4" % (speed, case))
            if not os.path.isfile(clip):
                raise SystemExit("missing recording: %s" % clip)
            start, end, start_name, end_name = find_bounds(clip, case)
            if start is None or end is None:
                raise SystemExit("could not find the %s sequence in %s" % (case.lower(), clip))
            segments.append({
                "clip": clip,
                "label": label,
                "speed": speed,
                "frames": frame_count(clip),
                "start": start / float(FPS),
                "end": end / float(FPS),
            })
            print("%-34s %s %4.2f s, %s %4.2f s, %s %4.2f s"
                  % (os.path.basename(clip), start_name, start / float(FPS),
                     end_name, end / float(FPS), case.lower(),
                     (end - start) / float(FPS)))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    graph = os.path.join(OUT_DIR, "filtergraph.txt")
    with open(graph, "w", encoding="utf-8") as handle:
        handle.write(build_graph(segments))

    cmd = ["ffmpeg", "-y", "-v", "error", "-vsync", "0"]
    for segment in segments:
        cmd += ["-i", segment["clip"]]
    cmd += ["-filter_complex_script", graph, "-map", "[outv]", "-map", "[outa]"]
    if args.web:
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-c:v", "libx264", "-qp", "0", "-preset", "medium", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", args.out]
    run(cmd)

    size = os.path.getsize(args.out)
    print("wrote %s (%.1f MB, %s)" % (args.out, size / 1048576.0,
                                       "web" if args.web else "lossless"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
