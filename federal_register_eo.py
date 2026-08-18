#!/usr/bin/env python3
"""National emergencies declared, Federal Register API (keyless), a DERIVED
COUNT with the rules printed on the card. v3 register #31.

No agency maintains an official list of National Emergencies Act declarations,
so the count is derived from the primary documents themselves, Federal
Register presidential documents, under three printed rules:

  RULE 1 (include): presidential documents whose full text contains the NEA's
    performative phrase, a declaration says "hereby declare a national
    emergency" (or "declare a national emergency"). Tariff/sanctions EOs that
    declare emergencies inside longer titles are caught this way; documents
    merely MENTIONING an emergency are not, because the phrase is the legal
    act itself.
  RULE 2 (exclude): annual "Continuation of the National Emergency ..."
    notices (they renew old emergencies; titles are standardised).
  RULE 3 (exclude): terminations / revocations.

Counts are reconciled against the Brennan Center's tracker (a labelled
cross-check, never the source of record, doc 04). If the derived count and
the cross-check diverge by more than the validator's max_jump the run fails
loudly and a rule gets reviewed, not fudged.

Same API family as the executive-orders connector (proven since v1). Closed
prior terms are backfilled once and carried forward, like EO curves."""
import os
import re
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, load_existing  # noqa: E402

API = "https://www.federalregister.gov/api/v1/documents.json"
TERM_START = datetime.date(2025, 1, 20)
PHRASE = "declare a national emergency"
CONTINUATION = re.compile(r"^\s*continuation of", re.I)
TERMINATION = re.compile(r"terminat|revocation of the national emergency", re.I)

# Closed prior terms for same-point context (one-time backfill, carried forward)
PREV_TERMS = {"biden": ("joe-biden", datetime.date(2021, 1, 20), datetime.date(2025, 1, 19)),
              "trump1": ("donald-trump", datetime.date(2017, 1, 20), datetime.date(2021, 1, 19)),
              "obama": ("barack-obama", datetime.date(2009, 1, 20), datetime.date(2013, 1, 19))}


def fetch_documents(president, gte, lte=None):
    """All presidential docs full-text-matching the NEA phrase for a president
    in a window: [{title, signing/publication date}]."""
    docs, page = [], 1
    while True:
        params = {
            "conditions[term]": f'"{PHRASE}"',
            "conditions[president]": president,
            "conditions[type]": "PRESDOCU",
            "conditions[publication_date][gte]": gte.isoformat(),
            "fields[]": ["title", "signing_date", "publication_date", "document_number"],
            "per_page": 300, "page": page,
        }
        if lte:
            params["conditions[publication_date][lte]"] = (lte + datetime.timedelta(days=45)).isoformat()
        r = requests.get(API, params=params, timeout=60)
        r.raise_for_status()
        js = r.json()
        docs += js.get("results", []) or []
        if page >= (js.get("total_pages") or 1):
            break
        page += 1
    return docs


def declarations(docs, gte, lte=None):
    """Apply the printed rules; return [{date, title}] of NEW declarations,
    deduped by document, dated by signing date (publication as fallback)."""
    out, seen = [], set()
    for d in docs:
        title = (d.get("title") or "").strip()
        num = d.get("document_number")
        if num in seen:
            continue
        seen.add(num)
        if CONTINUATION.search(title) or TERMINATION.search(title):
            continue
        ds = d.get("signing_date") or d.get("publication_date")
        if not ds:
            continue
        day = datetime.date.fromisoformat(ds)
        if day < gte or (lte and day > lte):
            continue
        out.append({"date": ds, "title": title})
    return sorted(out, key=lambda x: x["date"])


def cumulative_by_month(items, start):
    per = {}
    for it in items:
        per[it["date"][:7]] = per.get(it["date"][:7], 0) + 1
    out, cum = [], 0
    first = start.strftime("%Y-%m")
    for ym in sorted(set(per) | {first}):
        cum += per.get(ym, 0)
        out.append({"date": ym, "value": cum})
    return out


def prev_term_counts(existing):
    """Same-point + full-term counts for closed terms; fetched once."""
    have = (existing or {}).get("prev_terms") or {}
    if all(k in have for k in PREV_TERMS):
        return have
    counts = dict(have)
    for pid, (slug, start, end) in PREV_TERMS.items():
        if pid in counts:
            continue
        try:
            decls = declarations(fetch_documents(slug, start, lte=end), start, lte=end)
            days_in = (datetime.date.today() - TERM_START).days
            same_point = sum(1 for d in decls
                             if (datetime.date.fromisoformat(d["date"]) - start).days <= days_in)
            counts[pid] = {"full_term": len(decls), "same_point": same_point}
            print(f"  ✓ national_emergencies: backfilled {pid} ({len(decls)} full term, {same_point} at same point)")
        except Exception as e:  # noqa: BLE001
            print(f"  ! national_emergencies: {pid} backfill failed this run ({e}), will retry")
    return counts


def main():
    docs = fetch_documents("donald-trump", TERM_START)
    decls = declarations(docs, TERM_START)
    series = cumulative_by_month(decls, TERM_START)

    out = {
        "id": "national_emergencies", "name": "National emergencies declared",
        "category": "Executive Power & Governance", "value": len(decls), "unit": "declarations",
        "as_of": datetime.date.today().isoformat(), "since": TERM_START.isoformat(),
        "direction": "neutral",
        "declarations": decls,  # dates + titles: the receipts behind the count
        "source": {"name": "Federal Register (derived count, rules on the card)",
                   "url": "https://www.federalregister.gov/presidential-documents"},
        "cadence": "As signed", "stale_days": 45,
        "note": "New national emergencies declared under the National Emergencies Act, "
                "counted from Federal Register presidential documents containing the "
                "declaring phrase; annual continuations and terminations excluded. A "
                "derived count with the rules stated, no official list exists.",
    }
    prev = prev_term_counts(load_existing("national_emergencies"))
    if prev:
        out["prev_terms"] = prev
    publish(out, series=series)


if __name__ == "__main__":
    main()
