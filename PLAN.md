# PLAN.md

## Architecture

**Input:** CSV with `company_name` + `mailing_address`.
**Output:** Same rows enriched with `contact_name`, `contact_role`, `contact_email_or_phone`, `confidence_score`, `source`, `needs_human_review`.

An orchestrator agent accepts a row, fans out to N lookup tools (MCP-backed), collects results, merges them, scores confidence, and writes the output row.

Data flow (per row):
1. Normalize company name + address.
2. Fan out to each provider in parallel.
3. Merge results: if multiple sources return the same name/contact → confidence increases; single unverifiable source → confidence stays low.
4. If confidence < threshold → emit empty contact + `needs_human_review = true`.
5. Write output row with provenance (`source_url` per field).

<!-- GAPS — needs answers before building:
  - What is the execution model? Batch (process all rows at once) or one-at-a-time CLI call?
  - If a source times out or errors, does the row fail entirely or continue with remaining sources?
  - Is there intermediate storage (DB, JSON file) or is it pure CSV-in → CSV-out?
-->

## Sources & strategy

- **Business registry** (government/state-level): cross-reference mailing address → registered agent / owner name. Most authoritative for ownership; often missing for very small businesses.
- **Web/maps listing** (Google Maps or equivalent): look up company name + address → public business phone, sometimes a contact name. May return only a generic listing with no person.
- **Email/phone enrichment provider**: given company name/domain → candidate email or phone with provider-reported confidence. Individually fallible; treat as a signal, not a fact.

Cross-referencing strategy: agreement between sources raises confidence. A contact only from enrichment with no corroboration stays low-confidence.

Only public, business-facing data. Check terms of service before using any real source.

<!-- GAPS — needs answers before building:
  - What is the priority order when multiple sources return different people? (e.g., registry says Owner, enrichment says CFO)
  - How should conflicting names be handled — pick highest-confidence source, flag for review, or surface all candidates?
  - Are there specific disallowed source types (LinkedIn scraping, paid databases)?
-->

## Quality

**Confidence score logic (0–100):**
- Start at 0.
- Each independent source that returns a contact: +points (exact weight TBD).
- Sources that agree on the same name/contact: multiplier or bonus.
- `provider_confidence` from enrichment provider is a signal, not the final score.
- Single unverifiable source with no corroboration → score stays below threshold.

**"Cannot verify" representation:** `confidence_score < threshold` → `contact_email_or_phone = ""`, `needs_human_review = true`. Never fabricate a contact.

**Provenance:** every output field carries a `source` column listing the `source_url(s)` it came from. No value emitted without an attributable source.

**Dedupe:** if two sources return the same person (name fuzzy-match + same company), merge into one candidate and boost confidence rather than returning duplicates.

<!-- GAPS — needs answers before building:
  - What exact confidence threshold separates "emit contact" from "needs_human_review"? (likely 70, but confirm)
  - What scoring weight difference between "one agreeing source" vs "two agreeing sources"?
  - How strict is name deduplication? Exact match only, or fuzzy (e.g., "Dan Ortega" vs "Daniel Ortega")?
  - What happens if two sources agree on the same name but give conflicting emails?
-->

## Privacy / compliance

**Will do:**
- Use only publicly available, business-facing data (B2B contacts only).
- Record provenance (`source_url`) for every value so any contact can be audited.
- Support suppression: skip rows where company/contact is on an opt-out list.
- Check terms of service for each data source before using it in production.

**Will NOT do:**
- Collect personal/home addresses or personal phone numbers.
- Infer identity from protected characteristics.
- Use dark-pattern scraping (bypassing robots.txt, fake user agents, login walls).
- Store more data than needed to produce the output.

<!-- GAPS — needs answers before building:
  - Is there an existing suppression/opt-out list to check against, or does this need to be built?
  - What jurisdiction applies — US only, EU (GDPR), or both?
  - What is the data retention policy for enriched output — delete after use, or store in a DB?
-->

## Clarifying questions

1. **Who is the target decision-maker when multiple roles are present?**
   - Why it matters: if registry returns an Owner and enrichment returns a CFO, I need a priority order to pick one.
   - Default assumption: Owner / founder first for small businesses; AP manager or CFO for larger ones.
   - What changes if answered: the merge/selection logic in step 3 of the data flow.

2. **What is the confidence threshold for "needs_human_review"?**
   - Why it matters: the threshold determines how many rows get flagged vs. emitted — directly sets precision/recall trade-off.
   - Default assumption: 70 out of 100.
   - What changes if answered: the scoring cutoff in the output step; may also change how aggressively I boost single-source results.

3. **Are we optimizing for precision (fewer, more accurate contacts) or recall (more contacts, some uncertain)?**
   - Why it matters: it changes whether I should emit a low-confidence guess or leave the row blank and flag it.
   - Default assumption: precision over recall — a high `needs_human_review` rate on genuinely hard rows is acceptable.
   - What changes if answered: the threshold itself, and whether I surface multiple candidates per row.
