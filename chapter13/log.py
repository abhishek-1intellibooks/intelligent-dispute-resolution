"""The action log: every proposal and every verdict, with the gate's version.

The model's stated reason is stored for the person who reviews the run; it is
never passed to the gate.
"""
import json

import systems


class ActionLog:
    def __init__(self, case_id):
        self.case_id = case_id
        self.entries = []

    def write(self, step, action, verdict, config):
        world = systems._ACTIVE
        self.entries.append({
            "case_id": self.case_id, "step": step,
            "at": systems.clock_display(world.minutes) if world else None,
            "proposed": action.name, "args": action.args, "model_reason": action.reason,
            "allowed": verdict.allowed, "verdict": verdict.reason,
            "escalate": verdict.escalate, "alert": verdict.alert, "config": config,
        })

    def to_jsonl(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            for entry in self.entries:
                fh.write(json.dumps(entry) + "\n")

    def __iter__(self):
        return iter(self.entries)

    def __len__(self):
        return len(self.entries)
