<!--
*******************************************************************************
Copyright (c) 2025 Contributors to the Eclipse Foundation
See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.
This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0
SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->
# Integration Test Framework
This module implements support for running [`pytest`](https://docs.pytest.org/en/latest/contents.html) based tests
for ECUs (Electronic Control Units) in automotive domain.
The Integration Test Framework aims to support ECU testing on real hardware and on simulation (QEMU or QVP) as target.

## Usage
In your `MODULE.bazel` file, add the following line to include the ITF dependency:
```
bazel_dep(name = "itf", version = "0.1.0")
```

In your `.bazelrc` file, add the following line to include ITF configurations:
```
common --registry=https://raw.githubusercontent.com/eclipse-score/bazel_registry/main/
common --registry=https://bcr.bazel.build

build:qemu-integration --config=x86_64-qnx
build:qemu-integration --run_under=@score_itf//scripts:run_under_qemu
build:qemu-integration --test_arg="--qemu"
build:qemu-integration --test_arg="--os=qnx"
```

## Configuration options
Several additional command line options can be added to the execution to customize it.
These are divided into two groups: bazel configs and pytest arguments.

The bazel configs generally influence the build options. These include modifying the bazel `select()` statements, changing the dependencies tree, etc. Available configs are:
- `--config=qemu-integration` - Run ITF for QEMU target. If `--qemu_image` is specified, ITF will automatically start QEMU with the provided image before running the tests.

The Python arguments customize the runtime behavior.
They can be found in [`score/itf/plugins/base/base_plugin.py`](score/itf/plugins/base/base_plugin.py) file or displayed by passing `--test_arg="--help"` to any test invocation.
All the options can be passed in command line wrapped in `--test_arg="<...>"` or in `args` parameter of `py_itf_test` macro in `BUILD` file.

Runtime arguments:
* `--target_config` - Path to the target configuration file
* `--dlt_receive_path` - Path to DLT receive binary (Internally provided in `py_itf_test` macro)
* `--ecu` - Target ECU under test
* `--os` - Target Operating System
* `--qemu` - Run tests with QEMU image
* `--qemu_image` - Path to a QEMU image
* `--qvp` - Run tests with QVP simulation
* `--hw` - Run tests against connected HW


## Target configuration file
Target configuration file is a JSON file defining the ECUs under test, their connection parameters, DLT settings, etc.
Target configuration file path can be specified using `--target_config` argument.
An example file for S-CORE QEMU can be found in [`config/target_config.json`](config/target_config.json).

```json
{
    "S_CORE_ECU_QEMU_BRIDGE_NETWORK": {
        "performance_processor": {
            "name": "S_CORE_ECU_QEMU_BRIDGE_NETWORK_PP",
            "ip_address": "192.168.122.76",
            "ext_ip_address": "192.168.122.76",
            "ssh_port": 22,
            "diagnostic_ip_address": "192.168.122.76",
            "diagnostic_address": "0x91",
            "serial_device": "",
            "network_interfaces": [],
            "ecu_name": "s_core_ecu_qemu_bridge_network_pp",
            "data_router_config": {
                "vlan_address": "127.0.0.1",
                "multicast_addresses": []
            },
            "qemu_num_cores": 2,
            "qemu_ram_size": "1G"
        },
        "safety_processor": {
            "name": "S_CORE_ECU_QEMU_BRIDGE_NETWORK_SC",
            "ip_address": "192.168.122.76",
            "diagnostic_ip_address": "192.168.122.76",
            "diagnostic_address": "0x90",
            "serial_device": "",
            "use_doip": true
        },
        "other_processors": {}
    },
    ...
}
```

Target configuration file contains a dictionary of ECUs. Each ECU contains its processors (`performance_processor`, `safety_processor`, `other_processors`).
Each processor contains its connection parameters.

Performance processor: `performance_processor`
* `name` - Name of the processor
* `ip_address` - IP address of the processor
* `ext_ip_address` - External IP address of the processor (for cases where no direct access is possible)
* `ssh_port` - SSH port of the processor
* `diagnostic_ip_address` - IP address for diagnostics communication
* `diagnostic_address` - Diagnostic address of the processor
* `serial_device` - Serial device path if serial connection is used
* `network_interfaces` - List of network interfaces on the processor
* `ecu_name` - Name of the ECU as known on the target system
* `data_router_config` - Configuration for data router
  * `vlan_address` - VLAN address for data router
  * `multicast_addresses` - List of multicast addresses for data router
* `qemu_num_cores` - Number of CPU cores to allocate for QEMU
* `qemu_ram_size` - Amount of RAM to allocate for QEMU
* `use_doip` - Whether to use DoIP for diagnostics communication

Safety processor: `safety_processor`
* `name` - Name of the processor
* `ip_address` - IP address of the processor
* `diagnostic_ip_address` - IP address for diagnostics communication
* `diagnostic_address` - Diagnostic address of the processor
* `serial_device` - Serial device path if serial connection is used
* `use_doip` - Whether to use DoIP for diagnostics communication

Other processors: `other_processors`
* Dictionary of other processors with same parameters as `safety_processor`.

## Bazel
ITF provides a macro `py_itf_test` to simplify the creation of ITF based tests.
BUILD file example:
```python
load("//:defs.bzl", "py_itf_test")
load("//score/itf/plugins:plugins.bzl", "base")

py_itf_test(
    name = "test_ssh_qemu",
    srcs = [
        "test/itf/test_ssh.py",
    ],
    args = [
        "--target_config=$(location target_config.json)",
        "--ecu=s_core_ecu_qemu",
        "--qemu_image=$(location //build:init)",
    ],
    plugins = [
        "base",
    ],
    data = [
        "//build:init",
        "target_config.json",
    ],
)
```

## Regenerating pip dependencies
```bash
bazel run //:requirements.update
```

## Running tests
```bash
bazel test //test/...
```

Specify additionally:
- `--test_arg="-s"` to get stdout/err from pytest
- `--test_output=all` to get stdout/err from bazel
- `--nocache_test_results` not to cache test runs

## Preparation for testing with QEMU
To run the tests against QEMU target, KVM must be installed.
Following steps are for Ubuntu. See this tutorial: https://help.ubuntu.com/community/KVM/Installation

First, check if your system supports KVM. Run `ls -l /dev/kvm` - if the device is there, your system does support it.

Install necessary packages:
```bash
sudo apt-get install qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils python3-guestfs qemu-utils libguestfs-tools
sudo adduser `id -un` libvirt
sudo adduser `id -un` kvm
```

After the installation, you need to relogin - either reboot or ``` sudo login `id -un` ```.
Verify that the user is in KVM group by running: ``` groups ```.

## Running test against QNX Qemu
ITF can be run against running Qemu defined here https://github.com/eclipse-score/reference_integration/tree/main/qnx_qemu.
Steps:
* Checkout repository https://github.com/eclipse-score/reference_integration
* Run ssh test with qemu started with bridge network
  * Start Qemu with bridge network from `reference_integration/qnx_qemu` folder:
    ```bash
    bazel run --config=x86_64-qnx //:run_qemu
    ```
  * Run ITF test from `itf` folder:
    ```bash
    bazel test //test:test_ssh_bridge_network --test_output=streamed
    ```
  * Note: If it fails, check `IP address set to:` in logs of started Qemu and update IP addresses in `itf/config/target_config.json` for `S_CORE_ECU_QEMU_BRIDGE_NETWORK`
* Run ssh test with qemu started with port forwarding
  * Start Qemu with bridge network from `reference_integration/qnx_qemu` folder:
    ```bash
    bazel run --config=x86_64-qnx //:run_qemu_portforward
    ```
  * Run ITF test from `itf` folder:
    ```bash
    bazel test //test:test_ssh_port_forwarding --test_output=streamed
    ```
* Run ITF test with Qemu started automatically (https://github.com/eclipse-score/reference_integration/blob/main/qnx_qemu/README.md)
  * From `reference_integration/qnx_qemu` folder, run:
    ```bash
    bazel test --config=qemu-integration //:test_ssh_qemu --test_output=streamed
    ```

## Writing tests
Tests are written using `pytest` framework. Tests can utilize various ITF plugins to interact with the target ECU, perform diagnostics, capture logs, etc.

Example test using SSH to connect to the target ECU:
```python
from score.itf.core.com.ssh import execute_command


def test_ssh_with_default_user(target_fixture):
    with target_fixture.sut.ssh() as ssh:
        execute_command(ssh, "echo 'Username:' $USER && uname -a")
```

Main plugin is base plugin which provides common functionality, fixtures and argument parsing.
It should be specified in the `plugins` parameter of `py_itf_test` macro.
```python
    plugins = [
        "score.itf.plugins.base.base_plugin",
    ],
```

Fixtures provided by base plugin are:
* [`target_fixture`](score/itf/core/base/base_plugin.py#L80) - Provides access to the target ECU under test, its processors, connection methods, etc.
* [`test_config_fixture`](score/itf/core/base/base_plugin.py#L69) - Provides access to the test configuration, command line arguments.
* [`target_config_fixture`](score/itf/core/base/base_plugin.py#L74) - Provides access to the target configuration read from target configuration file.

### Communication with ECU
Main communication with target ECU is done via [`target_fixture`](score/itf/core/base/base_plugin.py#L80).

Usage of `target_fixture` to get performance processor SSH connection:
```python
with target_fixture.sut.performance_processor.ssh() as ssh:
    # Use ssh connection
```

Usage of `target_fixture` to get performance processor SFTP connection:
```python
with target_fixture.sut.performance_processor.sftp() as sftp:
    # Use sftp connection
```

Usage of `target_fixture` to ping performance processor:
```python
target_fixture.sut.performance_processor.ping()
```

Usage of `target_fixture` to check is ping lost of performance processor:
```python
target_fixture.sut.performance_processor.ping_lost()
```

For parameters of above mentioned functionality see [`target_processor.py`](score/itf/core/base/target/processors/target_processor.py).

## Capture DLT messages
By default ITF will start capturing DLT messages from the target ECU's performance processor
when the test starts and stop capturing when the test ends.
Captured DLT messages can be found in `dlt_receive.dlt` which can be found in `bazel-testlogs` folder.

Class [`DltWindow`](score/itf/plugins/dlt/dlt_window.py) can used in test to capture DLT messages in tests.
```python
dlt = DltWindow(dlt_file="./my_test.dlt")
with dlt.record():
    # Do something which will send DLT messages

# Stop recording
dlt.stop()

# Load captured DLT messages from file
dlt.load()

# Query captured DLT messages to check does it contains expected messages
query_dict = dict(apid=re.compile(r"LOGC"), payload_decoded=re.compile(rf".*{process}\[my_process.*\]:\s+Thread priority set to 70"))
dlt_thread_results = dlt.find(query=query_dict)

# Clear captured messages
dlt.clear()
```
# Software Component Test Framework
Software Component Test Framework allows developers to execute a single or multiple applications
in order to interact with them through their external interfaces (pipes, sockets, shared memory, etc.).

# Design

The framework uses [`pytest`](https://docs.pytest.org/en/latest/contents.html) as a test runner.
Applications are run in a sandboxed environment using `bubblewrap`. The sandbox environment is shared
between all applications and mocks used in the test, and resembles in structure the target file system.
Each application runs as a separate process under sandboxed root directory, thus the execution is separated
from your file system. This also helps parallelize test execution.

Common use cases consist of verifying a single application integration to the ARA:COM stack:
does it report states Running/Terminating properly, does it produce expected output for given input.

The key functionality tested is the SOME-IP and IPC communication. SOME-IP is typically used across
ECUs and is built on top of Ethernet, whereas IPC is for inside ECU communication and currently is
based on Unix domain sockets.

These interfaces are defined within Franca+ files, and the framework is meant to test against those.
In order to do that, you need to provide the mirror Franca+ files, i.e.: for each Required Port,
the mirror Franca+ must contain a Provided Port. The scope of the provided Franca+ mirrored model is
up to you, but at least should ensure the application under test starts correctly and can be tested.
From these, we can generate C++/Python bindings that allow for expressive tests to be written.

Note: Currently the recommended solution to provide and use the mirrored code to send/receive
to/from your application is to wrap the code in a C++/Python bindings library.
Alternatively, the entire C++ code could be wrapped into a separate binary and started in the framework.

## Setup
To ensure your development setup supports running SCTF,
you need to have Python3, `bubblewrap`, `catchsegv` (`glibc-tools`) installed.
All other packages are managed by Bazel build system, and should not need require manual installation. To see the list of dependencies please refer to the Bazel BUILD file and various deps sections.

If you're running on Ubuntu 23.10 or higher you need to disable apparmor to unblock unshare,
this however should be done before the bazel server is started! If an instance of bazel is already
running. it needs to be shutdown before running the next commands.
```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=0
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
```

To make this change permanent (survives reboot), add the following lines to `/etc/sysctl.conf`,
then reload with `sudo sysctl --system`
```bash
kernel.apparmor_restrict_unprivileged_unconfined=0
kernel.apparmor_restrict_unprivileged_userns=0
```

Source: https://ubuntu.com/blog/ubuntu-23-10-restricted-unprivileged-user-namespaces

If your are running Ubuntu 24.04 or higher you need to install the following:
- `catchsegv` is not available by default on Ubuntu 24.04. Install it with
```bash
sudo apt-get install glibc-tools
```
## Running tests
```bash
bazel test //test:test_simple_environment --config=sctf
```
## Bazel
SCTF provides a macro [`py_sctf_test`](bazel/py_sctf_test.bzl) to simplify the creation of SCTF based tests.
```python
def py_sctf_test(
    name,                   # Name of the test target
    srcs,                   # List of source files for the test
    main=None,              # Main entry point for the test (optional)
    data=None,              # Data files needed for the test. Put C++ test binary dependencies here
    deps=None,              # List of additional dependencies for the test.
    extra_tags=None,        # Additional tags to add to the test target.
    args = None,            # Additional arguments to pass to SCTF
    env = None,             # Environment variables to set for the test.
    timeout = "moderate",   # Timeout setting for the test.
    flaky = False           # If True, marks the test as flaky
)
```
BUILD file example:
```python
load("//:defs.bzl", "py_sctf_test")

py_sctf_test(
    name = "test_simple_environment",
    srcs = [
        "test_simple_environment.py",
    ],
)
```
