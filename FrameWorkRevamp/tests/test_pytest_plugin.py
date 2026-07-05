from __future__ import annotations


def test_dut_fixture_end_to_end(pytester):
    pytester.makeconftest(
        """
        import pytest
        from ctf.contracts import provides, requires
        from ctf.descriptor import Descriptor

        @provides("greeting")
        @requires("name")
        def greeting(name):
            return f"hello {name}"

        def pytest_ctf_setup(registry, config):
            registry.add_descriptor(Descriptor("name", value="world"))
            registry.register(greeting)

        @pytest.fixture
        def greeting_fixture(dut):
            return dut.require("greeting")
        """
    )
    pytester.makepyfile(
        """
        def test_it(greeting_fixture):
            assert greeting_fixture == "hello world"
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_before_and_after_test_steps_fire(pytester):
    pytester.makeconftest(
        """
        import pytest

        EVENTS = []

        def before(ctx):
            EVENTS.append(("before", ctx.item.name))

        def after(ctx):
            EVENTS.append(("after", ctx.item.name))

        def pytest_ctf_steps(steps, config):
            steps.add("ctf_before_test", before)
            steps.add("ctf_after_test", after)

        @pytest.fixture
        def events():
            return EVENTS
        """
    )
    pytester.makepyfile(
        """
        def test_one(events):
            assert ("before", "test_one") in events

        def test_two(events):
            # after ran for the previous test before this one started.
            assert ("after", "test_one") in events
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_collect_step_sees_report(pytester):
    pytester.makeconftest(
        """
        def collect(ctx):
            ctx.artifacts.add(ctx.item.nodeid, ctx.report.outcome)

        def pytest_ctf_steps(steps, config):
            steps.add("ctf_collect", collect)
        """
    )
    pytester.makepyfile(
        """
        def test_a(ctf_kernel):
            pass

        def test_b(ctf_kernel):
            names = ctf_kernel.artifacts.names()
            assert any(n.endswith("test_a") for n in names)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_unique_point_collision_fails_session(pytester):
    pytester.makeconftest(
        """
        from ctf.steps import Policy

        def owner_a(ctx):
            return "a"

        def owner_b(ctx):
            return "b"

        def pytest_ctf_steps(steps, config):
            # A plugin-declared single-owner point; two contributors collide.
            steps.declare("ctf_boot_owner", Policy.UNIQUE)
            steps.add("ctf_boot_owner", owner_a, name="a")
            steps.add("ctf_boot_owner", owner_b, name="b")
        """
    )
    pytester.makepyfile(
        """
        def test_never_runs():
            assert True
        """
    )
    result = pytester.runpytest_subprocess()
    # UNIQUE collision is a composition error: the run stops cleanly (no
    # INTERNALERROR) with a sourced diagnostic on stderr.
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        [
            "ERROR: CTF could not assemble the test environment*",
            "*StepCollisionError*",
        ]
    )


def test_multiple_provision_verbs_all_fire(pytester):
    pytester.makeconftest(
        """
        def provision_a(ctx):
            ctx.artifacts.add("provisioned:a")

        def provision_b(ctx):
            ctx.artifacts.add("provisioned:b")

        def pytest_ctf_steps(steps, config):
            # Provisioning fans out: both independent verbs run.
            steps.add("ctf_provision", provision_a, name="a")
            steps.add("ctf_provision", provision_b, name="b")
        """
    )
    pytester.makepyfile(
        """
        def test_both(ctf_kernel):
            names = ctf_kernel.artifacts.names()
            assert "provisioned:a" in names
            assert "provisioned:b" in names
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_provision_runs_once_at_session_start(pytester):
    pytester.makeconftest(
        """
        def provision(ctx):
            ctx.artifacts.add("provisioned")

        def pytest_ctf_steps(steps, config):
            steps.add("ctf_provision", provision)
        """
    )
    pytester.makepyfile(
        """
        def test_a(ctf_kernel):
            assert ctf_kernel.artifacts.names().count("provisioned") == 1

        def test_b(ctf_kernel):
            assert ctf_kernel.artifacts.names().count("provisioned") == 1
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_session_lived_resource_shared_across_tests(pytester):
    pytester.makeconftest(
        """
        import pytest
        from ctf.contracts import provides

        LOG = []

        @provides("resource")
        def resource():
            LOG.append("up")
            yield "r"
            LOG.append("down")

        def pytest_ctf_setup(registry, config):
            registry.register(resource)

        @pytest.fixture
        def log():
            return LOG

        @pytest.fixture
        def resource_fixture(dut):
            return dut.require("resource")
        """
    )
    pytester.makepyfile(
        """
        def test_first(resource_fixture, log):
            assert resource_fixture == "r"
            assert log.count("up") == 1
            assert log.count("down") == 0

        def test_second(resource_fixture, log):
            # The kernel owns one session timeline: the resource is built once
            # and shared -- not rebuilt or torn down between tests.
            assert resource_fixture == "r"
            assert log == ["up"]
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_unresolved_contract_reported(pytester):
    pytester.makeconftest(
        """
        from ctf.contracts import provides, requires

        @provides("needs")
        @requires("missing")
        def needs(missing):
            return missing

        def pytest_ctf_setup(registry, config):
            registry.register(needs)
        """
    )
    pytester.makepyfile(
        """
        def test_it(dut):
            dut.require("needs")
        """
    )
    result = pytester.runpytest_subprocess()
    # build_manager validates the graph at sessionstart -> the run stops
    # cleanly with a sourced diagnostic (not an INTERNALERROR traceback).
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        [
            "ERROR: CTF could not assemble the test environment*",
            "*UnresolvedContractError*",
            "*hint:*",
        ]
    )


def test_failing_setup_step_is_attributed_to_plugin(pytester):
    pytester.makeconftest(
        """
        def bad_provision(ctx):
            raise ValueError("boom in plugin")

        def pytest_ctf_steps(steps, config):
            steps.add("ctf_provision", bad_provision, name="bad_provision")
        """
    )
    pytester.makepyfile(
        """
        def test_never_runs():
            assert True
        """
    )
    result = pytester.runpytest_subprocess()
    # A plugin's own step raising is the plugin's fault -> clean stop that
    # names the step and shows its traceback, NOT an "internal CTF bug".
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        [
            "ERROR: CTF could not assemble the test environment*",
            "*StepExecutionError*bad_provision*",
            "*ValueError: boom in plugin*",
        ]
    )
    assert "INTERNAL CTF ERROR" not in "\n".join(result.stderr.lines)

