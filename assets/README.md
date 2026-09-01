# Assets

Static files templates point at — logos, watermarks, frames, endcards. Referenced by path
relative to the repo root:

```yaml
- type: image
  id: logo
  source: "assets/logo.png"
```

Running more than one account? Keep a logo per account and pass the right one by swapping the
template, or keep a template per account:

```
assets/memehut.png
assets/britchannel.png
templates/tweet-clip-memehut.yaml
templates/tweet-clip-britchannel.yaml
```

Use PNG with transparency. The composer scales to the template's `width` and preserves aspect
ratio — it never distorts.
