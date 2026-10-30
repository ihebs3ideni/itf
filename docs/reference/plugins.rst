..
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

.. _itf_plugins_reference:

Packs
=====

Each pack is loaded by Bazel label (``py_itf_test(plugins = [...])``); a recipe selects providers
by name with ``using:``. The `pack marketplace <../catalog.html>`_ is the same catalog as a browsable page: every contract and
state with its providers, consumers, packs, configuration and copy-ready recipe snippets. The catalog
lists every member, signature, config key and prerequisite,
built from the packs' code:

.. code-block:: bash

   bazel run //tools/catalog:query -- sql "SELECT * FROM v_capability_providers"
   bazel run //tools/catalog:query -- sql "SELECT * FROM v_state_deliverers"
   bazel run //tools/catalog:query -- serve

.. list-table::
   :header-rows: 1

   * - Label
     - Providers
     - Actions (state)
   * - ``//score/itf/packs/docker``
     - ``docker.instance``, ``docker.exec``, ``docker.process``, ``docker.files``, ``docker.endpoint``
     - ``docker.start_platform`` (platform.up)
   * - ``//score/itf/packs/qemu``
     - ``qemu.instance``, ``qemu.console``, ``qemu.endpoint``, ``qemu.credentials``
     - ``qemu.start_platform`` (platform.up), ``qemu.open_console`` (console.open)
   * - ``//score/itf/packs/ssh``
     - ``ssh.shell``, ``ssh.exec``, ``ssh.process``, ``sftp.files``
     - ``ssh.open_session`` (shell.open, network.reachable)
   * - ``//score/itf/packs/net``
     - ``static.endpoint``, ``key.credentials``, ``password.credentials``
     - —
   * - ``//score/itf/packs/ping`` / ``:boot``
     - ``icmp.ping``
     - ``icmp.await_boot`` (platform.up), ``:boot`` only
   * - ``//score/itf/packs/dlt`` / ``:multicast`` / ``:receive``
     - ``dlt.stream`` / ``dlt.multicast`` / ``dlt.receive``, ``dlt.receive_tcp``
     - ``dlt.subscribe_stream`` / ``dlt.join_multicast`` / ``dlt.start_receive`` (logs.active)
   * - ``//score/itf/packs/dlt:on_target``
     - the ``dlt_on_target`` fixture
     - —
   * - ``//score/itf/packs/pcap`` / ``:host``
     - ``tcpdump.capture``
     - ``tcpdump.start_capture`` / ``tcpdump.start_host_capture`` (capture.running)
   * - ``//score/itf/packs/serial``
     - ``serial.console``, ``serial.exec``
     - ``serial.open_console`` (console.open)
   * - ``//score/itf/packs/core_dump``
     - ``itf_teardown`` hook (``--//score/itf/packs/core_dump:extract_core_dumps``)
     - —

Offline variants (``:sim``) of docker, ssh, dlt and pcap stand in when no daemon or hardware is
available. score_tooling's attribute plugin is ``//:attribute_plugin``. The original plugins are gone; see
:doc:`../how-to/migrate`.
