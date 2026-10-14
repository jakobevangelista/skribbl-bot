import unittest

from pattern import matches, pattern_text, slots_from_hints, unknown_count
from rank import rank


class PatternTests(unittest.TestCase):
    def test_single_word_with_revealed_letter(self):
        slots = slots_from_hints(list("b_n_n_"), "")
        self.assertEqual(pattern_text(slots), "b_n_n_")
        self.assertTrue(matches("banana", slots))
        self.assertFalse(matches("bandana", slots))
        self.assertFalse(matches("Banana split", slots))

    def test_gap_from_word_length(self):
        slots = slots_from_hints(["_"] * 9, "3 5")
        self.assertEqual(pattern_text(slots), "___ _____")
        self.assertTrue(matches("ice cream", slots))
        self.assertTrue(matches("ice-cream", slots))
        self.assertFalse(matches("icecreamx", slots))

    def test_live_guesser_hint_shape(self):
        # Shape produced on the live page: 3 + space + 5, first letter revealed.
        slots = slots_from_hints(["i", "_", "_", " ", "_", "_", "_", "_", "_"], "3 5")
        self.assertEqual(pattern_text(slots), "i__ _____")
        self.assertTrue(matches("ice cream", slots))
        self.assertFalse(matches("ice-cream", slots))

    def test_revealed_space_is_exact(self):
        hints = ["i", "c", "e", " ", "c", "_", "_", "_", "_"]
        slots = slots_from_hints(hints, "3 5")
        self.assertTrue(matches("ice cream", slots))
        self.assertFalse(matches("ice-cream", slots))

    def test_hyphen_inside_one_segment(self):
        slots = slots_from_hints(list("__-__"), "5")
        self.assertTrue(matches("yo-yo", slots))
        self.assertFalse(matches("yoyo", slots))

    def test_hidden_mode_has_no_length(self):
        slots = slots_from_hints(["?", "?", "?"], "")
        self.assertIsNone(slots)
        self.assertEqual(pattern_text(slots), "hidden")
        self.assertTrue(matches("proposal", slots))
        self.assertEqual(unknown_count(slots), 99)

    def test_case_and_reject_and_dictionary(self):
        slots = slots_from_hints(list("c_t"), "3")
        self.assertEqual(unknown_count(slots), 1)
        guesses, close, extra = rank(
            ["Cat", "dog", "a yellow fruit"],
            slots,
            ["cat", "cot", "cut"],
            ["cut"],
        )
        self.assertEqual(guesses, ["cat", "cot"])
        self.assertEqual(close, [])
        self.assertEqual(extra, [])

    def test_drops_wrong_length_single_letters_and_spaces(self):
        slots = slots_from_hints(list("_l______k"), "9")
        guesses, close, extra = rank(
            ["k", "a", "sleep walk", "bank", "knight", "sleepwalk", "Sleepwalk"],
            slots,
            ["quickly", "chicken"],
            [],
        )
        self.assertEqual(guesses, ["sleepwalk"])
        self.assertEqual(close, [])
        self.assertEqual(extra, [])

    def test_sketch_words_sort_the_legal_answers(self):
        slots = slots_from_hints(list("_l______k"), "9")
        guesses, close, extra = rank(
            ["a person walking", "sleep", "glow"],
            slots,
            ["sleepwalk", "glowstick", "clockwork"],
            [],
        )
        self.assertEqual(guesses, ["sleepwalk", "glowstick", "clockwork"])
        self.assertEqual(close, [])
        self.assertEqual(extra, [])


if __name__ == "__main__":
    unittest.main()
