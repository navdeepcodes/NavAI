"""What this machine can actually run, measured rather than assumed.

Mike's configuration currently states what to run — a 9B brain at a 40,960
token context, a neural voice — and that is right for the machine it was
tuned on. It is a guess everywhere else. On a 8 GB laptop the same settings
swap; on a 64 GB desktop they leave most of the machine idle.

The principle this exists to serve is that **installation is not residency**.
Having a model on disk says nothing about whether it should be held in memory
right now, alongside whatever else is resident. So this module answers two
separate questions:

    what is this machine?          -> Machine.detect()
    what fits, given what is       -> Machine.can_host() / headroom()
    already running?

Deliberately not a rules engine. There is no table mapping RAM to model
names, because such a table is wrong the moment a new model appears and
cannot account for what else the user has open. Callers get measurements and
a small amount of arithmetic, and make their own decisions.

Nothing here downloads, installs, or changes anything.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field

from logs.logger import logger

GB = 1024 ** 3


@dataclass(frozen=True)
class Machine:
    """A snapshot of what the hardware is and what it currently has spare."""

    system: str
    architecture: str
    chip: str
    cpu_cores: int
    total_memory_gb: float
    available_memory_gb: float
    swap_used_gb: float
    free_disk_gb: float
    unified_memory: bool
    metal: bool
    notes: list[str] = field(default_factory=list)

    # ── detection ─────────────────────────────────────────

    @classmethod
    def detect(cls) -> "Machine":
        system = platform.system()
        architecture = platform.machine()
        notes: list[str] = []

        total = _total_memory_bytes() / GB
        available, swap = _memory_pressure_gb()
        disk = shutil.disk_usage(os.path.expanduser("~")).free / GB

        chip = _chip_name() or f"{system} {architecture}"
        # Apple Silicon shares one pool between CPU and GPU, which is the
        # single most important fact for deciding what can be resident: a
        # model on the GPU is taking memory away from everything else, not
        # using a separate card's.
        unified = system == "Darwin" and architecture == "arm64"
        metal = unified
        if unified:
            notes.append("unified memory: GPU and CPU draw on the same pool")

        if system != "Darwin":
            notes.append(
                f"{system} is not yet supported for computer control; "
                "memory and disk figures are still usable"
            )

        return cls(
            system=system, architecture=architecture, chip=chip,
            cpu_cores=os.cpu_count() or 1,
            total_memory_gb=round(total, 2),
            available_memory_gb=round(available, 2),
            swap_used_gb=round(swap, 2),
            free_disk_gb=round(disk, 2),
            unified_memory=unified, metal=metal, notes=notes,
        )

    # ── reasoning about residency ─────────────────────────

    def headroom_gb(self, reserve_gb: float = 3.0) -> float:
        """Memory that could be given to a model right now.

        `reserve_gb` is what the rest of the system needs to stay responsive:
        the window server, the browser the user has open, Mike himself.
        Measured on the machine this was written on, ignoring that reserve is
        how a 6.2 GB model plus a 0.9 GB voice drove free memory to 60 MB and
        made every reply stutter.
        """
        return round(max(0.0, self.available_memory_gb - reserve_gb), 2)

    def can_host(self, size_gb: float, reserve_gb: float = 3.0) -> bool:
        return self.headroom_gb(reserve_gb) >= size_gb

    def under_pressure(self) -> bool:
        """Is the machine already struggling?

        Swap in use is not itself a problem — macOS swaps eagerly and never
        reclaims — so this asks whether memory is *currently* scarce.
        """
        return self.available_memory_gb < 2.0

    def describe(self) -> str:
        lines = [
            f"{self.chip} · {self.cpu_cores} cores · {self.system} {self.architecture}",
            f"memory: {self.total_memory_gb:.0f} GB total, "
            f"{self.available_memory_gb:.1f} GB available now",
            f"disk: {self.free_disk_gb:.0f} GB free",
        ]
        if self.swap_used_gb:
            lines.append(f"swap in use: {self.swap_used_gb:.1f} GB")
        lines.extend(f"note: {n}" for n in self.notes)
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "chip": self.chip, "system": self.system,
            "architecture": self.architecture, "cpu_cores": self.cpu_cores,
            "total_memory_gb": self.total_memory_gb,
            "available_memory_gb": self.available_memory_gb,
            "swap_used_gb": self.swap_used_gb,
            "free_disk_gb": self.free_disk_gb,
            "unified_memory": self.unified_memory, "metal": self.metal,
            "notes": list(self.notes),
        }


# ── platform details, each failing softly ─────────────────

def _total_memory_bytes() -> int:
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                 capture_output=True, text=True, timeout=5)
            return int(out.stdout.strip())
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        logger.debug("Could not read total memory.", exc_info=True)
    return 0


def _memory_pressure_gb() -> tuple[float, float]:
    """Available memory and swap in use, in GB.

    "Available" means free plus inactive: inactive pages are cache the system
    will hand back on demand, so counting only free memory understates what a
    model could have by several gigabytes.
    """
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["vm_stat"], capture_output=True,
                                 text=True, timeout=5).stdout
            page = 16384
            values: dict[str, int] = {}
            for line in out.splitlines():
                if "page size of" in line:
                    page = int(line.split()[-2])
                    continue
                if ":" in line:
                    key, raw = line.split(":", 1)
                    try:
                        values[key.strip()] = int(raw.strip().rstrip("."))
                    except ValueError:
                        pass
            available = (values.get("Pages free", 0)
                         + values.get("Pages inactive", 0)) * page / GB

            swap_out = subprocess.run(["sysctl", "-n", "vm.swapusage"],
                                      capture_output=True, text=True, timeout=5).stdout
            swap = 0.0
            if "used =" in swap_out:
                swap = float(swap_out.split("used =")[1].split("M")[0]) / 1024
            return available, swap

        with open("/proc/meminfo") as handle:
            info = {}
            for line in handle:
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0]) * 1024
        return info.get("MemAvailable", 0) / GB, 0.0
    except Exception:
        logger.debug("Could not read memory pressure.", exc_info=True)
    return 0.0, 0.0


def _chip_name() -> str:
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True, timeout=5)
            return out.stdout.strip()
    except Exception:
        logger.debug("Could not read the chip name.", exc_info=True)
    return ""


_cached: Machine | None = None


def current(refresh: bool = False) -> Machine:
    """The machine as it is. Static facts are cached; pressure is not.

    Memory pressure changes second to second, so a cached snapshot of it
    would be worse than no snapshot — a caller would decide what fits based
    on how the machine looked when Mike started.
    """
    global _cached
    if refresh or _cached is None:
        _cached = Machine.detect()
        return _cached
    available, swap = _memory_pressure_gb()
    return Machine(
        **{**_cached.as_dict(),
           "available_memory_gb": round(available, 2),
           "swap_used_gb": round(swap, 2),
           "notes": list(_cached.notes)}
    )
