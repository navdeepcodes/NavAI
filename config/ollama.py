# Which backend powers Mike's brain. "ollama" today; adding another means
# adding a provider module, not changing the runtime.
BRAIN_PROVIDER = "ollama"

# Context Mike allocates per request. Ollama hands a request only part of
# this (see brain/providers/ollama_provider.USABLE_FRACTION_OF_CTX), so the
# planner budgets against the usable share rather than this number.
#
# 16384 rather than 8192 because 8192 was actively harming multi-step work:
# with Mike's prompt and 30 tool schemas costing ~5,300 tokens of a ~5,500
# token budget, an agency loop had almost no room for its own history and was
# discarding its previous observations every step. Measured cost of the
# increase on this machine: 5.8GB -> 6.2GB resident, still entirely on GPU,
# with no change in latency. The model's own window is far larger again
# (262k); this is a memory decision, not a model limit.
# 24576 rather than 16384 so a long prompt and a full file can coexist. At
# 16384 the input budget (12,288) plus the largest allowed generation (4,096)
# came to exactly the window, leaving no margin — a long conversation would
# squeeze the output and reproduce the truncation this was meant to prevent.
# Measured on this 16 GB machine: 24,576 -> 6.3GB, 40,960 -> 6.9GB resident,
# still entirely on GPU. Roughly 0.2GB per 8k of context.
#
# 40,960 is the GPU-resident figure and every measurement above was taken
# with the model entirely on GPU. That does not hold on a machine with no
# GPU offload path: measured on an Intel Core Ultra 5 125U (integrated
# graphics only, Ollama reports "100% CPU"), the same settings gave 4.4
# tok/s and a 114-second wall clock for a two-word first reply. The KV
# cache for 40,960 tokens is allocated and carried on the CPU there, and
# the prefill it has to do before the first token is the dominant cost.
#
# So this is now a measurement, not a constant: a machine that can offload
# to a GPU keeps the tuned 40,960; a CPU-only machine gets a window sized
# to what it can actually process promptly. 8,192 is chosen to still clear
# the ~7,200-token prefix (instructions + 44 tool schemas) with room for a
# real exchange on top -- below that the prefix itself would not fit and
# tool schemas would start being truncated, which is the exact failure
# config/ollama.py's own history above records.
# 40,960 is kept only for the machine class it was actually measured on: a
# GPU with its own large memory pool (or Apple unified memory), where the
# file's own notes recorded 6.9GB resident "still entirely on GPU".
#
# An integrated GPU is a different machine class and must not inherit that
# number. It shares system RAM -- measured here, 8.1GB total for a 5.6GB
# model -- so a 40,960-token KV cache is what tips it over into spilling
# back to the CPU, which would undo the entire reason for using the GPU. The
# measured-good configuration on this hardware is 8,192 with the model fully
# resident ("100% GPU", 13s replies), so that is what an iGPU gets.
#: Below this, Mike stops being Mike.
#:
#: Only 0.75 of num_ctx is usable (USABLE_FRACTION_OF_CTX), and the prefix --
#: instructions plus 44 tool schemas -- is ~7,200 tokens. At num_ctx=8192 the
#: usable budget is 6,144, so context planning does what it is designed to do
#: and drops tools to make the prompt fit: "offering 14 of 44 tools". That is
#: not a slower Mike, it is a Mike missing two thirds of what he can do, and
#: no speed gain justifies it. Every tier below is therefore floored here,
#: including the CPU-only one -- a user on a weak machine gets a slow Mike,
#: never a crippled one.
MIN_NUM_CTX = 24576


def _num_ctx() -> int:
    try:
        from brain.hardware import current
        machine = current()
        if not machine.gpu_offload:
            # No GPU path. This is slow, and the honest answer to that is a
            # warm-up and a resident model (see warm() and KEEP_ALIVE), not a
            # context small enough to amputate the toolset.
            return MIN_NUM_CTX
        if machine.metal or machine.discrete_gpu:
            return 40960
        # An integrated GPU on a machine with real memory behind it. The
        # iGPU's pool is carved out of system RAM (measured: 8.8GB of a
        # 15.4GB machine), so what it can hold tracks total RAM rather than
        # anything GPU-specific. Verified on this hardware that 40,960 still
        # loads entirely onto the GPU -- "100% GPU (6.7/6.7 GB)" -- and
        # answers in 2.5s warm, so the larger window costs nothing here and
        # buys a much longer conversation and room for real file content.
        # Gated at 16GB because below that the carve-out is too small to
        # hold the model at all, let alone a 40,960-token cache, and a spill
        # back to CPU would cost far more than the extra context is worth.
        if machine.total_memory_gb >= 15.0:
            return 40960
        # An integrated GPU: 24,576, not 8,192.
        #
        # 8,192 was tried first, purely as a speed decision, and it broke
        # something more important than speed. Only 0.75 of num_ctx is
        # usable (USABLE_FRACTION_OF_CTX), so 8,192 leaves 6,144 tokens for a
        # prefix that is ~7,200 -- and context planning responded exactly as
        # designed, by dropping tools to make it fit: "offering 14 of 44
        # tools". Mike would have been faster and lost two thirds of what he
        # can do, which is not a trade worth making and is caught by
        # test_model_agnostic's prompt-fits assertions.
        #
        # 24,576 is the value this file's own history already settled on so
        # "a long prompt and a full file can coexist", and it costs roughly
        # 0.4GB more than 8,192 at ~0.2GB per 8k -- comfortably inside the
        # 8.1GB an iGPU had available with a 5.6GB model resident.
        return MIN_NUM_CTX
    except Exception:
        return 8192


NUM_CTX = _num_ctx()

# How long Ollama keeps the model resident after a request.
#
# Ollama's own default is 5 minutes, and Mike never overrode it -- which is
# the wrong default for what Mike actually is. A hotkey-summoned assistant
# is idle most of the time by design: that is the whole point of the Edge
# strip and the global hotkey. Under the default, any gap longer than five
# minutes silently evicted the model, so the next question paid a full
# reload of a multi-gigabyte model off disk *before* it could even begin
# prefill. Observed directly while measuring this: `ollama ps` reporting
# "Stopping..." between test runs, and first-reply timings that swung
# between 114s and over 300s depending purely on whether the model happened
# to still be resident.
#
# "-1" pins it until something evicts it deliberately. That is a real
# memory commitment (~6.3GB for qwen3.5:9b at this context), so it is taken
# only when the machine has the headroom to give -- brain.hardware already
# exists to answer exactly that question, and its reserve keeps the rest of
# the system responsive rather than driving the machine into swap, which it
# has measured going wrong before. A machine without that headroom keeps
# Ollama's default rather than being pushed into thrashing.
# Deliberately measured against *total* memory, not what happens to be free.
# Free memory is the wrong question here and asking it gives the wrong
# answer: by the time this is consulted the model is usually already
# resident, so the machine reports ~1.8GB free precisely *because* the 6.3GB
# model is loaded. Testing that against the model's size then concludes
# there is no room for the thing that is already there, and evicts it --
# guaranteeing the reload this exists to prevent. Total memory is the stable
# fact: it says whether this machine can host the model at all, and does not
# flip based on whether a browser happens to be open.
# -1 is an int, not the string "-1": Ollama parses a string as a duration
# ("5m", "30s") and rejects "-1" outright with HTTP 400. Caught because the
# warm-up request failed against a live server the moment this was wired up.
def _keep_alive() -> int | str:
    try:
        from brain.hardware import current
        return -1 if current().total_memory_gb >= 12.0 else "5m"
    except Exception:
        return "5m"


KEEP_ALIVE = _keep_alive()

OLLAMA_HOST = "http://127.0.0.1:11434"

# Brain and vision models. Both are ordinary configuration now — the runtime
# reads them through brain/providers, so changing either is a config change.
#
# qwen3.5:9b is the local brain: it is the only local model that verified a
# benchmark task, and it sees images, so one model serves as both brain and
# eyes. qwen3:8b was the previous brain and has been removed from this
# machine; it is re-pullable if a regression comparison is ever wanted.
#
# History worth keeping: Qwen3.5 9B was first judged "unable to call tools".
# That was wrong. Mike was sending a ~4,950-token prompt with a 4,096-token
# budget, so Ollama truncated the tool schemas and the model was blamed for
# the result. Context planning now prevents that for every model.
OLLAMA_CHAT_MODEL = "qwen3.5:9b"

# Vision may be the same model as the brain or a different one — Mike
# supports both. Today it is the same model: qwen3.5:9b sees images, so the
# brain is its own eyes and no second model is loaded.
OLLAMA_VISION_MODEL = "qwen3.5:9b"

OLLAMA_SUMMARY_MODEL = "qwen3.5:9b"

OLLAMA_EMBED_MODEL = "nomic-embed-text"

# Measured on this machine, qwen3.5:9b, warm model, three runs each:
#
#   prose prompt,      num_predict=150  ->  10.5s   ("This is a screenshot of
#                                                     a macOS desktop...")
#   structured prompt, num_predict=64   ->   5.3s
#   structured prompt, num_predict=48   ->   3.3s   (usable control list)
#
# Latency tracks output tokens almost exactly -- a flat ~16 tok/s -- so output
# length is the lever. Preprocessing is not: capture, resize and encode total
# 0.23s together, against 3-10s of inference.
#
# Image size barely matters below 640 *on a GPU with its own memory*: there,
# 448px halves the prompt tokens (281 -> 147) and did not go faster, which is
# why 640 stood for so long. That does not hold on an integrated GPU sharing
# system memory, where image prefill is a real cost. Measured here, same
# screen, same model:
#
#   640px, predict 64  ->  25.5s
#   512px, predict 64  ->  21.5s
#   448px, predict 56  ->  16.6s
#   384px, predict 48  ->  14.9s
#
# 448 is the point where it comes in under twenty seconds while the answer is
# still specific -- at 448 it still identified the IDE on screen by name. 384
# buys three more seconds and starts losing that, which is the whole value of
# looking.
VISION_RESOLUTION = 448

# Prose description, for "what's on my screen" — the answer is read by a
# person, so it can afford to be longer.
# 56, down from 96. A screen description is read aloud and glanced at, not
# studied, and latency tracks output tokens almost exactly -- the tail of a
# 96-token description was costing real seconds on a first-run starter
# ("Look at my screen"), where the wait is the whole impression.
VISION_NUM_PREDICT = 56

# UI perception for computer control. Short on purpose: the answer feeds the
# next action, not a reader.
VISION_UI_NUM_PREDICT = 48

VISION_TEMPERATURE = 0.1

# Asking for a control list rather than a description is both faster and more
# useful. The prose prompt spent its budget on preamble; this returns lines
# the runtime can act on.
VISION_UI_PROMPT = (
    "List the interactive controls visible on this screen: buttons, text "
    "fields, links, menu items, checkboxes. One per line, formatted as: "
    'role "label". If a label is unreadable, write role "?". '
    "Then a final line starting with STATE: describing the current visual "
    "state in one sentence. No preamble, no explanation."
)
