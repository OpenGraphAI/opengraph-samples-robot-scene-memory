"""Regenerate and validate the Robot Scene Memory gallery artifacts.

Usage:
    python regenerate.py
    python regenerate.py --render-only
    python regenerate.py --validate-only
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv
from opengraph_image.graph import build_graph_from_folder

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "source").resolve()
GRAPH_JSON = ROOT / "graph.json"
GRAPH_HTML = ROOT / "graph.html"
TEMPLATE = ROOT / "graph.template.html"
D3_SOURCE = ROOT / "vendor" / "d3.v7.min.js"
NODE_TYPES = {"image", "object", "scene", "attribute", "text_span"}
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
LOCAL_PATH = re.compile(r"(?:[a-zA-Z]:[\\/]|/(?:Users|home)/)")


def snake_case(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not cleaned:
        cleaned = "node"
    if cleaned[0].isdigit():
        cleaned = f"node_{cleaned}"
    return cleaned


def normalize_ids(data: dict) -> None:
    used: set[str] = set()
    id_map: dict[str, str] = {}

    for node in data["nodes"]:
        original = str(node["id"])
        candidate = snake_case(original)
        unique = candidate
        suffix = 2
        while unique in used:
            unique = f"{candidate}_{suffix}"
            suffix += 1
        used.add(unique)
        id_map[original] = unique
        node["id"] = unique

    for edge in data["edges"]:
        edge["source"] = id_map[str(edge["source"])]
        edge["target"] = id_map[str(edge["target"])]

    for node in data["nodes"]:
        if "seen_in" in node:
            node["seen_in"] = [id_map.get(str(item), snake_case(str(item))) for item in node["seen_in"]]


def sanitize_paths(data: dict) -> None:
    for node in data["nodes"]:
        if node.get("type") == "image":
            filename = Path(str(node["path"])).name
            node["path"] = f"source/{filename}"


def add_fixed_layout(data: dict) -> None:
    type_order = ["image", "object", "scene", "attribute", "text_span"]
    groups = {
        node_type: sorted(
            (node for node in data["nodes"] if node.get("type") == node_type),
            key=lambda node: node["id"],
        )
        for node_type in type_order
    }
    max_group = max((len(nodes) for nodes in groups.values()), default=1)
    width = 1440
    height = max(760, 120 + max_group * 58)
    x_positions = {
        "image": 140,
        "object": 500,
        "scene": 840,
        "attribute": 1180,
        "text_span": 1320,
    }

    for node_type, nodes in groups.items():
        if not nodes:
            continue
        available = height - 140
        step = available / max(len(nodes), 1)
        for index, node in enumerate(nodes):
            node["x"] = x_positions[node_type]
            node["y"] = round(70 + step * (index + 0.5), 2)

    data.setdefault("graph", {})["layout"] = {
        "algorithm": "type_columns_v1",
        "width": width,
        "height": height,
    }


def prepare_graph(data: dict) -> dict:
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    normalize_ids(data)
    sanitize_paths(data)
    add_fixed_layout(data)
    data.setdefault("graph", {})["sample"] = "robot_scene_memory"
    data["graph"]["generator"] = {
        "package": "opengraph-image",
        "version": version("opengraph-image"),
        "model": "claude-sonnet-4-6",
    }
    return data


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)


def validate_graph(data: dict) -> tuple[int, int]:
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("graph.json must contain node and edge lists")

    ids = [node.get("id") for node in nodes]
    if any(not isinstance(node_id, str) or not SNAKE_CASE.fullmatch(node_id) for node_id in ids):
        raise ValueError("Every node ID must be unique snake_case")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate node IDs found")

    known = set(ids)
    for node in nodes:
        if node.get("type") not in NODE_TYPES:
            raise ValueError(f"Unknown node type: {node.get('type')}")
        if not all(isinstance(node.get(axis), (int, float)) and math.isfinite(node[axis]) for axis in ("x", "y")):
            raise ValueError(f"Node has no finite fixed position: {node['id']}")
        if node.get("type") == "image":
            path = node.get("path", "")
            if not path.startswith("source/") or ".." in Path(path).parts:
                raise ValueError(f"Unsafe image path: {path}")

    for edge in edges:
        if edge.get("source") not in known or edge.get("target") not in known:
            raise ValueError(f"Edge references an unknown node: {edge}")

    leaked = [text for text in walk_strings(data) if LOCAL_PATH.search(text)]
    if leaked:
        raise ValueError("A local absolute path remains in graph.json")

    return len(nodes), len(edges)


def render_html(data: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    d3_source = D3_SOURCE.read_text(encoding="utf-8").replace("</script", "<\\/script")
    graph_data = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    if template.count("/*__D3_SOURCE__*/") != 1 or template.count("__GRAPH_DATA__") != 1:
        raise ValueError("graph.template.html has invalid replacement markers")
    return template.replace("/*__D3_SOURCE__*/", d3_source).replace("__GRAPH_DATA__", graph_data)


def write_atomic(path: Path, contents: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    temporary.replace(path)


def validate_html() -> None:
    html = GRAPH_HTML.read_text(encoding="utf-8")
    if "/*__D3_SOURCE__*/" in html or "__GRAPH_DATA__" in html:
        raise ValueError("graph.html contains an unreplaced template marker")
    if "https://cdn" in html:
        raise ValueError("graph.html must not depend on a D3 CDN")
    if "d3.drag" in html:
        raise ValueError("The read-only viewer must not enable node dragging")


def render_current_graph() -> tuple[int, int]:
    data = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    add_fixed_layout(data)
    counts = validate_graph(data)
    write_atomic(GRAPH_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    write_atomic(GRAPH_HTML, render_html(data))
    validate_html()
    return counts


def regenerate() -> tuple[int, int]:
    load_dotenv(ROOT / ".env", override=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is missing. Copy .env.example to .env and add your key.")

    raw_graph = ROOT / ".graph.generated.json"
    try:
        build_graph_from_folder(SOURCE, raw_graph)
        data = prepare_graph(json.loads(raw_graph.read_text(encoding="utf-8")))
        counts = validate_graph(data)
        write_atomic(GRAPH_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        write_atomic(GRAPH_HTML, render_html(data))
        validate_html()
        return counts
    finally:
        raw_graph.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--render-only", action="store_true", help="Rebuild graph.html from graph.json without an API call")
    mode.add_argument("--validate-only", action="store_true", help="Validate the committed graph artifacts without an API call")
    args = parser.parse_args()

    if args.validate_only:
        counts = validate_graph(json.loads(GRAPH_JSON.read_text(encoding="utf-8")))
        validate_html()
    elif args.render_only:
        counts = render_current_graph()
    else:
        counts = regenerate()

    print(f"Validated {counts[0]} nodes and {counts[1]} edges.")


if __name__ == "__main__":
    main()
