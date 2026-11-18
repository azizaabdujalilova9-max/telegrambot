import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def _connect(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path: str | Path) -> None:
    with _connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
                question_text TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_index INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(user_id),
                test_id INTEGER REFERENCES tests(id) ON DELETE SET NULL,
                test_title TEXT NOT NULL,
                total_questions INTEGER NOT NULL,
                correct_answers INTEGER NOT NULL,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS attempt_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                question_text TEXT NOT NULL,
                selected_option TEXT NOT NULL,
                is_correct INTEGER NOT NULL
            );
            """
        )


def save_user(database_path: str | Path, user_id: int, username: str | None, first_name: str) -> None:
    with _connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name),
        )


def add_test(
    database_path: str | Path,
    title: str,
    description: str,
    questions: list[dict[str, Any]],
) -> int:
    with _connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.execute(
            "INSERT INTO tests (title, description) VALUES (?, ?)",
            (title, description),
        )
        test_id = cursor.lastrowid
        connection.executemany(
            """
            INSERT INTO questions (test_id, question_text, options_json, correct_index)
            VALUES (?, ?, ?, ?)
            """,
            [
                (test_id, item["question"], json.dumps(item["options"], ensure_ascii=False), item["answer"] - 1)
                for item in questions
            ],
        )
        return int(test_id)


def list_tests(database_path: str | Path) -> list[dict[str, Any]]:
    with _connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT tests.id, tests.title, tests.description, COUNT(questions.id)
            FROM tests
            LEFT JOIN questions ON questions.test_id = tests.id
            GROUP BY tests.id
            ORDER BY tests.id DESC
            """
        ).fetchall()
    return [
        {"id": row[0], "title": row[1], "description": row[2], "question_count": row[3]}
        for row in rows
    ]


def get_test(database_path: str | Path, test_id: int) -> dict[str, Any] | None:
    with _connect(database_path) as connection:
        row = connection.execute(
            "SELECT id, title, description FROM tests WHERE id = ?",
            (test_id,),
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "title": row[1], "description": row[2]}


def get_questions(database_path: str | Path, test_id: int) -> list[dict[str, Any]]:
    with _connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, question_text, options_json, correct_index
            FROM questions
            WHERE test_id = ?
            """,
            (test_id,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "question": row[1],
            "options": json.loads(row[2]),
            "correct_index": row[3],
        }
        for row in rows
    ]


def delete_test(database_path: str | Path, test_id: int) -> bool:
    with _connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.execute("DELETE FROM tests WHERE id = ?", (test_id,))
        return cursor.rowcount > 0


def save_attempt(
    database_path: str | Path,
    user_id: int,
    test_id: int,
    test_title: str,
    total_questions: int,
    correct_answers: int,
    answers: list[dict[str, Any]],
) -> None:
    with _connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        test_exists = connection.execute(
            "SELECT 1 FROM tests WHERE id = ?",
            (test_id,),
        ).fetchone()
        cursor = connection.execute(
            """
            INSERT INTO attempts (
                user_id, test_id, test_title, total_questions, correct_answers
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, test_id if test_exists else None, test_title, total_questions, correct_answers),
        )
        attempt_id = cursor.lastrowid
        connection.executemany(
            """
            INSERT INTO attempt_answers (
                attempt_id, question_text, selected_option, is_correct
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (attempt_id, answer["question"], answer["selected_option"], int(answer["is_correct"]))
                for answer in answers
            ],
        )
