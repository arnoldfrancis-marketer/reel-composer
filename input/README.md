# Numbered assets go here

One number per output video. The template names the patterns; `{n}` is the number.

```
input/
  m1.mp4   t1.png
  m2.mp4   t2.png
  m3.mp4   t3.png
```

The composer scans this folder for every `n` that has the template's video asset, and processes
them in order. Gaps are fine — `m1, m2, m7` composes three videos.

`m` for the raw clip, `t` for the tweet screenshot, purely by convention: change the `source`
patterns in the template to whatever you already name things.
