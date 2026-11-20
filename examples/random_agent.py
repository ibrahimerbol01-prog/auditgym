"""The smallest external agent: reads observations (one JSON per line) on stdin, writes actions on stdout.

    python -m auditgym.cli run-agent --cmd "python examples/random_agent.py" --split dev

It reads a few random pages, then accuses 0-2 of the IDs it has seen. Expect a score near -1: it is the
floor to compare real agents against. Standard library only; deterministic per episode.
"""
import json
import random
import sys

TABLES = ["ledger", "invoices", "payments", "fx"]
TYPES = ["duplicate_invoice", "payment_allocation", "date_or_fx", "period_classification"]


def main() -> None:
    episode_id, seen, n, rng, base = None, [], 0, random.Random(0), "USD"
    for line in sys.stdin:
        obs = json.loads(line)
        res = obs.get("result") if isinstance(obs.get("result"), dict) else {}
        if "manifest" in res:  # first observation of the episode
            episode_id = res["manifest"]["episode_id"]
            base = res["manifest"].get("base_currency", base)
            rng = random.Random(episode_id)
        for row in res.get("rows", []):
            rid = row.get("row_id") or row.get("invoice_id") or row.get("payment_id")
            if rid:
                seen.append(rid)
        n += 1
        if n <= 4:
            action = {"tool": "list_records", "args": {"table": rng.choice(TABLES), "cursor": None, "limit": 50}}
        else:
            picks = rng.sample(seen, min(len(seen), rng.randint(0, 2)))
            findings = [{"type": rng.choice(TYPES), "affected_ids": [p], "claimed_amount_minor": rng.randint(1, 10 ** 6),
                         "currency": base, "evidence_ids": [p], "explanation": "random guess"} for p in picks]
            action = {"tool": "submit", "args": {"findings": {"episode_id": episode_id, "findings": findings}}}
        sys.stdout.write(json.dumps(action) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
