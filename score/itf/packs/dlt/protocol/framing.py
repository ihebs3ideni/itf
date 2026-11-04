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
"""DLT standard and extended header framing, independent of TCP or UDP transport.

Payloads remain raw bytes; this codec does not decode verbose-mode typed arguments.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

_HTYP_UEH = 0x01  # extended header present
_HTYP_MSBF = 0x02  # multi-byte header fields are big-endian
_HTYP_WEID = 0x04  # ECU id present
_HTYP_WSID = 0x08  # session id present
_HTYP_WTMS = 0x10  # timestamp present
_VERSION = 1


@dataclass(frozen=True)
class DltMessage:
    ecu_id: str
    apid: str
    ctid: str
    counter: int
    payload: bytes

    def text(self) -> str:
        return self.payload.decode("utf-8", errors="replace")


def _fixed4(value: str) -> bytes:
    return value.encode("ascii", errors="replace")[:4].ljust(4, b"\x00")


def encode_message(*, ecu_id: str, apid: str, ctid: str, counter: int, payload: bytes) -> bytes:
    """One correctly framed message: standard header + ECU id + extended header + payload."""
    htyp = _HTYP_UEH | _HTYP_MSBF | _HTYP_WEID | (_VERSION << 5)
    ext_header = struct.pack("!BB4s4s", 0x01, 1, _fixed4(apid), _fixed4(ctid))
    body = _fixed4(ecu_id) + ext_header + payload
    total_len = 4 + len(body)  # the 4 standard-header bytes themselves count toward LEN
    return struct.pack("!BBH", htyp, counter & 0xFF, total_len) + body


def decode_message(buf: bytes) -> tuple[DltMessage | None, bytes]:
    """Decode one message, returning incomplete input unchanged for the caller to retry."""
    if len(buf) < 4:
        return None, buf
    htyp, counter, total_len = struct.unpack("!BBH", buf[:4])
    if len(buf) < total_len:
        return None, buf

    offset = 4
    ecu_id = ""
    if htyp & _HTYP_WEID:
        ecu_id = buf[offset : offset + 4].rstrip(b"\x00").decode("ascii", errors="replace")
        offset += 4
    if htyp & _HTYP_WSID:
        offset += 4
    if htyp & _HTYP_WTMS:
        offset += 4

    apid = ctid = ""
    if htyp & _HTYP_UEH:
        _msin, _noar, apid_b, ctid_b = struct.unpack("!BB4s4s", buf[offset : offset + 10])
        apid = apid_b.rstrip(b"\x00").decode("ascii", errors="replace")
        ctid = ctid_b.rstrip(b"\x00").decode("ascii", errors="replace")
        offset += 10

    payload = buf[offset:total_len]
    return DltMessage(ecu_id=ecu_id, apid=apid, ctid=ctid, counter=counter, payload=payload), buf[total_len:]
