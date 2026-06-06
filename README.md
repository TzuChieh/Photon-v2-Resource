# Photon-v2-Resource

Data files for the Photon-v2 renderer.

## Layout

- `Engine/`: runtime data used by engine features, such as precomputed BSDF tables.
- `EngineTest/`: small data files used by engine unit tests.
- `RenderTest/`: scenes and reference images for end-to-end render tests.
- `Scenes/`: standalone sample scenes.

## RenderTest

`RenderTest/` contains scenes and reference images for end-to-end render tests.

Reference image stems use semantic suffixes declared by `RenderTest/render_all_refs.py`:

```text
ref_name_beauty.pfm
ref_name_var.pfm
```

`beauty` is the radiance reference. `var` is the variance image used by unbiased path-tracing z-tests. Variance-only reference scenes emit a single variance output. Variance references may be shared only for intentionally equivalent sampling distributions; BVPT and BNEEPT use separate variance references. Photon-mapping scenes intentionally use non-z verifiers and do not require variance references.

Some tests, such as `fullscreen_unit_radiance` and `gray_furnace_box`, use analytic verifier targets instead of reference images.

Regenerate all reference scenes with:

```powershell
python RenderTest/render_all_refs.py --photon-cli <path-to-photon-cli> -t 8
```
