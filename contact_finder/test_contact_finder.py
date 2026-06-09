import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from contact_finder import (
    names_agree,
    name_matches_email,
    compute_confidence,
    select_contact,
    process_row,
    load_mocks,
    CONFIDENCE_THRESHOLD,
)

MOCKS_PATH = os.path.join(os.path.dirname(__file__), '..', 'challenge', 'mocks', 'enrichment_responses.json')


# ---------------------------------------------------------------------------
# names_agree
# ---------------------------------------------------------------------------

class TestNamesAgree(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(names_agree('Daniel Ortega', 'Daniel Ortega'))

    def test_same_last_name(self):
        self.assertTrue(names_agree('Robert Kowalski', 'Bob Kowalski'))

    def test_initial_abbreviation_forward(self):
        self.assertTrue(names_agree('Sean Murphy', 'S. Murphy'))

    def test_initial_abbreviation_reversed(self):
        self.assertTrue(names_agree('S. Murphy', 'Sean Murphy'))

    def test_title_stripped(self):
        self.assertTrue(names_agree('Dr. Emily Hart', 'Emily Hart'))

    def test_different_people(self):
        self.assertFalse(names_agree('Tina Alvarez', 'Marcus Webb'))

    def test_empty_string(self):
        self.assertFalse(names_agree('', 'Daniel Ortega'))

    def test_both_empty(self):
        self.assertFalse(names_agree('', ''))


# ---------------------------------------------------------------------------
# name_matches_email
# ---------------------------------------------------------------------------

class TestNameMatchesEmail(unittest.TestCase):

    def test_initial_plus_last_name(self):
        # g.whitfield@ → first initial "g" + last "whitfield" both present
        self.assertTrue(name_matches_email('George Whitfield', 'g.whitfield@tidewaterph.com'))

    def test_initial_dot_last_name(self):
        self.assertTrue(name_matches_email('Daniel Ortega', 'd.ortega@cedarridgeplumbing.com'))

    def test_initial_dot_last_name_2(self):
        self.assertTrue(name_matches_email('Angela Brooks', 'a.brooks@greenfieldcater.com'))

    def test_first_name_only_email_returns_false(self):
        # "karen@..." has no last name "liu" → should NOT match
        self.assertFalse(name_matches_email('Karen Liu', 'karen@bayviewauto.com'))

    def test_first_name_only_email_returns_false_2(self):
        # "maria@..." has no last name "gomez"
        self.assertFalse(name_matches_email('Maria Gomez', 'maria@pioneerlandscaping.com'))

    def test_empty_name(self):
        self.assertFalse(name_matches_email('', 'someone@example.com'))

    def test_empty_email(self):
        self.assertFalse(name_matches_email('Karen Liu', ''))


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------

class TestComputeConfidence(unittest.TestCase):

    def _registry(self, name='Test Owner', role='Owner'):
        return {'name': name, 'role': role, 'source_url': 'mock://r'}

    def _listing(self, name=None, phone='+1-555-0100'):
        return {'name': name, 'phone': phone, 'source_url': 'mock://l'}

    def _enrichment(self, email='test@example.com', phone=None, confidence=80):
        return {'email': email, 'phone': phone, 'provider_confidence': confidence, 'source_url': 'mock://e'}

    def test_no_sources_returns_zero(self):
        self.assertEqual(compute_confidence(None, None, None), 0)

    def test_registry_only(self):
        score = compute_confidence(self._registry(), None, None)
        self.assertEqual(score, 40)

    def test_listing_phone_and_name(self):
        score = compute_confidence(None, self._listing(name='Jane Doe'), None)
        self.assertEqual(score, 25)  # 20 (phone) + 5 (name)

    def test_listing_phone_only(self):
        score = compute_confidence(None, self._listing(), None)
        self.assertEqual(score, 20)

    def test_enrichment_only_low_confidence(self):
        # provider_confidence 38 → round(38 * 0.35) = 13
        score = compute_confidence(None, None, self._enrichment(confidence=38))
        self.assertEqual(score, 13)

    def test_enrichment_only_high_confidence(self):
        # provider_confidence 88 → round(88 * 0.35) = 31
        score = compute_confidence(None, None, self._enrichment(confidence=88))
        self.assertEqual(score, 31)

    def test_all_three_agreeing_caps_at_100(self):
        # Registry + listing (same name) + enrichment (name in email) → should hit 100
        registry   = {'name': 'Daniel Ortega', 'role': 'Owner', 'source_url': 'mock://r'}
        listing    = {'name': 'Daniel Ortega', 'phone': '+1-402-555-0148', 'source_url': 'mock://l'}
        enrichment = {'email': 'd.ortega@test.com', 'phone': None, 'provider_confidence': 84, 'source_url': 'mock://e'}
        self.assertEqual(compute_confidence(registry, listing, enrichment), 100)

    def test_conflicting_names_no_agreement_bonus(self):
        # Registry and listing have different names → no +10 bonus
        registry = {'name': 'Tina Alvarez', 'role': 'Manager', 'source_url': 'mock://r'}
        listing  = {'name': 'Marcus Webb',  'phone': '+1-941-555-0146', 'source_url': 'mock://l'}
        score = compute_confidence(registry, listing, None)
        # 40 (registry name) + 20 (listing phone) + 5 (listing name) = 65
        self.assertEqual(score, 65)

    def test_matching_phones_across_listing_and_enrichment(self):
        phone = '+1-480-555-0133'
        listing    = {'name': None, 'phone': phone, 'source_url': 'mock://l'}
        enrichment = {'email': None, 'phone': phone, 'provider_confidence': 66, 'source_url': 'mock://e'}
        score = compute_confidence(None, listing, enrichment)
        # 20 (listing phone) + round(66*0.35)=23 + 5 (matching phones) = 48
        self.assertEqual(score, 48)

    def test_score_never_exceeds_100(self):
        registry   = {'name': 'Big Name', 'role': 'Owner', 'source_url': 'mock://r'}
        listing    = {'name': 'Big Name',  'phone': '+1-555-0100', 'source_url': 'mock://l'}
        enrichment = {'email': 'b.name@test.com', 'phone': '+1-555-0100', 'provider_confidence': 100, 'source_url': 'mock://e'}
        self.assertLessEqual(compute_confidence(registry, listing, enrichment), 100)


# ---------------------------------------------------------------------------
# select_contact
# ---------------------------------------------------------------------------

class TestSelectContact(unittest.TestCase):

    def _providers(self):
        registry   = {'name': 'Maria Gomez', 'role': 'President', 'source_url': 'mock://r'}
        listing    = {'name': 'Maria Gomez', 'phone': '+1-208-555-0175', 'source_url': 'mock://l'}
        enrichment = {'email': 'maria@pioneerlandscaping.com', 'phone': '+1-208-555-0175',
                      'provider_confidence': 88, 'source_url': 'mock://e'}
        return registry, listing, enrichment

    def test_below_threshold_returns_empty_contact(self):
        registry, listing, enrichment = self._providers()
        _, _, contact, _, needs_review = select_contact(registry, listing, enrichment, 60)
        self.assertEqual(contact, '')
        self.assertTrue(needs_review)

    def test_above_threshold_emits_enrichment_email_first(self):
        registry, listing, enrichment = self._providers()
        _, _, contact, _, needs_review = select_contact(registry, listing, enrichment, 100)
        self.assertEqual(contact, 'maria@pioneerlandscaping.com')
        self.assertFalse(needs_review)

    def test_above_threshold_falls_back_to_listing_phone(self):
        # No enrichment — should use listing phone
        registry = {'name': 'Sean Murphy', 'role': 'Owner', 'source_url': 'mock://r'}
        listing  = {'name': 'S. Murphy', 'phone': '+1-508-555-0160', 'source_url': 'mock://l'}
        _, _, contact, _, needs_review = select_contact(registry, listing, None, 75)
        self.assertEqual(contact, '+1-508-555-0160')
        self.assertFalse(needs_review)

    def test_registry_name_preferred_over_listing_name(self):
        registry = {'name': 'Robert Kowalski', 'role': 'Owner', 'source_url': 'mock://r'}
        listing  = {'name': 'Bob Kowalski', 'phone': '+1-555-0100', 'source_url': 'mock://l'}
        name, _, _, _, _ = select_contact(registry, listing, None, 75)
        self.assertEqual(name, 'Robert Kowalski')

    def test_role_comes_from_registry(self):
        registry, listing, enrichment = self._providers()
        _, role, _, _, _ = select_contact(registry, listing, enrichment, 100)
        self.assertEqual(role, 'President')

    def test_sources_include_all_contributors(self):
        registry, listing, enrichment = self._providers()
        _, _, _, source, _ = select_contact(registry, listing, enrichment, 100)
        self.assertIn('mock://r', source)
        self.assertIn('mock://l', source)
        self.assertIn('mock://e', source)

    def test_no_sources_returns_empty_strings(self):
        name, role, contact, source, needs_review = select_contact(None, None, None, 0)
        self.assertEqual(name, '')
        self.assertEqual(contact, '')
        self.assertEqual(source, '')
        self.assertTrue(needs_review)


# ---------------------------------------------------------------------------
# process_row — integration tests against real mock data
# ---------------------------------------------------------------------------

class TestProcessRow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mocks = load_mocks(MOCKS_PATH)

    def test_cedar_ridge_high_confidence(self):
        row = process_row('Cedar Ridge Plumbing LLC', '4821 Maple Ave, Lincoln, NE 68504', self.mocks)
        self.assertEqual(row['confidence_score'], 100)
        self.assertEqual(row['contact_name'], 'Daniel Ortega')
        self.assertEqual(row['contact_email_or_phone'], 'd.ortega@cedarridgeplumbing.com')
        self.assertEqual(row['needs_human_review'], 'false')

    def test_pioneer_all_sources_agree(self):
        row = process_row('Pioneer Landscaping Inc', '940 Prairie View Dr, Boise, ID 83704', self.mocks)
        self.assertEqual(row['confidence_score'], 100)
        self.assertEqual(row['needs_human_review'], 'false')

    def test_summit_weak_enrichment_flagged(self):
        row = process_row('Summit Pest Control', '6310 Highland Blvd, Reno, NV 89506', self.mocks)
        self.assertLess(row['confidence_score'], CONFIDENCE_THRESHOLD)
        self.assertEqual(row['contact_email_or_phone'], '')
        self.assertEqual(row['needs_human_review'], 'true')

    def test_coastal_breeze_conflicting_sources_flagged(self):
        # Registry says Tina Alvarez, listing says Marcus Webb — should not reach threshold
        row = process_row('Coastal Breeze Pool Service', '233 Seagrape Way, Sarasota, FL 34236', self.mocks)
        self.assertLess(row['confidence_score'], CONFIDENCE_THRESHOLD)
        self.assertEqual(row['needs_human_review'], 'true')

    def test_company_not_in_mocks_returns_zero(self):
        row = process_row('Redwood Cabinetry', '509 Timber Ct, Eugene, OR 97401', self.mocks)
        self.assertEqual(row['confidence_score'], 0)
        self.assertEqual(row['contact_name'], '')
        self.assertEqual(row['contact_email_or_phone'], '')
        self.assertEqual(row['needs_human_review'], 'true')
        self.assertEqual(row['source'], '')

    def test_harbor_light_falls_back_to_listing_phone(self):
        # No enrichment — contact should be the listing phone
        row = process_row('Harbor Light Electric', '22 Dockside Ave, New Bedford, MA 02740', self.mocks)
        self.assertGreaterEqual(row['confidence_score'], CONFIDENCE_THRESHOLD)
        self.assertEqual(row['contact_email_or_phone'], '+1-508-555-0160')
        self.assertEqual(row['needs_human_review'], 'false')

    def test_provenance_included_for_all_contributing_sources(self):
        row = process_row('Cedar Ridge Plumbing LLC', '4821 Maple Ave, Lincoln, NE 68504', self.mocks)
        self.assertIn('mock://registry', row['source'])
        self.assertIn('mock://listing', row['source'])
        self.assertIn('mock://enrichment', row['source'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
