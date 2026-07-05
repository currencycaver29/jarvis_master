from dataclasses import dataclass

@dataclass
class ExactHit:
    memory_id: str
    fact_id: str
    score: float = 0.0
    entity: str = ""
    attribute: str = ""
    value: str = ""
    value_num: float = 0.0
    unit: str = ""
    period: str = ""
    source_span: str = ""
    surface: str = "exact"

def search_fts(*args, **kwargs):
    return []

def search_numeric(*args, **kwargs):
    return []

def search_numeric_historical(*args, **kwargs):
    return []
