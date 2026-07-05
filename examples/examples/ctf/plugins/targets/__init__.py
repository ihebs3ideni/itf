"""Interchangeable *target* plugins.

Each module here assembles a target and publishes the shared ``ctf/cap/*``
capability contracts (and, where relevant, ``ctf/scenario/*``). They are
mutually exclusive within a session -- a level's conftest registers exactly one.
Swapping the target = registering a different one of these modules.
"""
