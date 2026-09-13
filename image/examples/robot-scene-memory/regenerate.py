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
from tempfile import TemporaryDirectory

import networkx as nx
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
GENERATOR_VERSION = "0.1.2"
SPATIAL_RELATIONS = {"next_to", "holding", "wearing", "on_top_of", "inside", "behind", "in_front_of"}
OBJECT_ALIASES = {
    "yellow_cloth": {"yellow_cloth", "microfiber_cloth", "yellow_microfiber_cloth", "yellow_towel"},
    "robot_gripper": {"robot_gripper", "robotic_arm", "robotic_arm_gripper", "robotic_gripper"},
    "toy_banana": {"toy_banana", "banana_toy", "balloon", "toy_pear"},
    "toy_strawberry": {"toy_strawberry", "strawberry_toy"},
    "sandwich_toy": {"toy_bread", "sponge", "striped_roll_toy", "polishing_pad", "sandwich_toy", "toy_food_item"},
    "cloth_clip": {"binder_clip", "black_marker", "black_roller", "black_clamp"},
    "toy_tomato": {"toy_tomato", "tomato"},
}


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


def curate_graph(data: dict) -> None:
    """Remove noisy OCR, merge obvious label aliases, and collapse duplicate edges."""
    removed = {
        node["id"]
        for node in data["nodes"]
        if node.get("type") == "text_span"
        or (node.get("type") == "object" and node.get("label") == "qr_code")
    }
    nodes = [node for node in data["nodes"] if node["id"] not in removed]
    edges = [edge for edge in data["edges"] if edge["source"] not in removed and edge["target"] not in removed]

    aliases = {label: canonical for canonical, labels in OBJECT_ALIASES.items() for label in labels}
    groups: dict[str, list[dict]] = {}
    for node in nodes:
        if node.get("type") == "object" and node.get("label") in aliases:
            groups.setdefault(aliases[node["label"]], []).append(node)

    id_map: dict[str, str] = {}
    merged_ids: set[str] = set()
    merged_nodes: list[dict] = []
    for canonical, members in groups.items():
        canonical_id = f"shared_{canonical}"
        merged_ids.update(node["id"] for node in members)
        id_map.update({node["id"]: canonical_id for node in members})
        seen_in = sorted({image_id for node in members for image_id in node.get("seen_in", [])})
        confidence = max((node.get("confidence", 0) for node in members), default=0)
        merged_nodes.append({
            "id": canonical_id,
            "type": "object",
            "label": canonical,
            "confidence": confidence,
            "seen_in": seen_in,
        })

    nodes = [node for node in nodes if node["id"] not in merged_ids] + merged_nodes
    for edge in edges:
        edge["source"] = id_map.get(edge["source"], edge["source"])
        edge["target"] = id_map.get(edge["target"], edge["target"])

    deduplicated: dict[tuple[str, str, str], dict] = {}
    for edge in edges:
        if edge["source"] == edge["target"]:
            continue
        identity = (edge["source"], edge["target"], edge.get("relation", "unknown"))
        if identity not in deduplicated:
            deduplicated[identity] = dict(edge)
            deduplicated[identity]["occurrences"] = int(edge.get("occurrences", 1))
        else:
            current = deduplicated[identity]
            current["occurrences"] += int(edge.get("occurrences", 1))
            if (edge.get("confidence") or 0) > (current.get("confidence") or 0):
                current["confidence"] = edge.get("confidence")

    pair_keys: dict[tuple[str, str], int] = {}
    final_edges = []
    for edge in sorted(deduplicated.values(), key=lambda item: (item["source"], item["target"], item.get("relation", ""))):
        pair = (edge["source"], edge["target"])
        edge["key"] = pair_keys.get(pair, 0)
        pair_keys[pair] = edge["key"] + 1
        final_edges.append(edge)

    data["nodes"] = sorted(nodes, key=lambda node: node["id"])
    data["edges"] = final_edges


def add_fixed_layout(data: dict) -> None:
    width = 1440
    height = 900
    graph = nx.Graph()
    graph.add_nodes_from(node["id"] for node in sorted(data["nodes"], key=lambda node: node["id"]))
    graph.add_edges_from((edge["source"], edge["target"]) for edge in data["edges"])
    positions = nx.spring_layout(
        graph,
        seed=42,
        iterations=250,
        k=1.7 / math.sqrt(max(len(data["nodes"]), 1)),
    )
    x_values = [float(position[0]) for position in positions.values()]
    y_values = [float(position[1]) for position in positions.values()]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    x_span = x_max - x_min or 1
    y_span = y_max - y_min or 1

    for node in data["nodes"]:
        x, y = positions[node["id"]]
        node["x"] = round(80 + (float(x) - x_min) / x_span * (width - 160), 2)
        node["y"] = round(70 + (float(y) - y_min) / y_span * (height - 140), 2)

    data.setdefault("graph", {})["layout"] = {
        "algorithm": "spring_seed_42_v1",
        "width": width,
        "height": height,
    }


def prepare_graph(data: dict) -> dict:
    if "links" in data and "edges" not in data:
        data["edges"] = data.pop("links")
    normalize_ids(data)
    sanitize_paths(data)
    curate_graph(data)
    add_fixed_layout(data)
    data.setdefault("graph", {})["sample"] = "robot_scene_memory"
    data["graph"]["generator"] = {
        "package": "opengraph-image",
        "version": GENERATOR_VERSION,
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
    if data.get("directed") is not True or data.get("multigraph") is not True:
        raise ValueError("graph.json must describe a directed multigraph")
    if not nodes:
        raise ValueError("graph.json has no nodes")

    ids = [node.get("id") for node in nodes]
    if any(not isinstance(node_id, str) or not SNAKE_CASE.fullmatch(node_id) for node_id in ids):
        raise ValueError("Every node ID must be unique snake_case")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate node IDs found")

    known = set(ids)
    image_ids = {node["id"] for node in nodes if node.get("type") == "image"}
    source_ids = {path.stem for path in SOURCE.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}}
    if image_ids != source_ids:
        raise ValueError(f"Image nodes do not match the source set: {sorted(image_ids ^ source_ids)}")

    for node in nodes:
        if node.get("type") not in NODE_TYPES:
            raise ValueError(f"Unknown node type: {node.get('type')}")
        confidence = node.get("confidence")
        if confidence is not None and (not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError(f"Invalid node confidence: {node['id']}")
        bounding_box = node.get("bounding_box")
        if bounding_box is not None and (
            not isinstance(bounding_box, list)
            or len(bounding_box) != 4
            or not all(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1 for value in bounding_box)
        ):
            raise ValueError(f"Invalid bounding box: {node['id']}")
        seen_in = node.get("seen_in", [])
        if not isinstance(seen_in, list) or any(image_id not in image_ids for image_id in seen_in):
            raise ValueError(f"Invalid seen_in references: {node['id']}")
        if not all(isinstance(node.get(axis), (int, float)) and math.isfinite(node[axis]) for axis in ("x", "y")):
            raise ValueError(f"Node has no finite fixed position: {node['id']}")
        if node.get("type") == "image":
            path = node.get("path", "")
            if not path.startswith("source/") or ".." in Path(path).parts:
                raise ValueError(f"Unsafe image path: {path}")
            if not (ROOT / path).is_file():
                raise ValueError(f"Image path does not exist: {path}")

    node_types = {node["id"]: node["type"] for node in nodes}
    degrees = {node_id: 0 for node_id in ids}
    relations = {"contains", "in_scene", "has_attribute", "has_text"} | SPATIAL_RELATIONS
    for edge in edges:
        if edge.get("source") not in known or edge.get("target") not in known:
            raise ValueError(f"Edge references an unknown node: {edge}")
        if edge["source"] == edge["target"]:
            raise ValueError(f"Self-loop found: {edge}")
        relation = edge.get("relation")
        if relation not in relations:
            raise ValueError(f"Unknown edge relation: {relation}")
        confidence = edge.get("confidence")
        if confidence is not None and (not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError(f"Invalid edge confidence: {edge}")
        endpoints = (node_types[edge["source"]], node_types[edge["target"]])
        expected = {
            "contains": {("image", "object")},
            "in_scene": {("image", "scene")},
            "has_attribute": {("image", "attribute"), ("object", "attribute")},
            "has_text": {("image", "text_span")},
        }.get(relation, {("object", "object")})
        if endpoints not in expected:
            raise ValueError(f"Invalid endpoints for {relation}: {endpoints}")
        degrees[edge["source"]] += 1
        degrees[edge["target"]] += 1

    if any(degrees[node_id] == 0 for node_id in ids if node_types[node_id] != "image"):
        raise ValueError("An orphan non-image node remains")
    for image_id in image_ids:
        scene_edges = [edge for edge in edges if edge["source"] == image_id and edge.get("relation") == "in_scene"]
        if len(scene_edges) != 1:
            raise ValueError(f"Image must have exactly one in_scene edge: {image_id}")

    leaked = [text for text in walk_strings(data) if LOCAL_PATH.search(text)]
    if leaked:
        raise ValueError("A local absolute path remains in graph.json")

    return len(nodes), len(edges)


def render_html(data: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    d3_source = D3_SOURCE.read_text(encoding="utf-8").replace("</script", "<\\/script")
    graph_data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    graph_data = graph_data.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    if template.count("/*__D3_SOURCE__*/") != 1 or template.count("__GRAPH_DATA__") != 1:
        raise ValueError("graph.template.html has invalid replacement markers")
    return template.replace("/*__D3_SOURCE__*/", d3_source).replace("__GRAPH_DATA__", graph_data)


def write_atomic(path: Path, contents: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    temporary.replace(path)


def validate_html() -> None:
    html = GRAPH_HTML.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    if "/*__D3_SOURCE__*/" in html or "__GRAPH_DATA__" in html:
        raise ValueError("graph.html contains an unreplaced template marker")
    if "https://cdn" in html:
        raise ValueError("graph.html must not depend on a D3 CDN")
    if "d3.drag" in html:
        raise ValueError("The read-only viewer must not enable node dragging")
    for forbidden in ("forceSimulation", "contenteditable", "innerHTML"):
        if forbidden in template:
            raise ValueError(f"The read-only viewer template must not use {forbidden}")
    for required in ('<meta name="description"', 'rel="canonical"', 'rel="icon"'):
        if required not in html:
            raise ValueError(f"graph.html is missing required metadata: {required}")


def render_current_graph() -> tuple[int, int]:
    data = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    data = prepare_graph(data)
    counts = validate_graph(data)
    write_atomic(GRAPH_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    write_atomic(GRAPH_HTML, render_html(data))
    validate_html()
    return counts


def regenerate() -> tuple[int, int]:
    load_dotenv(ROOT / ".env", override=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is missing. Copy .env.example to .env and add your key.")

    installed = version("opengraph-image")
    if installed != GENERATOR_VERSION:
        raise SystemExit(f"Expected opengraph-image=={GENERATOR_VERSION}, found {installed}.")

    with TemporaryDirectory(prefix="robot-scene-memory-") as temporary_directory:
        raw_graph = Path(temporary_directory) / "graph.json"
        build_graph_from_folder(SOURCE, raw_graph)
        data = prepare_graph(json.loads(raw_graph.read_text(encoding="utf-8")))
        counts = validate_graph(data)
        write_atomic(GRAPH_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        write_atomic(GRAPH_HTML, render_html(data))
        validate_html()
        return counts


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
