"""The local provider: Gemma 4 in-process through llama-cpp-python.

`catalog` says what files are needed, `downloads` gets them, `runtime` keeps the two slots
resident and owns the adapter registry, `model` is the Pydantic AI model, `gemma` is the wire
format it speaks, and `check` is the sanity check.
"""
