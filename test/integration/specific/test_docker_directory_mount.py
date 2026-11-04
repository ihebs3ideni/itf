"""A Docker target can bind-mount a host directory declared in its target file."""

import score.itf as itf


@itf.requires("command")
def test_directory_mount_exposes_all_files(target):
    assert target.command.exec("test -f /extra/mount/UTC")[0] == 0
