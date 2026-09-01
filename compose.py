#!/usr/bin/env python3
"""
reel-composer — template-driven batch video compositing on ffmpeg.

Drop numbered assets in a folder, pick a template, get finished verticals.

    python compose.py --template tweet-clip --input input/ --out out/ --prefix memehut

Reads m1.mp4/t1.png/... from --input, composites each per the template,
writes memehut1.mp4 ... memehutN.mp4 to --out.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


# ----------------------------------------------------------------- ffprobe

def probe(path, streams="v:0"):
    """Return (width, height, duration) for a media file."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", streams,
         "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    st = d.get("streams", [{}])[0]
    dur = float(d.get("format", {}).get("duration", 0) or 0)
    return int(st.get("width", 0)), int(st.get("height", 0)), dur


def detect_crop(path, probe_seconds=6):
    """Auto-detect letterbox/pillarbox borders. Returns 'w:h:x:y' or None.

    Samples the middle of the clip — the first seconds are often a fade from
    black, which cropdetect happily reads as a giant letterbox.
    """
    _, _, dur = probe(path)
    start = max(0, dur / 2 - probe_seconds / 2)
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(probe_seconds),
         "-i", str(path), "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
        capture_output=True, text=True)
    matches = re.findall(r"crop=(\d+:\d+:\d+:\d+)", proc.stderr)
    if not matches:
        return None
    # last detection is the most settled
    return matches[-1]


# ----------------------------------------------------------------- template

def load_template(name):
    for ext in (".yaml", ".yml", ".json"):
        p = Path("templates") / f"{name}{ext}"
        if p.exists():
            text = p.read_text()
            if ext == ".json":
                return json.loads(text)
            if yaml is None:
                sys.exit("PyYAML not installed and template is YAML. "
                         "pip install pyyaml, or use a .json template.")
            return yaml.safe_load(text)
    sys.exit(f"No template named '{name}' in templates/")


def resolve_y(spec, resolved, canvas_h, own_h):
    """y may be an int, 'center', or 'below:<layer_id>+<gap>'."""
    if isinstance(spec, int):
        return spec
    if spec == "center":
        return (canvas_h - own_h) // 2
    m = re.match(r"below:(\w+)(?:\s*\+\s*(\d+))?", str(spec))
    if m:
        ref, gap = m.group(1), int(m.group(2) or 0)
        if ref not in resolved:
            sys.exit(f"Layer '{ref}' referenced before it is placed")
        return resolved[ref]["y"] + resolved[ref]["h"] + gap
    sys.exit(f"Cannot parse y: {spec!r}")


def resolve_x(spec, canvas_w, own_w):
    if isinstance(spec, int):
        return spec
    if spec == "center":
        return (canvas_w - own_w) // 2
    sys.exit(f"Cannot parse x: {spec!r}")


def esc(text):
    """Escape a string for ffmpeg drawtext."""
    return (text.replace("\\", "\\\\").replace(":", r"\:")
                .replace("'", r"\'").replace("%", r"\%"))


# ----------------------------------------------------------------- compose

def compose(tpl, index, input_dir, out_dir, prefix, caption, dry_run=False):
    canvas = tpl["canvas"]
    cw, ch = canvas["width"], canvas["height"]
    bg = canvas.get("background", "#FFFFFF").lstrip("#")

    inputs, filters, resolved = [], [], {}
    audio_from = None               # ffmpeg input index of the first audio-bearing clip
    duration = None
    base = f"color=c=0x{bg}:s={cw}x{ch}:r={tpl.get('output', {}).get('fps', 30)}"
    filters.append(f"{base}[canvas]")
    current = "canvas"

    for i, layer in enumerate(tpl["layers"]):
        ltype = layer["type"]
        lid = layer.get("id", f"L{i}")

        # ---- text layers draw straight onto the running canvas
        if ltype == "text":
            content = layer["content"].replace("{caption}", caption or "")
            if not content.strip():
                continue
            opts = [f"text='{esc(content)}'",
                    f"fontsize={layer.get('size', 44)}",
                    f"fontcolor={layer.get('color', 'black')}",
                    f"x={'(w-text_w)/2' if layer.get('x') == 'center' else layer.get('x', 0)}",
                    f"y={layer.get('y', 0)}"]
            if layer.get("font"):
                opts.append(f"fontfile='{layer['font']}'")
            if layer.get("line_spacing"):
                opts.append(f"line_spacing={layer['line_spacing']}")
            filters.append(f"[{current}]drawtext={':'.join(opts)}[v{i}]")
            current = f"v{i}"
            continue

        # ---- media layers become ffmpeg inputs
        src = layer["source"].replace("{n}", str(index))
        path = Path(src) if Path(src).exists() else Path(input_dir) / src
        if not path.exists():
            if layer.get("optional"):
                continue
            sys.exit(f"Missing asset for layer '{lid}': {path}")

        idx = len(inputs) // 2          # inputs holds ["-i", path] pairs
        if ltype == "image":
            inputs += ["-i", str(path)]
        elif ltype == "video":
            inputs += ["-i", str(path)]
        else:
            sys.exit(f"Unknown layer type: {ltype}")

        sw, sh, sdur = probe(path)
        chain = f"[{idx}:v]"

        if ltype == "video":
            if layer.get("crop") == "auto":
                c = detect_crop(path)
                if c:
                    chain += f"crop={c},"
                    cwid, chgt = (int(x) for x in c.split(":")[:2])
                    sw, sh = cwid, chgt
            elif isinstance(layer.get("crop"), str):
                chain += f"crop={layer['crop']},"
                cwid, chgt = (int(x) for x in layer["crop"].split(":")[:2])
                sw, sh = cwid, chgt
            duration = sdur if duration is None else min(duration, sdur)
            if layer.get("audio", True) and audio_from is None:
                audio_from = idx

        target_w = layer.get("width", sw)
        target_h = round(sh * target_w / sw)
        chain += f"scale={target_w}:{target_h}[s{i}]"
        filters.append(chain)

        y = resolve_y(layer.get("y", 0), resolved, ch, target_h)
        x = resolve_x(layer.get("x", 0), cw, target_w)
        resolved[lid] = {"x": x, "y": y, "w": target_w, "h": target_h}

        eof = ":shortest=0" if ltype == "image" else ""
        filters.append(f"[{current}][s{i}]overlay={x}:{y}{eof}[v{i}]")
        current = f"v{i}"

    if duration is None:
        sys.exit("Template has no video layer — nothing sets the duration.")

    out_cfg = tpl.get("output", {})
    name = out_cfg.get("name", "{prefix}{n}.mp4") \
        .replace("{prefix}", prefix or "out").replace("{n}", str(index))
    out_path = Path(out_dir) / name

    cmd = (["ffmpeg", "-y"] + inputs +
           ["-filter_complex", ";".join(filters),
            "-map", f"[{current}]"])
    # carry audio from the first video layer that declares it
    if audio_from is not None:
        cmd += ["-map", f"{audio_from}:a?", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", out_cfg.get("preset", "medium"),
            "-crf", str(out_cfg.get("crf", 20)),
            "-pix_fmt", "yuv420p", str(out_path)]

    if dry_run:
        print(" ".join(cmd))
        return out_path

    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


# ----------------------------------------------------------------- cli

def discover_indices(input_dir, tpl):
    """Find every n for which the template's required assets all exist."""
    pattern_layer = next((l for l in tpl["layers"]
                          if l["type"] == "video" and "{n}" in l.get("source", "")), None)
    if not pattern_layer:
        sys.exit("Template has no numbered video layer to iterate over.")
    rx = re.compile(re.escape(pattern_layer["source"]).replace(r"\{n\}", r"(\d+)") + "$")
    found = []
    for f in Path(input_dir).iterdir():
        m = rx.match(f.name)
        if m:
            found.append(int(m.group(1)))
    return sorted(found)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True, help="template name in templates/")
    ap.add_argument("--input", default="input", help="folder of numbered assets")
    ap.add_argument("--out", default="out", help="output folder")
    ap.add_argument("--prefix", default="out", help="output filename prefix")
    ap.add_argument("--captions", help="text file, one caption per line, line N -> asset N")
    ap.add_argument("--only", help="comma-separated indices, e.g. 3,7,9")
    ap.add_argument("--dry-run", action="store_true", help="print ffmpeg commands, run nothing")
    a = ap.parse_args()

    tpl = load_template(a.template)
    Path(a.out).mkdir(parents=True, exist_ok=True)

    captions = []
    if a.captions:
        captions = Path(a.captions).read_text().splitlines()

    indices = ([int(x) for x in a.only.split(",")] if a.only
               else discover_indices(a.input, tpl))
    if not indices:
        sys.exit(f"No numbered assets found in {a.input}/")

    print(f"{len(indices)} to compose with template '{a.template}'\n")
    ok = 0
    for n in indices:
        cap = captions[n - 1] if len(captions) >= n else ""
        try:
            path = compose(tpl, n, a.input, a.out, a.prefix, cap, a.dry_run)
            print(f"  [{n:>3}] {path}")
            ok += 1
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode()[-400:] if isinstance(e.stderr, bytes) else str(e.stderr)[-400:]
            print(f"  [{n:>3}] FAILED\n{err}\n", file=sys.stderr)
        except SystemExit as e:
            print(f"  [{n:>3}] {e}", file=sys.stderr)

    print(f"\n{ok}/{len(indices)} composed → {a.out}/")


if __name__ == "__main__":
    main()
