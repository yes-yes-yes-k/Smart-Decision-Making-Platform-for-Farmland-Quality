"""Offline provenance and draft sampling for the replacement extraction benchmark.

These helpers never call a model or change historical references. A draft is not
a final acceptance partition: unresolved metadata and duplicate review block it.
"""
from collections import Counter, defaultdict
import hashlib
import random
import re


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def reconcile(files, documents):
    """Match bytes only, never guess provenance from similar filenames."""
    byhash = defaultdict(list)
    for row in files:
        if row.get('sha256'):
            byhash[row['sha256']].append(row['path'])
    matches, seen = [], set()
    for doc in sorted(documents, key=lambda d: d['id']):
        paths = sorted(byhash.get(doc.get('file_hash'), []))
        seen.update(paths)
        matches.append(dict(document_id=doc['id'], source_paths=paths,
                            match='exact_bytes' if paths else 'unmatched',
                            filename_match_used=False))
    return matches, [row for row in files if row['path'] not in seen]


def standard_family(number):
    """Strip revision BEFORE punctuation normalization (avoids swallowing digits)."""
    value = re.sub(r'[-—–]\s*(?:19|20)\d{2}\s*$', '', number or '')
    return re.sub(r'[^\w]', '', value.casefold())


def identity_components(documents):
    parent = {d['id']: d['id'] for d in documents}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    seen = {}
    edges = []
    for d in sorted(documents, key=lambda r: r['id']):
        doi = (d.get('doi_normalized') or '').strip().lower()
        doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
        keys = [('file', d.get('file_hash')), ('doi', doi),
                ('standard_family', standard_family(d.get('standard_number_normalized')))]
        for kind, value in keys:
            if not value:
                continue
            if (kind, value) in seen:
                other = seen[kind, value]
                a, b = find(d['id']), find(other)
                parent[max(a, b)] = min(a, b)
                edges.append(dict(a=other, b=d['id'], reason=kind, value=value))
            else:
                seen[kind, value] = d['id']
    return {k: find(k) for k in parent}, edges


def language_hint(text):
    """Diagnostic script mix, not verified bibliographic language."""
    han = len(re.findall(r'[\u3400-\u9fff]', text))
    latin = len(re.findall(r'[A-Za-z]', text))
    if han + latin < 40:
        return 'unknown'
    if han > latin:
        return 'zh_candidate'
    if han < latin * .05:
        return 'en_candidate'
    return 'mixed_candidate'


def draft_representative(documents, chunks, seed, groups=100):
    """Group-stratified draft, max three chunks; short groups stay eligible.

    Fixed group quotas make inclusion probability n_h/N_h explicit. The group
    design weight is for document-group estimates, NOT a chunk population weight.
    A shortfall is reported instead of substituting a longer/easier document.
    """
    bygroup = defaultdict(list)
    for c in chunks:
        bygroup[c['isolation_group']].append(c)
    docmap = {d['id']: d for d in documents}
    strata = defaultdict(list)
    for group, rows in bygroup.items():
        d = docmap[min(c['document_id'] for c in rows)]
        key = (d.get('document_kind') or 'unknown',
               d.get('language') or 'unknown',
               d.get('parse_quality') or 'unknown')
        strata[key].append(group)
    count = min(groups, len(bygroup))
    total = len(bygroup)
    if not total:
        return [], dict(status='draft', shortfall=300, groups=0)
    quotas = {k: count * len(v) // total for k, v in strata.items()}
    remaining = count - sum(quotas.values())
    order = sorted(strata, key=lambda k: (-(count * len(strata[k]) % total), k))
    for k in order[:remaining]:
        quotas[k] += 1
    selected = []
    for key in sorted(strata):
        ids = sorted(strata[key])
        random.Random(seed + ':groups:' + repr(key)).shuffle(ids)
        for group in ids[:quotas[key]]:
            selected.append((group, key, quotas[key] / len(ids)))
    random.Random(seed + ':partition').shuffle(selected)
    cal_count = min(20, len(selected) // 5)
    rows = []
    for part, selected_groups in [('calibration', selected[:cal_count]),
                                  ('test', selected[cal_count:])]:
        offset = random.Random(seed + ':offset:' + part).randrange(4)
        for rank, (group, key, probability) in enumerate(selected_groups):
            # Rotate the omitted quartile separately in each partition.
            omitted = (rank + offset) % 4
            bucket_order = [q for q in range(4) if q != omitted] + [omitted]
            buckets = defaultdict(list)
            for c in sorted(bygroup[group], key=lambda c: c['sample_id']):
                buckets[c['position_quartile']].append(c)
            rng = random.Random(seed + ':chunks:' + str(group))
            for bucket in buckets.values():
                rng.shuffle(bucket)
            chosen = []
            while len(chosen) < 3 and any(buckets.values()):
                for q in bucket_order:
                    if buckets[q] and len(chosen) < 3:
                        chosen.append(buckets[q].pop())
            for c in chosen:
                partition_probability = probability * len(selected_groups) / len(selected)
                rows.append(dict(c, track='representative', partition=part,
                    selection_status='draft_not_acceptance_frozen',
                    group_inclusion_probability=probability,
                    group_design_weight=1 / probability,
                    group_partition_inclusion_probability=partition_probability,
                    group_partition_design_weight=1 / partition_probability,
                    weight_scope='document_group_only_not_chunk_population',
                    stratum=list(key)))
    return rows, dict(status='draft', groups=len(selected), chunks=len(rows),
        shortfall=max(0, 300-len(rows)), seed=seed,
        quartiles={p: dict(Counter(str(r['position_quartile']) for r in rows
                                   if r['partition'] == p))
                   for p in ('calibration', 'test')},
        stratum_allocation=[dict(stratum=list(k),pool_groups=len(strata[k]),selected_groups=quotas[k])
                            for k in sorted(strata)],
        final_freeze_blocked=True)
