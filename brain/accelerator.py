"""Make sure the machine's GPU is actually being used, not silently skipped.

This exists because of a measured, reproducible, and completely invisible
failure. On an Intel Core Ultra 5 125U -- integrated Arc graphics, no
discrete card -- Ollama detected the GPU through its own Vulkan backend and
then deliberately discarded it, logging:

    dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1
    id=0 library=Vulkan name=Vulkan0 description="Intel(R) Graphics"

and fell back to `library=cpu`. Nothing surfaced that decision to the user.
Mike simply ran the same 9.7B model on the CPU, and the cost was not subtle:

    CPU (iGPU dropped)   114.5s for a four-word first reply
    iGPU enabled          12.9s for the same reply

Same model, same quantisation, same prompt -- an ~8.8x difference decided
entirely by one environment variable the user has never heard of. Ollama's
default is defensible for a server (many integrated GPUs are slower than a
good CPU, and it cannot know), but it is the wrong default for a local
assistant on a laptop, which is precisely the machine that has an iGPU and
no alternative.

This does not force anything on a machine that already has a better option:
if a discrete GPU is present, Ollama is already using it and the variable is
irrelevant. Setting it is only ever a permission -- "you may use the
integrated GPU if that is all there is" -- never an instruction to prefer it
over a real card.

The variable is set at user scope so it survives a reboot and applies to
however the user happens to start Ollama next: the tray app, `ollama serve`,
or a service. It cannot retroactively change an Ollama that is already
running, which is why check_acceleration() reports that case rather than
restarting a process Mike does not own.
"""
from __future__ import annotations

import os
import platform
import subprocess

from logs.logger import logger

IGPU_ENV = "OLLAMA_IGPU_ENABLE"


def enable_igpu_for_future_starts() -> bool:
    """Persist OLLAMA_IGPU_ENABLE=1 for this user, if it isn't set already.

    Returns True when this call is what set it (so the caller knows a
    restart of Ollama is what stands between the user and the GPU).
    Windows-only: on macOS the GPU path is Metal and always taken, and this
    variable has no meaning there.
    """
    if platform.system() != "Windows":
        return False
    if os.environ.get(IGPU_ENV):
        return False
    try:
        # setx rather than os.environ: this must outlive Mike's process and
        # apply to whatever starts Ollama next, which is usually not Mike.
        subprocess.run(
            ["setx", IGPU_ENV, "1"],
            check=True, capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        os.environ[IGPU_ENV] = "1"
        logger.info(
            "Enabled Ollama's integrated-GPU support for future starts "
            "(%s=1). Ollama picks this up the next time it starts.", IGPU_ENV,
        )
        return True
    except Exception:
        logger.debug("Could not set %s.", IGPU_ENV, exc_info=True)
        return False


def describe_acceleration(client) -> str:
    """What is actually doing the work right now: "GPU", "CPU", or "unknown".

    Read from Ollama's own report of a loaded model rather than inferred
    from what hardware exists -- the entire bug this module addresses was a
    machine that *had* a usable GPU and wasn't using it, so anything short
    of asking what is really running would have missed it.
    """
    try:
        running = client.ps()
        for model in (running.get("models") or []):
            size = model.get("size") or 0
            size_vram = model.get("size_vram") or 0
            if not size:
                continue
            return "GPU" if size_vram >= size * 0.5 else "CPU"
    except Exception:
        logger.debug("Could not read Ollama's running-model report.", exc_info=True)
    return "unknown"
