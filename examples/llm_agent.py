"""An LLM agent through a local Ollama server (inference only, no training). Standard library only.

    ollama pull qwen2.5:1.5b
    python -m auditgym.cli run-agent --name qwen --cmd "python examples/llm_agent.py --model qwen2.5:1.5b" --split dev

Protocol: one observation (JSON) per line on stdin, one action (JSON) per line on stdout. The model sees the
task, the tools, the finding rules and a short history, and must answer with one JSON action. If the model
or the server fails, the agent submits what it has (possibly nothing): an honest result, never a crash.
Options: --model, --host (default http://127.0.0.1:11434), --temperature, --max-tokens, --history.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

SYSTEM = ("You are a financial audit agent in a sandbox. Investigate the books with the tools and then submit "
          "findings. Reply with ONE JSON object only, exactly {\"tool\": <name>, \"args\": {...}}. No prose.")


def ask(opts, messages):
    body = {"model": opts.model, "messages": messages, "stream": False, "format": "json",
            "options": {"temperature": opts.temperature, "num_predict": opts.max_tokens}}
    req = urllib.request.Request(opts.host.rstrip("/") + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=opts.timeout) as r:
        return json.loads(r.read())["message"]["content"]


def short(obs, limit=2500):
    text = json.dumps(obs, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " …(truncated)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--history", type=int, default=6, help="how many recent steps the model sees")
    ap.add_argument("--timeout", type=float, default=90)
    opts = ap.parse_args()
    episode_id, intro, history = None, "", []
    for line in sys.stdin:
        obs = json.loads(line)
        res = obs.get("result") if isinstance(obs.get("result"), dict) else {}
        if "manifest" in res:
            episode_id = res["manifest"]["episode_id"]
            intro = json.dumps({k: res.get(k) for k in ("task", "tools", "policy", "finding_schema", "finding_rules", "manifest")},
                               ensure_ascii=False)
            history = []
        else:
            history.append({"role": "user", "content": "Observation: " + short(obs)})
        left = obs.get("remaining_steps", 100)
        empty = {"tool": "submit", "args": {"findings": {"episode_id": episode_id, "findings": []}}}
        action = empty
        if left > 2:
            messages = [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"Episode setup: {intro}\nSteps left: {left}. episode_id = {episode_id}"}]
            messages += history[-2 * opts.history:]
            try:
                reply = ask(opts, messages)
                cand = json.loads(reply)
                if isinstance(cand, dict) and isinstance(cand.get("tool"), str):
                    action = cand
                    history.append({"role": "assistant", "content": reply})
            except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
                print(f"llm_agent: {exc}; submitting what we have", file=sys.stderr)
        if action.get("tool") == "submit":
            f = action.setdefault("args", {}).get("findings")
            if isinstance(f, dict):
                f["episode_id"] = episode_id
            elif isinstance(f, list):
                action["args"]["findings"] = {"episode_id": episode_id, "findings": f}
        sys.stdout.write(json.dumps(action, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
