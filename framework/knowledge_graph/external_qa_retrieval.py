"""Source-bound vector and real NetworkX graph retrieval for isolated QA runs."""
from collections import defaultdict, deque
import hashlib
import json
import math


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def text_ranges(text, limit=4000):
    start, size = 0, 0
    for index, char in enumerate(text):
        width = len(char.encode("utf-8"))
        if width > limit:
            raise ValueError("byte_limit_smaller_than_character")
        if size + width > limit:
            yield start, index
            start, size = index, 0
        size += width
    if start < len(text):
        yield start, len(text)


def make_index_inputs(documents, limit=4000):
    chunks, units = [], []
    for document in documents:
        doc_chunks = []
        for block in document["blocks"]:
            for start, end in text_ranges(block["text"], limit):
                value = block["text"][start:end]
                if not value.strip():
                    continue
                item = {"id": sha(document["id"]+"\0"+block["id"]+f":{start}:{end}"),
                        "document_id": document["id"], "block_id": block["id"], "start": start, "end": end,
                        "text": value, "kind": block.get("kind", "text"), "text_sha256": sha(value)}
                chunks.append(item); doc_chunks.append(item)
        # Pack source chunks within the same document. Graph provenance is at
        # this text-unit granularity, never an invented sentence-level citation.
        members, texts, size = [], [], 0
        def emit():
            value = "\n\n".join(texts)
            units.append({"id": sha(document["id"]+"|"+"|".join(members)), "document_id": document["id"],
                          "text": value, "text_sha256": sha(value), "chunk_ids": list(members)})
        for chunk in doc_chunks:
            width = len(chunk["text"].encode("utf-8"))
            if members and size+width+2 > limit:
                emit(); members, texts, size = [], [], 0
            members.append(chunk["id"]); texts.append(chunk["text"]); size += width+2
        if members:
            emit()
    if len({row["id"] for row in chunks}) != len(chunks):
        raise ValueError("duplicate_source_chunk")
    return chunks, units


def build_graph(predictions, units):
    import networkx as nx
    sources = {unit["id"]: unit for unit in units}
    graph = nx.MultiDiGraph()
    seen = set()
    for prediction in predictions:
        uid = prediction["unit_id"]
        if uid in seen or uid not in sources:
            raise ValueError("duplicate_or_wrong_graph_source")
        seen.add(uid)
        if prediction.get("origin") != "model_graph_extractor" or prediction["source_sha256"] != sources[uid]["text_sha256"]:
            raise ValueError("graph_must_use_source_bound_candidate_predictions")
        if prediction.get("state") != "completed":
            continue
        for entity in prediction["entities"]:
            name = entity["title"].strip().upper()
            if name not in graph:
                graph.add_node(name, units=set(), types=set())
            graph.nodes[name]["units"].add(uid)
            graph.nodes[name]["types"].add(entity["type"])
        for index, relation in enumerate(prediction["relationships"]):
            source, target = relation["source"].strip().upper(), relation["target"].strip().upper()
            for name in (source, target):
                if name not in graph:
                    graph.add_node(name, units=set(), types={"UNRESOLVED_ENDPOINT"})
                graph.nodes[name]["units"].add(uid)
            graph.add_edge(source, target, key=uid+":"+str(index), unit_id=uid,
                           description=relation["description"], origin="model_graph_extractor")
    return graph


def graph_payload(graph):
    return {"backend": "networkx.MultiDiGraph", "nodes": [{"id": key, "units": sorted(value["units"]), "types": sorted(value["types"])} for key, value in sorted(graph.nodes(data=True))],
            "edges": [{"source": a, "target": b, "key": key, **value} for a,b,key,value in graph.edges(keys=True, data=True)]}


def rank(chunks, embeddings, query_embedding, *, question, graph, units, arm, top_k=5, byte_budget=20000):
    import numpy as np
    if arm not in {"vector", "graphrag"}:
        raise ValueError("unknown_retrieval_arm")
    if len(embeddings) != len(chunks):
        raise ValueError("embedding_alignment_failed")
    matrix, query = np.asarray(embeddings, dtype=float), np.asarray(query_embedding, dtype=float)
    if matrix.ndim != 2 or query.ndim != 1 or matrix.shape[1] != len(query) or not np.isfinite(matrix).all() or not np.isfinite(query).all():
        raise ValueError("invalid_embeddings")
    norms = np.linalg.norm(matrix, axis=1)
    if not np.linalg.norm(query) or (norms == 0).any():
        raise ValueError("zero_embedding")
    similarities = matrix @ query / (norms*np.linalg.norm(query))
    order = sorted(range(len(chunks)), key=lambda index: (-float(similarities[index]), chunks[index]["id"]))
    boosts, edge_trace, seeds = defaultdict(float), defaultdict(list), []
    if arm == "graphrag":
        if graph is None or graph.number_of_edges() == 0:
            raise ValueError("graph_backend_unavailable_no_simulated_fallback")
        unit_map = {unit["id"]: unit for unit in units}
        chunk_to_units = defaultdict(set)
        for unit in units:
            for cid in unit["chunk_ids"]:
                chunk_to_units[cid].add(unit["id"])
        source_seed_units = set().union(*(chunk_to_units[chunks[index]["id"]] for index in order[:2]))
        normalized = question.casefold()
        literal = [name for name in graph if len(name) >= 3 and name.casefold() in normalized]
        semantic = [name for name, value in graph.nodes(data=True) if value["units"] & source_seed_units]
        seeds = sorted(set(literal), key=lambda name: (-len(name), name))[:8]
        seeds += [name for name in sorted(semantic) if name not in seeds][:max(0, 12-len(seeds))]
        queue, visited = deque((name, 0) for name in seeds), set(seeds)
        while queue:
            node, depth = queue.popleft()
            if depth >= 2:
                continue
            edges = list(graph.out_edges(node, keys=True, data=True)) + list(graph.in_edges(node, keys=True, data=True))
            for source, target, key, edge in sorted(edges, key=lambda edge: (edge[0], edge[1], edge[2])):
                for cid in unit_map[edge["unit_id"]]["chunk_ids"]:
                    boosts[cid] = max(boosts[cid], 1/(depth+1))
                    if key not in edge_trace[cid]:
                        edge_trace[cid].append(key)
                other = target if source == node else source
                if other not in visited and len(visited) < 128:
                    visited.add(other); queue.append((other, depth+1))
        order.sort(key=lambda index: (-boosts[chunks[index]["id"]], -float(similarities[index]), chunks[index]["id"]))
    result, consumed = [], 0
    for index in order:
        chunk = chunks[index]
        width = len(chunk["text"].encode("utf-8"))
        if len(result) >= top_k:
            break
        if consumed+width > byte_budget:
            continue
        consumed += width
        result.append({**chunk, "vector_score": float(similarities[index]), "graph_boost": boosts[chunk["id"]],
                       "graph_edge_ids": edge_trace[chunk["id"]][:20]})
    return result, {"source_utf8_bytes": consumed, "max_source_utf8_bytes": byte_budget, "top_k": top_k,
                    "seeds": seeds, "graph_contributing_chunks": sum(bool(row["graph_boost"]) for row in result)}
