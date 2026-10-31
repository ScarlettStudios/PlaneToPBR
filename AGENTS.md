# Project guidance

## Purpose and layout

PlaneToPBR is a Blender add-on (extension) that turns one image into a plane
with a PBR material. `blender_manifest.toml` declares the extension; its
`blender_version_min` (5.1) sets the oldest supported Blender and therefore
Python 3.13. `__init__.py` registers the modules in `scripts/`:

- `hf_client.py`: the free flow's stdlib HTTP client for the FacadeMaker
  Inference Space (`SPACE_BASE`).
- `platform_client.py`: the authenticated PlaneToPBR Pro (GPU) backend client.
- `utils.py`: both generation pipelines, plane creation, the material
  node graph, and modifiers.
- `operators.py`: Blender operators; network work runs on background threads
  polled by modal timers.
- `panels.py`, `properties.py`, `extension_draw.py`, `addon_runtime.py`: the
  sidebar panel, add-on preferences (Pro login lives here), the extension
  listing UI, and package-id lookup.

`tests/` holds pytest tests that stub `bpy`, so they run without Blender.
`requirements-dev.txt` is the hashed set of development tools (pytest, Ruff).
The add-on has no pip runtime dependencies; keep it stdlib-only so it runs on
Blender's bundled Python. `Containerfile` defines the checks image;
`.containerignore` restricts the build context to required inputs.
`.github/workflows/ci.yml` builds the checks stage with Buildah, then packages
and releases the extension zip. `ruff.toml` defines lint and format rules and
the Python 3.13 target.

## Setup and checks

Use Python 3.13 (Blender 5.1's interpreter) in a project virtual environment.
Install with `python -m pip install -r requirements-dev.txt`.

Run:

```sh
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
```

To run the same checks in a container, as CI does:

```sh
buildah bud --format docker --file Containerfile --target checks .
```

Pin the base image by digest in `PYTHON_IMAGE`, and keep its Python minor
version equal to the oldest supported Blender's.

## Change conventions

- Keep `hf_client.py` compatible with the Space's `/predict` contract: inputs
  `(image_path, prompt)`, and four PNG file outputs in the order depth, normal,
  roughness, mask. The client resolves `predict` by name from `/config`; do not
  hard-code an `fn_index`. Change `SPACE_BASE` only when the Space moves.
- Never block Blender's UI thread on network calls. Keep requests on worker
  threads, and touch `bpy` data only from the operator's main-thread callbacks.
- Keep the manifest's `[permissions]` accurate when network or file access
  changes. Bump the manifest `version` deliberately for releases.
- The release zip contains only `__init__.py`, `blender_manifest.toml`,
  `README.md`, `LICENSE`, and `scripts/`. CI publishes it to a GitHub release
  only for `v*` tags; create release tags only when the owner asks.
- Add focused tests for behavior changes, with `bpy` and network calls
  mocked. Do not commit credentials, tokens, generated textures, release zips,
  or virtual environments.
- Commit messages follow Conventional Commits. Do not add `Co-Authored-By`
  trailers or any other AI/agent attribution to commits or pull requests.
- Keep changes focused and report which checks ran and anything verified only
  in Blender or against the live Space.
