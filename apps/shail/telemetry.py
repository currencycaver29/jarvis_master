"""
In-memory telemetry system for SHAIL.
Tracks increments and observations, and supports snapshots for testing.
"""

RETRIEVAL_PATH = "retrieval_path"
RETRIEVAL_FUSION_WINNER = "retrieval_fusion_winner"
RETRIEVAL_THRESHOLD_DROPS = "retrieval_threshold_drops"
RETRIEVAL_LATENCY_MS = "retrieval_latency_ms"

_counters = {}
_histograms = {}

def reset():
    _counters.clear()
    _histograms.clear()

def incr(name: str, value: float = 1.0, **labels):
    label_suffix = ""
    if labels:
        label_suffix = "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"
    key = f"{name}{label_suffix}"
    _counters[key] = _counters.get(key, 0.0) + value

def observe(name: str, value: float, **labels):
    label_suffix = ""
    if labels:
        label_suffix = "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"
    key = f"{name}{label_suffix}"
    if key not in _histograms:
        _histograms[key] = []
    _histograms[key].append(value)

def snapshot():
    return {
        "counters": dict(_counters),
        "histograms": dict(_histograms)
    }
