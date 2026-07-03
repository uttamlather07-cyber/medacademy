"""
polls.py
Simple live polls — admin asks a question with options, students vote,
admin sees live tallies and can end the poll.
"""

from database import save_db


def start_poll(db, question: str, options: list):
    opts = [o.strip() for o in options if o and o.strip()]
    db["polls"] = {
        "active": True,
        "question": question,
        "options": opts,
        "votes": {},
    }
    save_db(db)


def end_poll(db):
    db["polls"]["active"] = False
    save_db(db)


def cast_vote(db, username: str, option: str):
    db["polls"]["votes"][username] = option
    save_db(db)
