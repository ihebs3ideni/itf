#!/bin/bash
set -euo pipefail

# Check if TEST_UNDECLARED_OUTPUTS_DIR is set
CMD_UNDECLARED_OUTPUTS_DIR="true"
if [[ -n "${TEST_UNDECLARED_OUTPUTS_DIR}" ]]; then
	CMD_UNDECLARED_OUTPUTS_DIR="export TEST_UNDECLARED_OUTPUTS_DIR=$TEST_UNDECLARED_OUTPUTS_DIR"
else
	TEST_UNDECLARED_OUTPUTS_DIR="/tmp"
fi

# Set the ulimits accordingly, for the core dumps to be produced
# Ensure the '/proc/sys/kernel/core_pattern' contents are relative, for dumps to be produced within sandbox
#   i.e.: core.%e.%p (core.<name>.<pid>)
# The pattern cannot be set inside this script
CMD_CORE_DUMP="ulimit -c unlimited"

# Prepare the /etc overlayfs for providing global configuration files
# For some reason trying to use SCTF directory as 'upper' directly fails to create overlay mount
# TODO: Currently disabled due to failing in CI check/gate, SPPAD-66542
# ETC_OVERLAY_DIR="platform/aas/tools/sctf/bazel_gen/etc_overlay"
# ETC_OVERLAY_UPPER_DIR="/tmp/etc_overlay"
# ETC_OVERLAY_WORK_DIR="/tmp/workdir"
# if [[ -d "${ETC_OVERLAY_DIR}" ]]; then
#   CMD_OVERLAYFS="mkdir ${ETC_OVERLAY_WORK_DIR} &&
#     cp -r ${ETC_OVERLAY_DIR} ${ETC_OVERLAY_UPPER_DIR} &&
#     mount -t overlay -o lowerdir=/etc,upperdir=${ETC_OVERLAY_UPPER_DIR},workdir=${ETC_OVERLAY_WORK_DIR} etc_overlay /etc"
# else
#   CMD_OVERLAYFS=":"  # essentially noop
# fi

# Copy possible Python core dump on crash
function finish {
  PYTHON_CORE_DUMP_PATTERN="./core.python3.*"
  if compgen -G "${PYTHON_CORE_DUMP_PATTERN}" > /dev/null; then
    echo "Saving crashed Python core dump matching pattern '${PYTHON_CORE_DUMP_PATTERN}' to the test outputs directory, see bazel-testlogs/<path_to_your_test>/test.outputs/outputs.zip."
    cp "${PYTHON_CORE_DUMP_PATTERN}" "${TEST_UNDECLARED_OUTPUTS_DIR}/"
  fi
}
trap finish EXIT

# Run the concatenated commands in an unnamed network namespace for isolation
unshare -U -n --map-root-user --mount /bin/bash -c \
  "${CMD_UNDECLARED_OUTPUTS_DIR} &&
  ${CMD_CORE_DUMP} &&
  catchsegv ${*}"
