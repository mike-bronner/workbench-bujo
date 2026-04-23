"""Scribe verb implementations.

Each module owns exactly one verb. Verbs accept validated input models from
`schemas`, dispatch backend calls through `NotebookBackend`, and return
validated output models. Nothing here touches storage directly.
"""
