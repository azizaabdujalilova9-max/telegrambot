import json
from typing import Any


class QuizFormatError(ValueError):
    """Raised when an uploaded quiz JSON document is invalid."""


def parse_quiz_json(contents: bytes) -> dict[str, Any]:
    try:
        document = json.loads(contents.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QuizFormatError("Fayl UTF-8 kodlangan to'g'ri JSON bo'lishi kerak.") from error

    if not isinstance(document, dict):
        raise QuizFormatError("JSON ning yuqori qismi obyekt bo'lishi kerak.")

    title = document.get("title")
    questions = document.get("questions")
    description = document.get("description", "")
    if not isinstance(title, str) or not title.strip():
        raise QuizFormatError("'title' maydoni bo'sh bo'lmagan matn bo'lishi kerak.")
    if not isinstance(description, str):
        raise QuizFormatError("'description' maydoni matn bo'lishi kerak.")
    if not isinstance(questions, list) or not questions:
        raise QuizFormatError("'questions' kamida bitta savoldan iborat ro'yxat bo'lishi kerak.")

    validated_questions: list[dict[str, Any]] = []
    for position, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise QuizFormatError(f"{position}-savol obyekt bo'lishi kerak.")
        question = item.get("question")
        options = item.get("options")
        answer = item.get("answer")
        if not isinstance(question, str) or not question.strip():
            raise QuizFormatError(f"{position}-savol matni bo'sh bo'lmasligi kerak.")
        if (
            not isinstance(options, list)
            or len(options) < 2
            or any(not isinstance(option, str) or not option.strip() for option in options)
        ):
            raise QuizFormatError(f"{position}-savolda kamida 2 ta bo'sh bo'lmagan variant bo'lishi kerak.")
        if isinstance(answer, bool) or not isinstance(answer, int) or not 1 <= answer <= len(options):
            raise QuizFormatError(
                f"{position}-savolning 'answer' qiymati 1 dan {len(options)} gacha bo'lgan variant raqami bo'lishi kerak."
            )
        validated_questions.append(
            {"question": question.strip(), "options": options, "answer": answer}
        )

    return {
        "title": title.strip(),
        "description": description.strip(),
        "questions": validated_questions,
    }
