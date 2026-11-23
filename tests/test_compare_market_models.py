"""Synthetic research-method checks; no official inputs or operating writes."""
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from tools.compare_market_models import (
    ROOT, add, band, correlation_record, domain_view, footprint, midranks,
    output_path, pearson, spearman, stability, transform,
)


class ComparisonResearchTests(unittest.TestCase):
    def series(self, months=69):
        return {add('2021-01', i): 100+i*i for i in range(months)}

    def test_pearson_direction_and_scale(self):
        self.assertAlmostEqual(pearson([1, 2, 3, 4], [3, 5, 7, 9]), 1)
        self.assertAlmostEqual(pearson([1, 2, 3, 4], [9, 7, 5, 3]), -1)

    def test_no_coefficient_for_short_or_constant_series(self):
        self.assertIsNone(pearson([1, 2], [2, 3]))
        self.assertIsNone(pearson([2, 2, 2], [1, 2, 3]))
        self.assertIsNone(spearman([], []))

    def test_pair_lengths_cannot_silently_truncate(self):
        with self.assertRaisesRegex(ValueError, 'pair_length'):
            pearson([1, 2, 3], [2, 3])

    def test_spearman_midranks_and_known_value(self):
        self.assertEqual(midranks([2, 1, 1, 3]), [3, Fraction(3, 2), Fraction(3, 2), 4])
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [1, 3, 2, 4]), .8)
        self.assertAlmostEqual(spearman([2, 1, 1, 3], [2, 1, 1, 3]), 1)

    def test_yoy_and_smoothing_are_calendar_exact(self):
        s = self.series()
        growth = transform(s, 'yoy')
        self.assertEqual(growth['2022-01'], Fraction(144))
        self.assertEqual(len(growth), 57)
        smoothed = transform(s, 'smoothed_yoy')
        self.assertEqual(len(smoothed), 55)
        self.assertEqual(smoothed['2022-03'], sum(growth[p] for p in ['2022-01', '2022-02', '2022-03'])/3)

    def test_gap_is_not_compressed_or_imputed(self):
        s = self.series()
        del s['2022-02']
        self.assertNotIn('2022-02', transform(s, 'yoy'))
        self.assertNotIn('2022-03', transform(s, 'smoothed_yoy'))
        self.assertNotIn('2022-04', transform(s, 'smoothed_yoy'))
        self.assertNotIn('2023-02', transform(s, 'yoy'))

    def test_zero_denominator_not_zero_growth(self):
        s = self.series()
        s['2021-01'] = 0
        self.assertNotIn('2022-01', transform(s, 'yoy'))

    def test_exclusion_checks_denominators_and_smoothing_inputs(self):
        s = self.series()
        yoy = correlation_record(s, s, 'yoy', '2022-12')
        smooth = correlation_record(s, s, 'smoothed_yoy', '2022-12')
        self.assertEqual((yoy['n'], yoy['first']), (33, '2024-01'))
        self.assertEqual((smooth['n'], smooth['first']), (31, '2024-03'))
        self.assertEqual(min(footprint('2024-03', 'smoothed_yoy')), '2023-01')

    def test_missing_industry_keeps_full_model_empty(self):
        r = domain_view([{'domain': 'demand', 'percentile': '200/3'},
                         {'domain': 'consumption', 'percentile': '175/3'}])
        self.assertEqual(r['missing_required_domains'], ['industry'])
        self.assertIsNone(r['whole_market_score'])
        self.assertEqual(r['whole_market_status'], 'withheld')

    def test_domain_variable_count_does_not_increase_weight(self):
        one = [{'domain': 'demand', 'percentile': '40'},
               {'domain': 'consumption', 'percentile': '80'}]
        duplicate = one + [{'domain': 'demand', 'percentile': '40'}]
        self.assertEqual(domain_view(one), domain_view(duplicate))

    def test_stability_does_not_compare_across_gap(self):
        r = stability([{'period': '2024-01', 'exact': '10'},
                       {'period': '2024-02', 'exact': '20'},
                       {'period': '2024-04', 'exact': '90'}])
        self.assertEqual(r['consecutive_comparisons'], 1)
        self.assertEqual(r['mean_absolute_monthly_change'], 10)
        self.assertIsNone(stability([])['minimum'])

    def test_output_cannot_target_repo_existing_or_parent(self):
        for p in [ROOT, ROOT/'site/data/private', ROOT.parent]:
            with self.assertRaisesRegex(ValueError, 'external_output'):
                output_path(p)
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError, 'new_output'):
                output_path(t)
            self.assertEqual(output_path(Path(t)/'fresh'), Path(t)/'fresh')

    def test_existing_weather_cutoff_boundaries(self):
        self.assertEqual([band(Fraction(v)) for v in [0, 25, 50, 75, 100]],
                         ['rain', 'cloudy', 'partly', 'sunny', 'sunny'])


if __name__ == '__main__':
    unittest.main()
