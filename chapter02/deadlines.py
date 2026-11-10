"""Alias for clocks.py.

Chapter 3's "What you now have" list refers to this module as
chapter02/deadlines.py; Chapter 2 calls it clocks.py. Both names work.
"""
from clocks import BDAY, RULES_PATH, add_time, deadlines, load_rules, main, stale_rules  # noqa: F401

if __name__ == "__main__":
    main()
