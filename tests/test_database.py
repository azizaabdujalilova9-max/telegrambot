import sqlite3
import tempfile
import unittest
from pathlib import Path

import database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        database.initialize_database(self.database_path)
        database.save_user(self.database_path, 42, "tester", "Test User")
        self.test_id = database.add_test(
            self.database_path,
            "Matematika",
            "",
            [{"question": "2+2?", "options": ["3", "4"], "answer": 2}],
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_and_read_test_questions(self) -> None:
        test = database.get_test(self.database_path, self.test_id)
        questions = database.get_questions(self.database_path, self.test_id)
        self.assertEqual(test["title"], "Matematika")
        self.assertEqual(questions[0]["options"], ["3", "4"])
        self.assertEqual(questions[0]["correct_index"], 1)

    def test_deleting_test_preserves_saved_attempt(self) -> None:
        database.save_attempt(
            self.database_path,
            42,
            self.test_id,
            "Matematika",
            1,
            1,
            [{"question": "2+2?", "selected_option": "4", "is_correct": True}],
        )
        self.assertTrue(database.delete_test(self.database_path, self.test_id))
        connection = sqlite3.connect(self.database_path)
        try:
            attempt = connection.execute(
                "SELECT test_id, test_title, correct_answers FROM attempts"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(attempt, (None, "Matematika", 1))

    def test_attempt_can_be_saved_after_test_is_deleted(self) -> None:
        database.delete_test(self.database_path, self.test_id)
        database.save_attempt(
            self.database_path,
            42,
            self.test_id,
            "Matematika",
            1,
            0,
            [{"question": "2+2?", "selected_option": "3", "is_correct": False}],
        )
        connection = sqlite3.connect(self.database_path)
        try:
            attempt = connection.execute(
                "SELECT test_id, test_title, correct_answers FROM attempts"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(attempt, (None, "Matematika", 0))


if __name__ == "__main__":
    unittest.main()
