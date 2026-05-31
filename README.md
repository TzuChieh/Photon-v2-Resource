# Photon-v2-Resource

Data files for the Photon-v2 renderer.

## Layout

- `Engine/`: runtime data used by engine features, such as precomputed BSDF tables.
- `EngineTest/`: small data files used by engine unit tests.
- `RenderTest/`: scenes and reference images for end-to-end render tests.
- `Scenes/`: standalone sample scenes.

## RenderTest

`RenderTest/` contains scenes and reference images for end-to-end render tests.

PhotonCLI writes multi-image outputs as numbered files, so reference images use the same naming:

```text
ref_name_0.pfm
ref_name_1.pfm
...
```

`_0` is the beauty output. Later indices are scene-specific outputs, such as variance images used by unbiased path-tracing z-tests. Photon-mapping scenes intentionally use non-z verifiers and do not require variance references.

Some tests, such as `fullscreen_unit_radiance` and `gray_furnace_box`, use analytic verifier targets instead of reference images.

Regenerate all reference scenes with:

```powershell
python RenderTest/render_all_refs.py --photon-cli <path-to-photon-cli> -t 8
```
