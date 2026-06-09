# PLAN_v2.md — Stage B Implementation

## What we built

A single Python script (`contact_finder/contact_finder.py`) that reads `challenge/data/companies.csv`, queries the three mock providers in `challenge/mocks/enrichment_responses.json`, scores each company, and writes an enriched CSV to `output/results.csv`.

**Dependency:** [`rapidfuzz`](https://github.com/rapidfuzz/RapidFuzz) for semantic name similarity. Managed via a local venv — no global install needed.

---

## How to run

```bash
just run    # auto-creates venv + installs deps on first run, then executes
just show   # display output/results.csv as a formatted table (q to exit)
just all    # run then show
```

`just run` is self-contained: it checks whether `contact_finder/.venv` exists and creates it (+ runs `pip install`) only if it does not. Subsequent runs skip setup entirely.

---

## File layout

```
contact_finder/
  contact_finder.py    # all logic
  requirements.txt     # rapidfuzz
  .venv/               # created by just run (gitignored)
output/
  results.csv          # written by the script
Justfile               # task runner
```

---

## Data reality (from reading the mocks)

30 companies in the CSV. 18 have mock data; 12 have no entry at all (intentional "cannot verify" rows). Among the 18:

| Pattern | Examples | Score |
|---|---|---|
| All 3 sources agree | Cedar Ridge, Pioneer, Ironclad, Brookside | 100 |
| Registry + enrichment, name matches email | Greenfield, Tidewater | 75–77 |
| Registry + enrichment, first-name-only email | Bayview Auto | 67 → review |
| Registry + listing, names agree | Harbor Light | 73 |
| Listing + enrichment, weak confidence | Sunbelt, Lakeside | 45–48 |
| Enrichment only, low provider_confidence | Riverside (41%), Summit (38%), Hometown (44%) | 13–15 |
| Registry only, no contact detail | Northgate HVAC | 40 |
| Listing only | Maple Leaf Bakery | 20 |
| Conflicting registry vs listing names | Coastal Breeze Pool | 65 → review |
| No mock entry | 12 companies | 0 |

---

## Output schema

One row per input company.

| Column | Type | Description |
|---|---|---|
| `company_name` | string | From input CSV |
| `mailing_address` | string | From input CSV |
| `contact_name` | string | Registry name → listing name → empty |
| `contact_role` | string | From registry, or empty |
| `contact_email_or_phone` | string | Empty when `confidence_score < 70` |
| `confidence_score` | int 0–100 | See scoring algorithm below |
| `source` | string | Pipe-separated `source_url` values that contributed |
| `needs_human_review` | `true`/`false` | true when score < 70 |

---

## Implementation: function map

```
load_mocks(path)               → dict          load enrichment_responses.json
load_csv(path)                 → list[dict]    load companies.csv

_normalize_name(name)          → str           lowercase + strip titles (Dr., Mr., …)
name_similarity(a, b)          → float 0–100   rapidfuzz.fuzz.token_set_ratio on normalized names
names_agree(a, b)              → bool          name_similarity >= 70
name_matches_email(name, email)→ bool          first initial + last name in email local part

find_mock_providers(name, mocks) → dict        fuzzy company-name lookup (similarity >= 80)
compute_confidence(r, l, e)    → int           base scores + cross-source bonuses (capped 100)
select_contact(r, l, e, score) → tuple         name, role, contact, source, needs_review
process_row(name, addr, mocks) → dict          one output row
write_output(rows, path)                       write CSV
main()                                         load → iterate → process → write
```

---

## Confidence scoring algorithm

```
score = 0

# Base scores
if registry.name:                          score += 40   # most authoritative
if listing.phone:                          score += 20
if listing.name:                           score += 5
if enrichment has email or phone:          score += round(provider_confidence * 0.35)  # max 35

# Cross-source agreement bonuses
sim = name_similarity(registry.name, listing.name)
if sim >= 70:                              score += round(sim / 100 * 10)  # 7–10 pts, scaled

if name_matches_email(registry.name, enrichment.email):
                                           score += 10

if listing.phone == enrichment.phone:      score += 5

score = min(score, 100)
```

**`name_similarity`** uses `rapidfuzz.fuzz.token_set_ratio` on lowercased, title-stripped strings.
`token_set_ratio` handles nicknames ("Bob" vs "Robert"), initials ("S. Murphy" vs "Sean Murphy"), and
partial names correctly. Measured scores on the real mock data:

| Pair | Score |
|---|---|
| Daniel Ortega / Daniel Ortega | 100 |
| Sean Murphy / S. Murphy | 80 |
| Robert Kowalski / Bob Kowalski | 81 |
| Dr. Emily Hart / Emily Hart | 100 (after title strip) |
| Tina Alvarez / Marcus Webb | 26 |

**`name_matches_email`** is a structural check: strips dots/hyphens from the local part, then checks
whether the person's last name and first initial both appear in it.
Example: `"George Whitfield"` → last=`whitfield`, initial=`g` → matches `g.whitfield@…`.
A first-name-only email like `karen@bayviewauto.com` correctly scores 0 (explains Bayview's 67).

**`find_mock_providers`** uses `name_similarity` to fuzzy-match the CSV company name against mock
keys (threshold 80). Handles missing suffixes ("Ironclad Welding" → "Ironclad Welding Shop"),
abbreviations ("Brookside Vet Clinic" → "Brookside Veterinary Clinic"), and rejects genuinely
unknown companies.

---

## Contact selection

If `confidence_score < 70`:
- `contact_email_or_phone = ""`
- `needs_human_review = true`

If `confidence_score >= 70`, first available wins:
1. `enrichment.email`
2. `enrichment.phone`
3. `listing.phone`

---

## Edge cases

| Case | Handling |
|---|---|
| Company not in mocks (12 rows) | `find_mock_providers` returns `{}` → score = 0 → review |
| Company name slightly different from mock key | Fuzzy match ≥ 80 still resolves it |
| Provider key present but all fields null | Treated as absent for that provider |
| `enrichment.provider_confidence` null | Contributes 0 to score |
| Conflicting registry vs listing names (Coastal Breeze) | Similarity 26 → no agreement bonus → score 65 → review |
| Registry name but no contact detail (Northgate HVAC) | Score 40 → review, name still shown |
| First-name-only enrichment email (Bayview) | `name_matches_email` returns false → no +10 → score 67 → review |
