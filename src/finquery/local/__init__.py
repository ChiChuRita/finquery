"""The local provider: Gemma 4 E4B and Qwen3.5 9B in-process through llama-cpp-python.

`catalog` says what files are needed, `downloads` gets them, `runtime` keeps the two slots
resident and owns the adapter registry, `model` is the Pydantic AI model, `wire` is the shape
of a chat wire format with `gemma` (fast slot) and `qwen` (quality slot) filling it in, and
`check` is the sanity check.
"""
