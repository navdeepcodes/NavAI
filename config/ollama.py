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
NUM_CTX = 40960

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
# Image size barely matters below 640: 448px halves the prompt tokens (281 ->
# 147) and did not go faster. 640 stays.
VISION_RESOLUTION = 640

# Prose description, for "what's on my screen" — the answer is read by a
# person, so it can afford to be longer.
VISION_NUM_PREDICT = 96

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
