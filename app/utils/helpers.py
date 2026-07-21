"""Small, generic helpers used across the pipeline.

`safe_get` navigates the deeply-nested, all-nullable CT.gov JSON without a
cascade of `.get(...) or {}` guards at every call site.
"""


def safe_get(data, path: str, default=None):
    """Dotted-path lookup into nested dicts; returns default if any step is missing.

    safe_get({"a": {"b": 1}}, "a.b") -> 1
    safe_get({"a": {}}, "a.b.c", 0)  -> 0
    """
    cur = data
    for key in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return default
    return cur if cur is not None else default
