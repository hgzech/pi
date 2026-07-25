#!/usr/bin/env python3
"""
major_buckets.py -- deterministic candidate pools for a two-digit major system.

Encoding rules implemented:
    0 = s/z        5 = l
    1 = t/d        6 = ch/sh/j/zh
    2 = n/ng       7 = k/g
    3 = m          8 = f/v
    4 = r          9 = p/b

  th, dh, w, h, y and all vowels are BLANK (jokers).
  A word encodes to its FIRST TWO digit-bearing consonants.
  A word with exactly ONE digit-bearing consonant DOUBLES it (Athena -> 22).
  A word with none is inert and dropped.

Works from phonemes, not spelling, so silent letters and digraphs are handled:
    Descartes -> D K      -> 17
    Ptolemy   -> T L M    -> 15
    sugar     -> SH G     -> 67
    taxi      -> T K S    -> 17
    toothpick -> T TH P K -> 19

Words with more than one CMUdict pronunciation that encode differently
(tsunami: 10 or 02) are kept but marked "amb": true -- those are the only
errors that do not self-cancel, since you may say them either way.

Inputs
------
CMUdict:      pip install cmudict
Concreteness: Brysbaert, Warriner & Kuperman (2014) norms, ~40k lemmas.
              The Ghent link in the paper is dead; use the mirror:

  curl -O https://raw.githubusercontent.com/ArtsEngine/concreteness/master/Concreteness_ratings_Brysbaert_et_al_BRM.txt
  mv Concreteness_ratings_Brysbaert_et_al_BRM.txt concreteness.tsv

              Optional -- without it you get everything, abstract words and
              ~40k US surnames included. Strongly recommended.

Note on --min-conc: default 3.0 is deliberately loose. The LLM stage curates,
so a dud costs one dropped word while an omission costs recall you never see.
4.0 is defensible for the rich buckets but starves the thin ones (83 drops to
eight candidates).

Usage
-----
    python major_buckets.py                       # writes buckets.json
    python major_buckets.py --min-conc 3.5        # looser vividness cut
    python major_buckets.py --per-bucket 250      # cap candidates per bucket
"""

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import cmudict

PHONEME_DIGIT = {
    "S": "0", "Z": "0",
    "T": "1", "D": "1",
    "N": "2", "NG": "2",
    "M": "3",
    "R": "4", "ER": "4",          # ER is r-coloured: butter -> B T R -> 91
    "L": "5",
    "CH": "6", "JH": "6", "SH": "6", "ZH": "6",
    "K": "7", "G": "7",
    "F": "8", "V": "8",
    "P": "9", "B": "9",
}
# Everything else -- TH DH W Y HH and all vowels -- is blank by omission.

STRESS = re.compile(r"\d")


def encode(phones):
    """Phoneme list -> two-digit code, or None if inert."""
    digits = [PHONEME_DIGIT[p] for p in phones if p in PHONEME_DIGIT]
    if len(digits) >= 2:
        return digits[0] + digits[1]
    if len(digits) == 1:
        return digits[0] * 2
    return None


def encode_word(word, pron_dict=None):
    """Convenience: encode a single spelled word. Returns (code, ambiguous)."""
    d = pron_dict if pron_dict is not None else cmudict.dict()
    prons = d.get(word.lower().strip())
    if not prons:
        return None, False
    codes = []
    for pron in prons:
        c = encode([STRESS.sub("", p) for p in pron])
        if c:
            codes.append(c)
    if not codes:
        return None, False
    return codes[0], len(set(codes)) > 1


def load_concreteness(path):
    conc = {}
    p = Path(path)
    if not p.exists():
        return conc
    with p.open(newline="", encoding="utf-8-sig") as f:
        head = f.readline()
        f.seek(0)
        delim = "\t" if "\t" in head else ","
        for row in csv.DictReader(f, delimiter=delim):
            w = (row.get("Word") or "").strip().lower()
            try:
                conc[w] = float(row["Conc.M"])
            except (KeyError, TypeError, ValueError):
                continue
    return conc


def build(min_conc=3.0, per_bucket=300, conc_path="concreteness.tsv"):
    conc = load_concreteness(conc_path)
    if not conc:
        print("! no concreteness file found -- abstract words will be included")

    d = cmudict.dict()
    buckets = defaultdict(list)

    for word, prons in d.items():
        if len(word) < 2 or not word.isalpha():
            continue                      # drops "a", initials, entries like "won't"

        codes = []
        for pron in prons:
            c = encode([STRESS.sub("", p) for p in pron])
            if c:
                codes.append(c)
        if not codes:
            continue                      # inert: eye, yo-yo, hay

        score = conc.get(word)
        if conc:
            if score is None or score < min_conc:
                continue

        buckets[codes[0]].append({
            "w": word,
            "c": round(score, 2) if score is not None else None,
            "amb": len(set(codes)) > 1,
        })

    out = {}
    for code in (f"{n:02d}" for n in range(100)):
        items = buckets.get(code, [])
        items.sort(key=lambda x: (x["c"] is None, -(x["c"] or 0), x["w"]))
        out[code] = items[:per_bucket]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-conc", type=float, default=3.0)
    ap.add_argument("--per-bucket", type=int, default=300)
    ap.add_argument("--conc", default="concreteness.tsv")
    ap.add_argument("--out", default="buckets.json")
    args = ap.parse_args()

    buckets = build(args.min_conc, args.per_bucket, args.conc)
    Path(args.out).write_text(json.dumps(buckets, indent=1), encoding="utf-8")

    sizes = {k: len(v) for k, v in buckets.items()}
    total = sum(sizes.values())
    thin = sorted(sizes.items(), key=lambda kv: kv[1])[:12]
    print(f"wrote {args.out}: {total} candidates across 100 buckets")
    print("thinnest:", ", ".join(f"{k}={n}" for k, n in thin))


if __name__ == "__main__":
    main()
