from random import choice

_QUOTES: list[dict] = [
    {"id": 1, "text": "The only limit to our realization of tomorrow is our doubts of today.", "author": "Franklin D. Roosevelt", "category": "inspirational", "is_premium": False},
    {"id": 2, "text": "In the middle of difficulty lies opportunity.", "author": "Albert Einstein", "category": "inspirational", "is_premium": False},
    {"id": 3, "text": "Life is what happens when you are busy making other plans.", "author": "John Lennon", "category": "life", "is_premium": False},
    {"id": 4, "text": "The best way to predict the future is to invent it.", "author": "Alan Kay", "category": "technology", "is_premium": False},
    {"id": 5, "text": "Simplicity is the ultimate sophistication.", "author": "Leonardo da Vinci", "category": "design", "is_premium": False},
    {"id": 6, "text": "Talk is cheap. Show me the code.", "author": "Linus Torvalds", "category": "technology", "is_premium": False},
    {"id": 7, "text": "First, solve the problem. Then, write the code.", "author": "John Johnson", "category": "technology", "is_premium": False},
    {"id": 8, "text": "The function of good software is to make the complex appear to be simple.", "author": "Grady Booch", "category": "technology", "is_premium": False},
    {"id": 9, "text": "Any fool can write code that a computer can understand. Good programmers write code that humans can understand.", "author": "Martin Fowler", "category": "technology", "is_premium": True},
    {"id": 10, "text": "The computer was born to solve problems that did not exist before.", "author": "Bill Gates", "category": "technology", "is_premium": True},
    {"id": 11, "text": "Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away.", "author": "Antoine de Saint-Exupery", "category": "design", "is_premium": True},
    {"id": 12, "text": "Architecture is the art of how to waste space.", "author": "Philip Johnson", "category": "design", "is_premium": True},
]

_next_id = len(_QUOTES) + 1


def get_all() -> list[dict]:
    return [q for q in _QUOTES if not q["is_premium"]]


def get_by_id(quote_id: int) -> dict | None:
    for quote in _QUOTES:
        if quote["id"] == quote_id:
            return quote
    return None


def get_random() -> dict | None:
    public = [q for q in _QUOTES if not q["is_premium"]]
    if not public:
        return None
    return choice(public)


def get_premium() -> list[dict]:
    return [q for q in _QUOTES if q["is_premium"]]


def _reset_store() -> None:
    global _QUOTES
    _QUOTES = [
        {"id": 1, "text": "The only limit to our realization of tomorrow is our doubts of today.", "author": "Franklin D. Roosevelt", "category": "inspirational", "is_premium": False},
        {"id": 2, "text": "In the middle of difficulty lies opportunity.", "author": "Albert Einstein", "category": "inspirational", "is_premium": False},
        {"id": 3, "text": "Life is what happens when you are busy making other plans.", "author": "John Lennon", "category": "life", "is_premium": False},
        {"id": 4, "text": "The best way to predict the future is to invent it.", "author": "Alan Kay", "category": "technology", "is_premium": False},
        {"id": 5, "text": "Simplicity is the ultimate sophistication.", "author": "Leonardo da Vinci", "category": "design", "is_premium": False},
        {"id": 6, "text": "Talk is cheap. Show me the code.", "author": "Linus Torvalds", "category": "technology", "is_premium": False},
        {"id": 7, "text": "First, solve the problem. Then, write the code.", "author": "John Johnson", "category": "technology", "is_premium": False},
        {"id": 8, "text": "The function of good software is to make the complex appear to be simple.", "author": "Grady Booch", "category": "technology", "is_premium": False},
        {"id": 9, "text": "Any fool can write code that a computer can understand. Good programmers write code that humans can understand.", "author": "Martin Fowler", "category": "technology", "is_premium": True},
        {"id": 10, "text": "The computer was born to solve problems that did not exist before.", "author": "Bill Gates", "category": "technology", "is_premium": True},
        {"id": 11, "text": "Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away.", "author": "Antoine de Saint-Exupery", "category": "design", "is_premium": True},
        {"id": 12, "text": "Architecture is the art of how to waste space.", "author": "Philip Johnson", "category": "design", "is_premium": True},
    ]