"""Generation, checking and approval (Listing 12.5), with the three writers.

produce() builds the context pack, runs a writer and the checker, regenerates
once if the draft is flagged, logs every attempt and never sends anything.
approve() is the only way a document leaves: a named person releases it.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field

import llm_client
from context import context_pack, render_pack
from draft import (draft_letter, draft_narrative, render, render_for_check,
                   split_sentences, strip_citations)
from guardrails import check, check_length
from summarize import sentences as summary_sentences
from summarize import summarize, summarize_slotted


@dataclass
class Draft:
    kind: str
    text: str                       # the draft as an analyst reads it, values rendered
    sentences: list                 # what the checker reads: values and citations
    prompt_version: str
    model: str
    template: str | None = None     # the slotted template, kept for re-rendering
    structure_flags: list = field(default_factory=list)
    truth: dict | None = None       # the stand-in's record of its own mistakes

    @property
    def customer_text(self):
        return strip_citations(self.text)


def _truth():
    model = llm_client.offline_model() if llm_client.provider() == "offline" else None
    return dict(model.last) if model is not None and getattr(model, "last", None) else None


def summary_writer(items, slotted=False):
    pack = render_pack(items)
    try:
        out = summarize_slotted(pack) if slotted else summarize(pack)
    except (ValueError, json.JSONDecodeError) as exc:      # invalid output: regenerate
        return Draft("summary", "", [], "summary-1.4", llm_client.model_name(),
                     structure_flags=[("structure", str(exc))], truth=_truth())
    written = summary_sentences(out)
    checked = [render_for_check(s, items) for s in written]
    return Draft("summary", "\n".join(checked), checked, out["prompt_version"],
                 llm_client.model_name(), template="\n".join(written) if slotted else None,
                 truth=_truth())


def slotted_summary_writer(items):
    return summary_writer(items, slotted=True)


def letter_writer(items):
    text, version = draft_letter(items)
    lines = split_sentences(text)
    return Draft("letter", "\n".join(lines), lines, version, llm_client.model_name(),
                 structure_flags=check_length(text, 250), truth=_truth())


def representment_writer(items):
    template, version = draft_narrative(items)
    lines = split_sentences(template)
    checked = [render_for_check(s, items) for s in lines]
    try:
        rendered = " ".join(render(s, items) for s in lines)
    except KeyError as exc:                                # invented placeholder
        rendered = " ".join(checked)
        flags = [("bad_placeholder", str(exc))]
    else:
        flags = []
    return Draft("representment", rendered, checked, version, llm_client.model_name(),
                 template=template, structure_flags=flags + check_length(rendered, 150),
                 truth=_truth())


WRITERS = {"summary": summary_writer, "letter": letter_writer,
           "representment": representment_writer}


class JsonlLog:
    """The generation log: one JSON line per attempt, approval or edit."""

    def __init__(self, path):
        self.path = path
        open(path, "w", encoding="utf-8").close()

    def write(self, entry):
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")


class MemoryLog(list):
    def write(self, entry):
        self.append(entry)


def produce(kind, case, evidence, decision, writer, log, attempts=2):
    """Write, check, and regenerate once; never send anything."""
    items = context_pack(case, evidence, decision)
    pack_hash = hashlib.sha256(render_pack(items).encode()).hexdigest()
    for attempt in range(1, attempts + 1):
        draft = writer(items)              # summary, letter or representment
        flags = check(draft.sentences, items) + draft.structure_flags
        log.write({"case_id": case.case_id, "kind": kind, "attempt": attempt,
                   "pack_sha256": pack_hash, "prompt": draft.prompt_version,
                   "model": draft.model, "text": draft.text, "flags": flags,
                   "at": time.time()})
        if not flags:
            return {"status": "ready_for_approval", "draft": draft, "flags": []}
    return {"status": "needs_person", "draft": draft, "flags": flags}


def approve(case, result, approver, final_text, log):
    """Only a named person can release a document."""
    log.write({"case_id": case.case_id, "event": "approved", "approver": approver,
               "edited": final_text != result["draft"].text,
               "text": final_text, "at": time.time()})
    return final_text
