"""The local provider: Gemma 4 E4B and Gemma 4 26B A4B in-process through llama-cpp-python.

`catalog` says what files are needed, `downloads` gets them, `runtime` keeps the one loaded
model and owns the adapter registry, `model` is the Pydantic AI model, `wire` is the shape
of a chat wire format with `gemma` (every catalog entry) and `qwen` (the benchmark candidates)
filling it in, and `check` is the sanity check.
"""
