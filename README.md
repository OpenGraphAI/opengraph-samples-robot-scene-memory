# Robot Scene Memory

A static gallery showing how [OpenGraph AI](https://github.com/OpenGraphAI/opengraph-ai) turns robot workspace observations into an explorable scene memory.

## Status

The first example is built from 16 attributed BridgeData V2 observations. Its 127-node, 323-edge graph is read-only and explorable; `opengraph-image` produced the source graph offline and Cytoscape.js renders its fixed positions in the browser.

**Live demo:** [opengraphai.github.io/opengraph-samples-robot-scene-memory](https://opengraphai.github.io/opengraph-samples-robot-scene-memory/)

## What this example demonstrates

- Visual objects and spatial relationships represented as a knowledge graph
- Recurring scene entities linked across robot-camera observations
- A static Cytoscape.js gallery that requires no account, API key, or runtime service

See the [OpenGraph AI repository](https://github.com/OpenGraphAI/opengraph-ai) for the graph-building tools and MCP integration.

The landing page includes copy-ready Claude Desktop and Cursor configurations for the pinned `opengraph-image==0.1.2` MCP server. An Anthropic API key is required for local MCP extraction and query calls, but never for the static gallery.

## Rendering contract

- `opengraph-image` produces the graph data offline from selected observations.
- The gallery ships a fixed graph snapshot and precomputed node positions.
- Cytoscape.js renders a read-only viewer with zoom, pan, filtering, and inspection. Visitors cannot move, add, edit, or delete graph data.
- Additional conversations can produce a newer graph snapshot through the MCP workflow; the GitHub Pages gallery itself has no model, API key, or server runtime.

## Data source

The source is [BridgeData V2](https://rail-berkeley.github.io/bridgedata/), published under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The sample uses the terminal view 0/view 1 frame pairs from trajectories 2, 5, 8, and 11 in the public `datacol2_folding_table/fold_cloth_pnp/01/2023-05-19_12-20-29/raw/traj_group0` session. Exact source URLs, checksums, and attribution live beside the selected images.
