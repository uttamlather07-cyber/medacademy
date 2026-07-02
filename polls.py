"""
polls.py
Smart tracking polls — voting increments a student's performance metric.

Two poll modes:
- Tracking poll: fixed Yes/No/Partially options, tied to a metric
  (Revision/Tests/DPPs). Any vote increments that metric by 1 for the
  voting student — same mechanic regardless of which option they pick,
  since the point is "did you engage with this", not grading the answer.
- Custom poll: admin-defined question with a list of options (added one
  at a time in the UI, not typed as comma-separated text).
"""

from database import save_db

TRACKING_OPTIONS = ["Yes", "No", "Partially"]


def start_poll(db, question: str, options: list, is_smart: bool, track_metric: str):
    opts = [o.strip() for o in options if o and o.strip()]
    db["polls"] = {
        "active": True,
        "question": question,
        "options": opts,
        "votes": {},
        "is_smart": is_smart,
        "track_metric": track_metric,
    }
    save_db(db)


def start_tracking_poll(db, metric: str, question: str = None):
    """Convenience wrapper for the Yes/No/Partially tracking poll preset."""
    q = question or f"Did you complete today's {metric.lower()}?"
    start_poll(db, q, TRACKING_OPTIONS, is_smart=True, track_metric=metric)


def end_poll(db):
    db["polls"]["active"] = False
    save_db(db)


def cast_vote(db, username: str, option: str):
    db["polls"]["votes"][username] = option
    if db["polls"].get("is_smart") and db["polls"].get("track_metric"):
        metric = db["polls"]["track_metric"]
        db["users"][username]["metrics"][metric] = db["users"][username]["metrics"].get(metric, 0) + 1
    save_db(db)
