# reel-composer

**Templates for video. Drop numbered assets in a folder, get finished verticals out.**

An ffmpeg compositing pipeline where the layout lives in a YAML template instead of in the
script. Change where the logo sits by editing four lines — not by rewriting a filter graph.

Built for running clip-repost pages at volume, where the format is fixed and the only thing that
changes is which clip goes in it.

---

## The idea

Every batch video tool starts as one hardcoded ffmpeg command and dies the first time you want a
second format. This splits the two apart:

```
templates/tweet-clip.yaml   ← the format: canvas, layers, positions, output settings
input/m1.mp4  t1.png        ← the assets: numbered, one number per output
compose.py                  ← the engine: knows nothing about your format
```

```bash
python compose.py --template tweet-clip --prefix memehut
```

```
input/m1.mp4 + t1.png  →  out/memehut1.mp4
input/m2.mp4 + t2.png  →  out/memehut2.mp4
...
```

## What a template looks like

```yaml
name: tweet-clip
canvas:
  width: 1080
  height: 1920
  background: "#FFFFFF"

layers:
  - type: image
    id: tweet
    source: "t{n}.png"
    width: 940
    x: center
    y: 300

  - type: video
    id: clip
    source: "m{n}.mp4"
    crop: auto              # letterbox detected and stripped
    width: 1080
    x: center
    y: "below:tweet+40"     # stacks under the layer above it

  - type: image
    id: logo
    source: "assets/logo.png"
    width: 190
    x: center
    y: 1760
    optional: true          # skipped silently if absent

output:
  name: "{prefix}{n}.mp4"
  fps: 30
  crf: 20
```

Three layer types — `image`, `video`, `text` — composited in order, bottom to top.

| Feature | What it does |
|---|---|
| `crop: auto` | Runs cropdetect on the middle of the clip and strips baked-in letterboxing. Samples the middle deliberately: opening fades read as a full-frame letterbox and will eat your video |
| `y: "below:<id>+gap"` | Positions relative to another layer's resolved height, so a taller tweet card pushes the clip down instead of overlapping it |
| `x: center` / `y: center` | Resolved against the actual scaled dimensions, not guessed |
| `optional: true` | Missing asset skips the layer instead of failing the batch |
| `{caption}` in a text layer | Pulled from `--captions hooks.txt`, line N to asset N |
| `width` only | Height follows aspect ratio. Nothing is ever distorted |

## Shipped templates

- **`tweet-clip`** — tweet card above a cropped clip on white, logo bottom-centre. The workhorse.
- **`caption-clip`** — same shape, but the hook is drawn text from a captions file, no image asset.
- **`full-bleed`** — clip fills the frame, small corner logo. For sources that are already vertical.

Copy any of them and change the numbers; that's the whole extension story.

## Run it

```bash
pip install -r requirements.txt        # PyYAML, and ffmpeg on PATH

python compose.py --template tweet-clip --prefix memehut
python compose.py --template caption-clip --captions hooks.txt --prefix britchannel
python compose.py --template tweet-clip --only 3,7,9 --dry-run
```

| Flag | |
|---|---|
| `--template` | template name in `templates/` |
| `--input` | folder of numbered assets (default `input/`) |
| `--out` | output folder (default `out/`) |
| `--prefix` | output filename prefix — usually the account name |
| `--captions` | text file, one hook per line, line N to asset N |
| `--only` | comma-separated indices, e.g. `3,7,9` |
| `--dry-run` | print the ffmpeg commands and run nothing |

Indices are discovered from whatever is actually in the input folder. Gaps are fine — `m1, m2,
m7` composes three videos. One clip failing doesn't stop the batch; it reports and moves on.

## Multiple accounts

Keep a logo and a template per account:

```
assets/memehut.png          templates/tweet-clip-memehut.yaml
assets/britchannel.png      templates/tweet-clip-britchannel.yaml
```

Then it's one command per account, same input folder.

## Pairs with

[niche-content-sourcer](https://github.com/arnoldfrancis-marketer/niche-content-sourcer) — that
finds the clips and writes the hooks, this composites them. Sourcer's caption column drops
straight into `--captions`.

## Requirements

ffmpeg and ffprobe on PATH · Python 3.8+ · PyYAML.

## Licence

MIT.
