"""Folder organizer — Mike's first single-purpose feature.

Point it at a messy folder (Downloads, Desktop) and it proposes a tidy
layout: every file sorted into a category folder, junk names like
``IMG_4821.png`` or ``document(3).pdf`` given readable ones, and exact
duplicates set aside. Nothing moves until the user has seen the whole plan,
and the whole run can be undone in one step.

The pipeline is deliberately not an agent loop:

    scan  ->  classify  ->  plan  ->  (user approves)  ->  apply  ->  undo

The local model is only asked the one question it is good at -- "what is
this file, and what should it be called?" -- and never decides to move
anything itself. Every filesystem change is made here, by code that can be
tested, and recorded in a journal before it happens.

Nothing is ever deleted. Not junk, not installers, not duplicates.
"""
from organizer.plan import Move, Plan, build_plan
from organizer.journal import apply_plan, undo_run, list_runs

__all__ = ["Move", "Plan", "build_plan", "apply_plan", "undo_run", "list_runs"]
