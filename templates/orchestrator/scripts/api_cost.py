"""API-equivalent cost of the recorded usage: what it would cost through the provider's API, at the rates the
workspace keeps in .orchestrator/rates.json. Always an estimate, never a subscription's spend: a plan such as
Claude Pro or Max, or ChatGPT Plus, has no per-token price. Called by `telemetry.py cost`.

The rates file ships empty: prices are the user's to add, each with its date and source, so none is assumed here.
Only runtime_reported usage is priced. Estimated or inferred figures never are, and neither is `calculated` usage:
it would be allowed only as a deterministic calculation from runtime_reported figures, and no record says which
figures it came from (no adapter produces it today). A runtime is priced only with a rule checked against its real
figures: Claude Code (Anthropic: input excludes cache reads and writes). Codex reports cached input inside
input_tokens; its rule waits for real payloads.
Cache writes: Anthropic prices 5-minute and 1-hour cache writes differently, and the transcripts give them as one
figure. That sum is priced at the single, combined `cache_write` rate the rates file gives, chosen by the user (the
5-minute rate undervalues 1-hour writes, the 1-hour rate overvalues 5-minute ones). So the result is an estimate at
a combined rate, never an exact API cost, even with exact prices.
"""
import datetime
import json
from decimal import Decimal, InvalidOperation

PRICES = ("input", "output", "cache_read", "cache_write")  # per million tokens
PROVIDER = {"claude-code": "anthropic"}  # runtimes whose token semantics are verified
_TOKENS = {"input": "input_tokens", "output": "output_tokens", "cache_read": "cache_read_tokens",
           "cache_write": "cache_write_tokens"}
_MILLION = Decimal(1000000)
_CENT = Decimal("0.0001")


def parse_rate(r):
    """A rates.json entry with its prices as Decimal, or ValueError naming what's wrong."""
    if not isinstance(r, dict):
        raise ValueError("entry is not an object")
    for k in ("provider", "model", "currency", "source", "effective_from"):
        if not isinstance(r.get(k), str) or not r[k].strip():
            raise ValueError("missing " + k)
    try:
        datetime.date.fromisoformat(r["effective_from"])
    except ValueError:
        raise ValueError("effective_from is not YYYY-MM-DD")
    out = dict(r)
    for k in PRICES:
        try:
            v = Decimal(str(r.get(k)))
        except InvalidOperation:
            raise ValueError(k + " is not a number")
        if not v.is_finite() or v < 0:
            raise ValueError(k + " is not a non-negative number")
        out[k] = v
    return out


def load_rates(path):
    """(valid rates, the file's version, [errors]). A missing file is no rates, not an error."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], None, []
    except (OSError, ValueError) as err:
        return [], None, ["rates file not readable: %s" % type(err).__name__]
    rates, errors = [], []
    for n, r in enumerate(data.get("rates", []) if isinstance(data, dict) else [], 1):
        try:
            rates.append(parse_rate(r))
        except ValueError as err:
            errors.append("entry %d: %s" % (n, err))
    return rates, (data.get("version") if isinstance(data, dict) else None) or "unversioned", errors


def rate_for(rates, provider, model, day):
    """The rate in force on day (YYYY-MM-DD) for that provider and model, or None."""
    fits = [r for r in rates if r["provider"] == provider and r["model"] == model and r["effective_from"] <= day]
    return max(fits, key=lambda r: r["effective_from"]) if fits else None


def estimate(runtime, usage, rate):
    """(Decimal cost, None), or (None, why it can't be estimated)."""
    if runtime not in PROVIDER:
        return None, "no verified pricing rule for %s usage yet" % (runtime or "unknown runtime")
    if usage.get("source") != "runtime_reported":
        return None, "usage %s" % (usage.get("source") or "missing")
    if rate is None:
        return None, "no rate for this model"
    if any(usage.get(t) is None for t in _TOKENS.values()):
        return None, "usage incomplete"
    return sum(Decimal(usage[_TOKENS[k]]) * rate[k] for k in PRICES) / _MILLION, None


def report(db, rates_path):
    """The API-equivalent estimate per model, as Markdown."""
    rates, version, errors = load_rates(rates_path)
    out = ["## API-equivalent (estimated, combined cache-write rate)", "",
           "> What this usage would cost through the provider's API, at the rates in `.orchestrator/rates.json`"
           " (version %s). It is not what a subscription (Claude Pro or Max, ChatGPT Plus) costs you: a plan has"
           " no per-token price. Anthropic cache writes: the transcripts give the 5-minute and 1-hour cache writes"
           " as one figure, valued at the single, combined `cache_write` rate of the rates file, so this is an"
           " estimate, not the API's actual charge. Only usage the runtime reported is priced." % (version or "—"),
           ""]
    if not rates:
        out.append("No rates in `.orchestrator/rates.json`: add the provider's published prices, each with the date"
                   " it applies from and its source, to see an estimate.")
        out += ["", "Rates left out: " + "; ".join(errors)] if errors else []
        return "\n".join(out) + "\n"
    rows = db.execute(
        "SELECT coalesce(u.model, i.model), i.runtime, substr(coalesce(i.started_at, u.captured_at), 1, 10), "
        "u.source, u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens "
        "FROM usage_records u LEFT JOIN agent_invocations i ON i.invocation_id = u.invocation_id")
    per_model, totals = {}, {}
    for model, runtime, day, source, *tokens in rows:
        m = per_model.setdefault(model or "unknown", {"n": 0, "priced": 0, "cost": {}, "rates": set(),
                                                       "why": set()})
        m["n"] += 1
        usage = dict(zip(_TOKENS.values(), tokens), source=source)
        rate = rate_for(rates, PROVIDER.get(runtime), model, day or "")
        cost, why = estimate(runtime, usage, rate)
        if cost is None:
            m["why"].add(why)
            continue
        m["priced"] += 1
        m["cost"][rate["currency"]] = m["cost"].get(rate["currency"], 0) + cost
        totals[rate["currency"]] = totals.get(rate["currency"], 0) + cost
        m["rates"].add("%s · from %s · %s" % (version, rate["effective_from"], rate["source"]))
    out += ["| Model | Invocations | Priced | API-equivalent (estimated) | Rate or why not |", "|---|---|---|---|---|"]
    for model, m in sorted(per_model.items()):
        cost = ", ".join("%s %s" % (c, v.quantize(_CENT)) for c, v in sorted(m["cost"].items())) or "—"
        note = "; ".join(sorted(m["rates"])) or "; ".join(sorted(m["why"]))
        out.append("| %s | %d | %d | %s | %s |" % (model, m["n"], m["priced"], cost, note))
    out += ["", "Total (priced invocations only): " + (", ".join(
        "%s %s" % (c, v.quantize(_CENT)) for c, v in sorted(totals.items())) or "—")]
    out += ["", "Rates left out: " + "; ".join(errors)] if errors else []
    return "\n".join(out) + "\n"
