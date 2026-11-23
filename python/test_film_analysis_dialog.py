"""Default task selection in combined film analysis."""
import unittest
from film_analysis_dialog import default_analysis_selection


class AnalysisSelectionTests(unittest.TestCase):
    def test_missing_results_are_selected(self):
        self.assertEqual(default_analysis_selection(None, False),
                         {"lufs": True, "subtitles": True})

    def test_existing_results_are_unselected(self):
        self.assertEqual(default_analysis_selection(-19.4, True),
                         {"lufs": False, "subtitles": False})

    def test_independent_selection(self):
        self.assertEqual(default_analysis_selection(-22.0, False),
                         {"lufs": False, "subtitles": True})


if __name__ == "__main__":
    unittest.main()
