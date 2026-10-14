import unittest

from guess import ROOT, build_prompt, handle_payload, load_dictionary, retry_prompt
from parse import parse_candidates


class ParseTests(unittest.TestCase):
    def test_prompt_requires_length_and_revealed_letters(self):
        prompt = build_prompt("_x_l_____")
        self.assertIn("skribbl.io", prompt)
        self.assertIn("bad sketch", prompt)
        self.assertNotIn("exactly 9 characters", prompt)

    def test_retry_when_nothing_fits(self):
        prompt = retry_prompt("_x_l_____", "bomb\nstar\nfire\n")
        self.assertIn("bomb, star, fire", prompt)
        self.assertIsNone(retry_prompt("_x_l_____", "explosive\nbomb\n"))
        self.assertIsNone(retry_prompt("hidden", "bomb\n"))
    def test_strips_markers_and_drops_sentences(self):
        text = "\n".join(
            [
                "1. Banana",
                "2. Ice cream",
                "- a yellow fruit sitting on a table",
                "papaya",
                "1. banana",
            ]
        )
        self.assertEqual(parse_candidates(text), ["banana", "ice cream", "papaya"])

    def test_refilter_skips_the_model(self):
        def fail_ask(image, pattern):
            raise AssertionError("model should not be called")

        payload = handle_payload(
            {
                "hints": list("c_t"),
                "word_length": "3",
                "raw": ["cat", "cot", "pencil"],
                "rejects": ["cot"],
            },
            fail_ask,
            ["cut"],
        )
        self.assertIsNone(payload["error"])
        self.assertIsNone(payload["model_ms"])
        self.assertEqual(payload["pattern"], "c_t")
        self.assertEqual(payload["guesses"], ["cat", "cut"])
        self.assertEqual(payload["close"], [])
        self.assertEqual(payload["dictionary"], [])

    def test_model_text_is_filtered(self):
        def ask(image, pattern):
            self.assertIn("b_n_n_", pattern)
            return "1. banana\n2. canoe\n"

        payload = handle_payload(
            {"image": "abc", "hints": list("b_n_n_"), "word_length": "6"},
            ask,
            [],
        )
        self.assertEqual(payload["guesses"], ["banana"])
        self.assertEqual(payload["close"], [])
        self.assertEqual(payload["raw"], ["banana", "canoe"])
        self.assertIsInstance(payload["model_ms"], int)

    def test_tight_board_uses_letters_and_skips_the_drawing(self):
        def fail_ask(image, pattern):
            raise AssertionError("model should not be called")

        payload = handle_payload(
            {
                "image": "abc",
                "hints": list("_l______k"),
                "word_length": "9",
                "raw": ["knight", "bank", "k"],
            },
            fail_ask,
            ["blackjack", "clockwork", "flashback", "sleepwalk", "knight"],
        )
        self.assertIsNone(payload["model_ms"])
        self.assertEqual(
            payload["guesses"],
            ["blackjack", "clockwork", "flashback", "sleepwalk"],
        )

    def test_sleepwalk_board_on_the_real_word_list(self):
        words = load_dictionary(ROOT.parent / "words" / "en.txt")
        self.assertGreater(len(words), 1000)

        def fail_ask(image, pattern):
            raise AssertionError("model should not be called")

        payload = handle_payload(
            {"image": "abc", "hints": list("_l______k"), "word_length": "9"},
            fail_ask,
            words,
        )
        self.assertEqual(payload["guesses"], ["sleepwalk", "glowstick"])
        self.assertIsNone(payload["model_ms"])

    def test_letters_keep_fitting_words_from_the_list(self):
        payload = handle_payload(
            {
                "hints": list("___ck__"),
                "word_length": "7",
                "raw": ["banana", "cherry", "grape"],
            },
            lambda image, pattern: (_ for _ in ()).throw(AssertionError("no model")),
            ["quickly", "chicken", "orange"],
        )
        self.assertEqual(payload["guesses"], ["quickly", "chicken"])
        self.assertNotIn("banana", payload["guesses"])

    def test_model_failure_is_reported(self):
        def ask(image, pattern):
            raise RuntimeError("down")

        payload = handle_payload(
            {"image": "abc", "hints": list("___"), "word_length": "3", "raw": ["cat"]},
            ask,
            [],
        )
        self.assertEqual(payload["error"], "down")
        self.assertEqual(payload["guesses"], ["cat"])


if __name__ == "__main__":
    unittest.main()
