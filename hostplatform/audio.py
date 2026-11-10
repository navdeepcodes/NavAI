"""Which microphone is Mike about to open -- and will it ruin the sound?

A Bluetooth headset has two modes. Playing music or a video uses a stereo,
high-quality one. The moment ANY app opens the headset's microphone, the whole
headset drops to a hands-free "phone call" mode: mono, 16 kHz, and on many
headsets it sounds muffled, thin and oddly bass-heavy. It stays that way for as
long as the microphone stays open.

Measured on a Mac with Mike running ("Hey Mike" listening): the headset's
output fell from 44,100 Hz to 16,000 Hz, and came back the moment Mike quit.
Mike held the microphone open all day for the wake word, so anyone listening
through AirPods or any Bluetooth headset had their audio ruined for as long as
Mike was open.

So Mike asks, before opening the microphone, whether the one it would use is
Bluetooth. If it is, the always-on wake word waits, and recording (the mic
button, F6) uses the computer's own microphone instead, leaving the headset's
sound alone.

macOS only. Elsewhere every answer is "no", which keeps today's behaviour.
"""
from __future__ import annotations

import ctypes
import platform
import struct

from logs.logger import logger


def _four(code: str) -> int:
    return struct.unpack(">I", code.encode("ascii"))[0]


class _Address(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32),
                ("element", ctypes.c_uint32)]


_SYSTEM_OBJECT = 1
_BLUETOOTH = {_four("blue"), _four("blea")}          # classic and low-energy


def _core_audio():
    return ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")


def _property(object_id: int, selector: str) -> int | None:
    """One 32-bit CoreAudio property of an object, or None if it can't be read."""
    try:
        core = _core_audio()
        address = _Address(_four(selector), _four("glob"), 0)
        value, size = ctypes.c_uint32(0), ctypes.c_uint32(4)
        status = core.AudioObjectGetPropertyData(
            ctypes.c_uint32(object_id), ctypes.byref(address), ctypes.c_uint32(0), None,
            ctypes.byref(size), ctypes.byref(value))
        return value.value if status == 0 else None
    except Exception:
        logger.debug("Could not read a CoreAudio property.", exc_info=True)
        return None


def default_input_is_bluetooth() -> bool:
    """True if the microphone Mike would open by default is a Bluetooth one."""
    if platform.system() != "Darwin":
        return False
    device = _property(_SYSTEM_OBJECT, "dIn ")        # default input device
    if not device:
        return False
    return _property(device, "tran") in _BLUETOOTH    # its transport type


#: Names of the computer's own microphone, in the order worth preferring.
_BUILT_IN_HINTS = ("macbook", "built-in", "builtin", "internal", "imac", "mac mini",
                   "mac studio", "mac pro")


def pick_built_in_input(devices: list[dict], default_index: int | None) -> int | None:
    """The index of the computer's own microphone among `devices` (the list
    sounddevice returns), or None if it can't be told apart. Never the default
    device itself: that is the Bluetooth one this exists to avoid."""
    default_name = (devices[default_index]["name"]
                    if default_index is not None and 0 <= default_index < len(devices) else "")
    for hint in _BUILT_IN_HINTS:
        for index, device in enumerate(devices):
            name = str(device.get("name", ""))
            if (device.get("max_input_channels", 0) > 0 and index != default_index
                    and name != default_name and hint in name.lower()):
                return index
    return None


def recording_device() -> int | None:
    """The sounddevice input index to record from, or None for the system
    default. Chooses the computer's own microphone when the default is
    Bluetooth, so recording does not put the headset into phone-call mode."""
    if not default_input_is_bluetooth():
        return None
    try:
        import sounddevice as sd

        default_index = sd.default.device[0]
        choice = pick_built_in_input(list(sd.query_devices()), default_index)
        if choice is not None:
            logger.info("Recording from the built-in microphone: the default input is "
                        "a Bluetooth headset, and using it would degrade its sound.")
        return choice
    except Exception:
        logger.debug("Could not choose a built-in microphone.", exc_info=True)
        return None
