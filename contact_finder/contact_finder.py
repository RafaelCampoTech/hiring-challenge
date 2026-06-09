import csv
import json
import os
import re

from rapidfuzz import fuzz

NAME_SIMILARITY_THRESHOLD = 70

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
MOCKS_PATH  = os.path.join(REPO_ROOT, 'challenge', 'mocks', 'enrichment_responses.json')
CSV_PATH    = os.path.join(REPO_ROOT, 'challenge', 'data', 'companies.csv')
OUTPUT_PATH = os.path.join(REPO_ROOT, 'output', 'results.csv')

OUTPUT_FIELDS = [
    'company_name', 'mailing_address', 'contact_name', 'contact_role',
    'contact_email_or_phone', 'confidence_score', 'source', 'needs_human_review',
]

CONFIDENCE_THRESHOLD = 70

 
def load_mocks(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_csv(path: str) -> list:
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

 
def _remove_titles_from_name(name: str) -> str:
    return re.sub(r'\b(dr|mr|mrs|ms|prof)\.?\s*', '', name, flags=re.IGNORECASE).strip()


def _normalize_name(name: str) -> str:
    name = _remove_titles_from_name(name.lower())
    return name.strip()


def name_similarity(a: str, b: str) -> float:
    """Semantic similarity between two name strings (0–100).

    Uses token_set_ratio so that shared tokens like a last name anchor the
    score even when first names differ (e.g. 'Robert Kowalski' vs 'Bob Kowalski' → 81).
    Titles are stripped and names are lowercased before comparison.
    """
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(_normalize_name(a), _normalize_name(b))


def names_agree(a: str, b: str) -> bool:
    """True if two name strings are semantically similar enough to be the same person."""
    return name_similarity(a, b) >= NAME_SIMILARITY_THRESHOLD


def name_matches_email(name: str, email: str) -> bool:
    """True if the person's first initial + last name appear in the email local part."""
    if not name or not email:
        return False
    local = re.sub(r'[.\-_]', '', email.split('@')[0].lower())
    parts = _normalize_name(name).split()
    if not parts:
        return False
    last = parts[-1]
    first_initial = parts[0][0] if len(parts) > 1 else ''
    return last in local and (not first_initial or first_initial in local)



def compute_confidence(registry, listing, enrichment) -> int:
    score = 0

    if registry and registry.get('name'):
        score += 40

    if listing:
        if listing.get('phone'):
            score += 20
        if listing.get('name'):
            score += 5

    if enrichment:
        has_contact = enrichment.get('email') or enrichment.get('phone')
        if has_contact:
            provider_conf = enrichment.get('provider_confidence') or 0
            score += round(provider_conf * 0.35)

    # Cross-source agreement bonuses
    reg_name  = (registry   or {}).get('name')
    list_name = (listing    or {}).get('name')
    list_phone = (listing   or {}).get('phone')
    enr_email  = (enrichment or {}).get('email')
    enr_phone  = (enrichment or {}).get('phone')

    if reg_name and list_name:
        sim = name_similarity(reg_name, list_name)
        if sim >= NAME_SIMILARITY_THRESHOLD:
            score += round(sim / 100 * 10)   # 7–10 pts scaled by similarity

    if reg_name and enr_email and name_matches_email(reg_name, enr_email):
        score += 10

    if list_phone and enr_phone and list_phone == enr_phone:
        score += 5

    return min(score, 100)



def select_contact(registry, listing, enrichment, score: int) -> tuple:
    """Return (contact_name, contact_role, contact_email_or_phone, source, needs_human_review)."""
    reg_name   = (registry   or {}).get('name')   or ''
    list_name  = (listing    or {}).get('name')   or ''
    reg_role   = (registry   or {}).get('role')   or ''
    enr_email  = (enrichment or {}).get('email')  or ''
    enr_phone  = (enrichment or {}).get('phone')  or ''
    list_phone = (listing    or {}).get('phone')  or ''

    contact_name = reg_name or list_name
    contact_role = reg_role

    # Collect all source_urls that contributed a non-null signal
    sources = []
    if registry and (registry.get('name') or registry.get('role')):
        sources.append(registry['source_url'])
    if listing and (listing.get('name') or listing.get('phone')):
        sources.append(listing['source_url'])
    if enrichment and (enrichment.get('email') or enrichment.get('phone')):
        sources.append(enrichment['source_url'])
    source = ' | '.join(sources)

    if score < CONFIDENCE_THRESHOLD:
        return contact_name, contact_role, '', source, True

    # Priority: enrichment email > enrichment phone > listing phone
    contact = enr_email or enr_phone or list_phone
    return contact_name, contact_role, contact, source, False


# ---------------------------------------------------------------------------
# Row processor
# ---------------------------------------------------------------------------

def find_mock_providers(company_name: str, mocks: dict) -> dict:
    """Return the mock providers for the best-matching company name (similarity >= 80)."""
    best_key, best_score = None, 0.0
    for key in mocks:
        score = name_similarity(company_name, key)
        if score > best_score:
            best_score, best_key = score, key
    return mocks[best_key] if best_score >= 80 else {}


def process_row(company_name: str, mailing_address: str, mocks: dict) -> dict:
    providers  = find_mock_providers(company_name, mocks)
    registry   = providers.get('registry')
    listing    = providers.get('listing')
    enrichment = providers.get('enrichment')

    score = compute_confidence(registry, listing, enrichment)
    contact_name, contact_role, contact, source, needs_review = select_contact(
        registry, listing, enrichment, score
    )

    return {
        'company_name':            company_name,
        'mailing_address':         mailing_address,
        'contact_name':            contact_name,
        'contact_role':            contact_role,
        'contact_email_or_phone':  contact,
        'confidence_score':        score,
        'source':                  source,
        'needs_human_review':      str(needs_review).lower(),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_output(rows: list, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    mocks    = load_mocks(MOCKS_PATH)
    companies = load_csv(CSV_PATH)

    results = []
    for row in companies:
        result = process_row(row['company_name'], row['mailing_address'], mocks)
        results.append(result)

        flag = '⚠' if result['needs_human_review'] == 'true' else '✓'
        print(f"{flag}  [{result['confidence_score']:>3}]  {row['company_name']:<35}  {result['contact_name'] or '—'}")

    write_output(results, OUTPUT_PATH)
    print(f'\nWrote {len(results)} rows → {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
