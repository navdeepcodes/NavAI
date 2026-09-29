"""Every Windows machine class must get a *whole* Mike.

These exist because a speed fix nearly shipped a crippled assistant to the
users with the weakest hardware. Sizing the context down to 8,192 to make a
CPU-only laptop faster left only 6,144 usable tokens against a ~7,200-token
prefix, so context planning dropped tools to make it fit -- "offering 14 of
44 tools". Faster, and missing two thirds of what Mike does.

So the rule these pin down is: hardware decides how *fast* Mike is, never
how *capable* he is. Each tier may choose a different context, and none of
them may choose one that cannot hold the full toolset.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import json

import pytest

from brain.core_runtime import SYSTEM_PROMPT
from brain.core_tools import TOOL_DECLARATIONS
from brain.providers.ollama_provider import USABLE_FRACTION_OF_CTX


def _prefix_tokens() -> int:
    """Roughly what Mike sends before the user has said anything."""
    tools = json.dumps([
        {"name": t.name, "description": t.description,
         "parameters": t.parameters_json_schema}
        for t in TOOL_DECLARATIONS
    ])
    return (len(SYSTEM_PROMPT) + len(tools)) // 4


# (metal, discrete_gpu, gpu_offload) for each machine Mike actually meets.
TIERS = [
    ("Apple Silicon", True, False, True),
    ("Windows + NVIDIA/AMD discrete", False, True, True),
    ("Windows + Intel/AMD integrated", False, False, True),
    ("Windows, no GPU offload at all", False, False, False),
]


@pytest.mark.parametrize("name,metal,discrete,offload", TIERS)
def test_every_machine_class_can_hold_the_whole_toolset(
    name, metal, discrete, offload, monkeypatch,
):
    import brain.hardware as hardware
    from config import ollama as ollama_config

    real = hardware.Machine.detect()
    monkeypatch.setattr(
        hardware, "current",
        lambda refresh=False: hardware.Machine(
            **{**real.as_dict(),
               "metal": metal, "discrete_gpu": discrete, "gpu_offload": offload,
               "notes": []}
        ),
    )

    num_ctx = ollama_config._num_ctx()
    usable = int(num_ctx * USABLE_FRACTION_OF_CTX)
    assert usable > _prefix_tokens(), (
        f"{name}: num_ctx={num_ctx} leaves {usable} usable tokens for a "
        f"~{_prefix_tokens()}-token prefix, so tools would be dropped"
    )


def test_no_tier_falls_below_the_documented_floor(monkeypatch):
    """The floor is the contract; a future tier must not quietly undercut it."""
    import brain.hardware as hardware
    from config import ollama as ollama_config

    real = hardware.Machine.detect()
    for _name, metal, discrete, offload in TIERS:
        monkeypatch.setattr(
            hardware, "current",
            lambda refresh=False, m=metal, d=discrete, o=offload: hardware.Machine(
                **{**real.as_dict(),
                   "metal": m, "discrete_gpu": d, "gpu_offload": o, "notes": []}
            ),
        )
        assert ollama_config._num_ctx() >= ollama_config.MIN_NUM_CTX


def test_a_cpu_only_machine_is_slow_not_lobotomised(monkeypatch):
    """The specific regression: CPU-only must not be the tier that loses tools."""
    import brain.hardware as hardware
    from config import ollama as ollama_config

    real = hardware.Machine.detect()
    monkeypatch.setattr(
        hardware, "current",
        lambda refresh=False: hardware.Machine(
            **{**real.as_dict(),
               "metal": False, "discrete_gpu": False, "gpu_offload": False,
               "notes": []}
        ),
    )
    assert ollama_config._num_ctx() == ollama_config.MIN_NUM_CTX
    assert int(ollama_config._num_ctx() * USABLE_FRACTION_OF_CTX) > _prefix_tokens()
