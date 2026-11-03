"""Token usage of one Claude Code subagent, read from its transcript (the SubagentStop hook's
agent_transcript_path). Called by telemetry.py; reads nothing but the usage figures and model names.

Why a transcript: no documented hook gives a subagent's usage. The Agent tool result reports only the last
request, and a background agent's result reports none (code.claude.com/docs/en/hooks). The transcript's
format is private, so this reader is strict: any line or usage it doesn't recognize makes the whole agent
`unavailable` instead of a partial sum. Each request appears on several lines with the same usage, so it
counts each message id once. Shape checked against Claude Code 2.1.308; when a release changes it, bump
PARSER_VERSION with the fix.
"""
import json

PARSER_VERSION = "claude-transcript/1"
_FIELDS = {"input_tokens": "input_tokens", "output_tokens": "output_tokens",
           "cache_read_input_tokens": "cache_read_tokens", "cache_creation_input_tokens": "cache_write_tokens"}


def usage(path):
    """({model: {input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, requests}}, None), or
    (None, reason) when the figures can't be read reliably."""
    try:
        f = open(path, encoding="utf-8")
    except (OSError, TypeError):
        return None, "transcript not readable"
    per_request = {}
    with f:
        for n, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                return None, "unrecognized transcript line %d" % n
            if not isinstance(row, dict) or row.get("type") != "assistant":
                continue
            msg = row.get("message")
            if not isinstance(msg, dict) or not isinstance(msg.get("model"), str):
                return None, "unrecognized assistant entry on line %d" % n
            if msg["model"] == "<synthetic>":  # written by Claude Code itself, no API request behind it
                continue
            u, mid = msg.get("usage"), msg.get("id") or row.get("requestId")
            if not mid or not isinstance(u, dict) or not all(
                    isinstance(u.get(k), int) and not isinstance(u.get(k), bool) and u[k] >= 0 for k in _FIELDS):
                return None, "unrecognized usage on line %d" % n
            per_request[mid] = (msg["model"], u)
    if not per_request:
        return None, "no requests in transcript"
    models = {}
    for model, u in per_request.values():
        m = models.setdefault(model, dict.fromkeys(list(_FIELDS.values()) + ["requests"], 0))
        for k, name in _FIELDS.items():
            m[name] += u[k]
        m["requests"] += 1
    return models, None
