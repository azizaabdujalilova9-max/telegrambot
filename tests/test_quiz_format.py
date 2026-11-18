import json
import unittest

from quiz_format import QuizFormatError, parse_quiz_json


class ParseQuizJsonTests(unittest.TestCase):
    def test_parses_valid_quiz_and_trims_title_and_description(self) -> None:
        source = {
            "title": "  Sinov  ",
            "description": "  Izoh  ",
            "questions": [
                {"question": "Savol?", "options": ["A", "B"], "answer": 2}
            ],
        }
        parsed = parse_quiz_json(json.dumps(source).encode())
        self.assertEqual(parsed["title"], "Sinov")
        self.assertEqual(parsed["description"], "Izoh")
        self.assertEqual(parsed["questions"][0]["answer"], 2)

    def test_rejects_answer_outside_options(self) -> None:
        source = {
            "title": "Sinov",
            "questions": [{"question": "Savol?", "options": ["A", "B"], "answer": 3}],
        }
        with self.assertRaises(QuizFormatError):
            parse_quiz_json(json.dumps(source).encode())

    def test_rejects_boolean_answer(self) -> None:
        source = {
            "title": "Sinov",
            "questions": [{"question": "Savol?", "options": ["A", "B"], "answer": True}],
        }
        with self.assertRaises(QuizFormatError):
            parse_quiz_json(json.dumps(source).encode())


if __name__ == "__main__":
    unittest.main()
