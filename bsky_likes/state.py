# -*- coding: utf-8 -*-
"""Resumable ingest state.

JSON on disk with a set-valued `done_users` (serialized as a list). Path and
initial-defaults are supplied by the caller so a single implementation serves
all ingest modes, which previously each had their own copy.
"""
import json


def load_state(path, defaults):
    """Load state from `path`, or return a fresh state seeded with `defaults`.

    `defaults` is the mode-specific initial dict (e.g. {"shard_idx": 0, ...}).
    `done_users` is always present and always a set.
    """
    if path.exists():
        s = json.loads(path.read_text())
        s["done_users"] = set(s.get("done_users", []))
        return s
    return {"done_users": set(), **defaults}


def save_state(path, state):
    s = dict(state)
    s["done_users"] = list(state["done_users"])
    path.write_text(json.dumps(s))
