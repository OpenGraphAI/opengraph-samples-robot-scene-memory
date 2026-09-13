# Robot Scene Memory graph

This example treats sixteen robot-camera observations as a compact scene memory. It is not a training dataset or behavior model. `opengraph-image` extracts objects, scenes, attributes, and spatial relationships; a bundled Cytoscape.js viewer then renders the committed result as a read-only static graph.

## Snapshot

- 127 nodes and 323 directed relationships
- 16 BridgeData V2 observations from four cloth-manipulation trajectories
- Shared concepts for recurring entities such as `yellow_cloth`, `robot_gripper`, and `toy_tomato`
- Fixed, seeded node positions; the browser never runs a force simulation or mutates graph data
- No API key, model call, backend, or third-party CDN is required to view `graph.html`

## Reproduce the artifacts

Use Python 3.12, then install the pinned dependencies:

```powershell
py -3.12 -m venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
Copy-Item .env.example .env
```

Put an Anthropic API key in the local `.env` file and run:

```powershell
.venv\Scripts\python.exe regenerate.py
```

The script calls `opengraph-image==0.1.2` with its `claude-sonnet-4-6` extractor, normalizes and validates the result, merges a documented set of obvious label aliases, removes noisy OCR nodes, computes seeded fixed positions, and writes `graph.json` plus the self-contained `graph.html`. Model extraction is reproducible as a procedure but is not guaranteed to be byte-for-byte deterministic.

To rebuild only the Cytoscape.js artifact from the committed graph, or validate without a model call:

```powershell
.venv\Scripts\python.exe regenerate.py --render-only
.venv\Scripts\python.exe regenerate.py --validate-only
```

The `.env` file is ignored by Git. Do not commit API keys.

## Data and licenses

The selected images come from [BridgeData V2](https://rail-berkeley.github.io/bridgedata/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See [`source/README.md`](source/README.md) for exact URLs and SHA-256 checksums. Cytoscape.js 3.34.3 and its MIT license are included under `vendor/` so the gallery has no runtime network dependency.
