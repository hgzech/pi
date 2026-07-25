#!/usr/bin/env python3
"""
run_batch.py -- send one Batch API request per two-digit bucket.

One call per bucket, so nothing accumulates across buckets and every call
holds a single fixed constraint. Batch API is 50% off and returns within
24h (usually far sooner).

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...

    python run_batch.py submit                    # all 100 buckets
    python run_batch.py submit --only 10-19       # one decade
    python run_batch.py submit --pass 2           # second run, different seed
    python run_batch.py fetch msgbatch_01ABC...   # writes pegs/<code>.md

Running `submit` two or three times with different --pass values and taking
the union is the cheapest way to broaden the lists -- at these prices it is
less effort than tuning the prompt.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from anthropic import Anthropic

MODEL = "claude-opus-5"
# Thinking tokens count against max_tokens, so leave real headroom:
# at effort=high the reasoning alone can run several thousand.
MAX_TOKENS = 64000
# Opus 5 thinks by default; effort is the only knob.
# Levels: low, medium, high, xhigh, max.
EFFORT = "high"

# Nudges to diversify repeat passes. Union the outputs afterwards.
PASS_HINTS = {
    1: "",
    2: ("\n\nThis is a second pass. Favour entries a first pass would likely "
        "miss: obscure mythology, historical figures, tools and machines, "
        "regional food, slang and taboo vocabulary, multiword images."),
    3: ("\n\nThis is a third pass. Favour proper nouns above all: named "
        "characters from film, opera, literature and games; landmarks; "
        "brands; specific animals and cultivars; historical persons."),
}


def load_buckets(path="buckets.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_only(spec):
    if not spec:
        return [f"{n:02d}" for n in range(100)]
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += [f"{n:02d}" for n in range(int(a), int(b) + 1)]
        else:
            out.append(f"{int(part):02d}")
    return out


def build_requests(buckets, codes, system, hint, cap, effort=EFFORT):
    reqs = []
    for code in codes:
        cands = [c["w"] for c in buckets.get(code, [])][:cap]
        amb = [c["w"] for c in buckets.get(code, []) if c["amb"]][:cap]
        body = [f"Bucket {code}."]
        if cands:
            body.append("Script candidates (already sound-filtered to this "
                        "bucket, ranked by concreteness):\n" + ", ".join(cands))
        else:
            body.append("The script found no candidates. Generate from scratch.")
        if amb:
            body.append("Script flagged these as having multiple pronunciations: "
                        + ", ".join(amb))
        body.append(f"Produce the {code} list now." + hint)

        reqs.append({
            "custom_id": f"b{code}",
            "params": {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "output_config": {"effort": effort},
                "system": system,
                "messages": [{"role": "user", "content": "\n\n".join(body)}],
            },
        })
    return reqs


def submit(args):
    client = Anthropic()
    system = Path(args.rules).read_text(encoding="utf-8")
    buckets = load_buckets(args.buckets)
    codes = parse_only(args.only)
    hint = PASS_HINTS.get(args.pass_no, "")

    reqs = build_requests(buckets, codes, system, hint, args.cap, args.effort)
    batch = client.messages.batches.create(requests=reqs)

    print(f"submitted {len(reqs)} requests at effort={args.effort}")
    print(f"batch id: {batch.id}")
    print(f"then:  python {sys.argv[0]} fetch {batch.id}")


def fetch(args):
    client = Anthropic()
    while True:
        batch = client.messages.batches.retrieve(args.batch_id)
        if batch.processing_status == "ended":
            break
        counts = batch.request_counts
        print(f"  {batch.processing_status}: "
              f"{counts.succeeded} done, {counts.processing} running", flush=True)
        time.sleep(20)

    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)
    ok = failed = 0
    in_tok = out_tok = 0

    for result in client.messages.batches.results(args.batch_id):
        code = result.custom_id.lstrip("b")
        if result.result.type != "succeeded":
            err = getattr(result.result, "error", None)
            detail = ""
            if err is not None:
                inner = getattr(err, "error", err)
                detail = f" | {getattr(inner, 'type', '?')}: {getattr(inner, 'message', inner)}"
            print(f"  !! {code}: {result.result.type}{detail}")
            failed += 1
            continue
        msg = result.result.message
        text = "".join(b.text for b in msg.content if b.type == "text")
        if msg.stop_reason == "max_tokens":
            print(f"  ~~ {code}: TRUNCATED at max_tokens -- raise MAX_TOKENS and rerun")
        path = outdir / f"{code}.md"
        # append rather than overwrite, so repeat passes accumulate
        with path.open("a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")
        in_tok += msg.usage.input_tokens
        out_tok += msg.usage.output_tokens
        ok += 1

    cost = (in_tok / 1e6 * 5 + out_tok / 1e6 * 25) * 0.5   # batch = 50% off
    print(f"\n{ok} ok, {failed} failed -> {outdir}/")
    print(f"{in_tok:,} in + {out_tok:,} out  ~= ${cost:.2f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit")
    s.add_argument("--buckets", default="buckets.json")
    s.add_argument("--rules", default="rules.md")
    s.add_argument("--only", default=None, help="e.g. 10-19 or 88,38,06")
    s.add_argument("--cap", type=int, default=220,
                   help="max script candidates fed per bucket")
    s.add_argument("--pass", dest="pass_no", type=int, default=1, choices=[1, 2, 3])
    s.add_argument("--effort", default=EFFORT,
                   choices=["low", "medium", "high", "xhigh", "max"])
    s.set_defaults(func=submit)

    f = sub.add_parser("fetch")
    f.add_argument("batch_id")
    f.add_argument("--outdir", default="pegs")
    f.set_defaults(func=fetch)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
