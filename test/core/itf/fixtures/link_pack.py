# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""One action, two states, two probes: connecting both reaches the peer and opens a session."""

from score.itf.core import delivers, provides


class Link:
    def __init__(self):
        self.peer_answers = False  # what a reachability probe can see
        self.session = False  # what a session probe can see
        self.connects = 0
        self.break_reachability = False

    def connect(self):
        self.connects += 1
        self.peer_answers = not self.break_reachability
        self.session = True


@provides("link.handle", name="link_pack.link")
def make_link(config) -> Link:
    return Link()


@delivers("session.open", name="link_pack.connect", also_delivers=("peer.reachable",), uses={"link": "link.handle"})
def connect(link):
    link.connect()


@connect.probe
def session_is_open(link):
    return link.session


@connect.probe_for("peer.reachable")
def peer_answers(link):
    return link.peer_answers
