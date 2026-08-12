# Robot Scene Memory

A static gallery showing how [OpenGraph AI](https://github.com/OpenGraphAI/opengraph-ai) turns robot workspace observations into an explorable scene memory.

## Status

The first example is being built from a small, attributed selection of BridgeData V2 observations. The published graph will be read-only and explorable; the source graph will be produced offline with `opengraph-image`.

**Live demo:** Coming soon.

## What this example demonstrates

- Visual objects and spatial relationships represented as a knowledge graph
- Recurring scene entities linked across robot-camera observations
- A static D3.js gallery that requires no account, API key, or runtime service

See the [OpenGraph AI repository](https://github.com/OpenGraphAI/opengraph-ai) for the graph-building tools and MCP integration.

## Rendering contract

- `opengraph-image` produces the graph data offline from selected observations.
- The gallery ships a fixed graph snapshot and precomputed node positions.
- D3.js renders a read-only viewer with zoom, pan, filtering, and inspection. Visitors cannot move, add, edit, or delete graph data.
- Additional conversations can produce a newer graph snapshot through the MCP workflow; the GitHub Pages gallery itself has no model, API key, or server runtime.

## Data source

The source is [BridgeData V2](https://rail-berkeley.github.io/bridgedata/), published under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The sample will use the terminal view 0/view 1 frame pairs from trajectories 2, 5, 8, and 11 in the public `datacol2_folding_table/fold_cloth_pnp/01/2023-05-19_12-20-29/raw/traj_group0` session. Full attribution and any image transformations will be recorded alongside the Phase 4 artifacts.
