from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import agent_harness
from tests.unit.support import init_repo


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AgentHarnessRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_source_bundle_excludes_ignored_and_untracked_local_files(self):
        repo = init_repo(
            self.root / "repo",
            {
                ".gitignore": b".codex/\n",
                "tracked.txt": b"tracked\n",
            },
        )
        incident = repo / ".codex" / "incident.txt"
        incident.parent.mkdir()
        incident.write_text("local incident\n")
        (repo / "scratch.txt").write_text("untracked\n")

        bundle = agent_harness.copy_source_bundle(self.root / "runtime", repo)

        self.assertEqual((bundle / "tracked.txt").read_text(), "tracked\n")
        self.assertFalse((bundle / ".codex").exists())
        self.assertFalse((bundle / "scratch.txt").exists())

    def test_source_bundle_self_upgrade_does_not_delete_itself(self):
        runtime = self.root / "runtime"
        bundle = runtime / agent_harness.SOURCE_BUNDLE_REL
        bundle.mkdir(parents=True)
        marker = bundle / "package.json"
        marker.write_text("{}\n")
        self.assertEqual(agent_harness.copy_source_bundle(runtime, bundle), bundle)
        self.assertTrue(marker.exists())

    def test_setup_parser_defaults_to_full_toolchain_and_supports_none(self):
        parser = agent_harness.build_parser()
        self.assertEqual(parser.parse_args(["setup"]).toolchain, "full")
        self.assertEqual(
            parser.parse_args(["setup", "--toolchain", "none"]).toolchain,
            "none",
        )

    def test_toolchain_none_never_probes_or_writes(self):
        with patch.object(agent_harness, "load_toolchain_manifest") as load:
            result = agent_harness.install_toolchain(
                self.root / "runtime", PROJECT_ROOT, "none"
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        load.assert_not_called()

    def test_full_toolchain_dry_run_builds_receipt_without_writing(self):
        unavailable = {"available": False, "executables": ["missing"]}
        with (
            patch.object(agent_harness, "detect_package_manager", return_value="brew"),
            patch.object(agent_harness, "probe_executables", return_value=unavailable),
            patch.object(agent_harness, "uv_bin_dir", return_value=[]),
            patch.object(agent_harness.shutil, "which", return_value=None),
        ):
            result = agent_harness.install_toolchain(
                self.root / "runtime", PROJECT_ROOT, "full", dry_run=True
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["actions"])
        self.assertFalse((self.root / "runtime").exists())

    def test_ubuntu_dry_run_has_no_unsupported_tool(self):
        unavailable = {"available": False, "executables": ["missing"]}
        with (
            patch.object(agent_harness, "detect_package_manager", return_value="apt-get"),
            patch.object(agent_harness, "probe_executables", return_value=unavailable),
            patch.object(agent_harness, "uv_bin_dir", return_value=[]),
            patch.object(agent_harness.shutil, "which", return_value=None),
        ):
            result = agent_harness.install_toolchain(
                self.root / "runtime", PROJECT_ROOT, "full", dry_run=True
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["unsupported"], [])
        self.assertEqual(
            {action.get("tool") for action in result["actions"] if action["kind"] == "fallback"},
            {"ast-grep", "yq", "uv", "rtk"},
        )
        uv_actions = [action for action in result["actions"] if action["kind"] == "uv"]
        self.assertEqual({action["tool"] for action in uv_actions}, {"semble", "serena", "headroom"})
        for action in uv_actions:
            if action["tool"] == "serena":
                self.assertNotIn("--no-build", action["command"])
                self.assertIn("--overrides", action["command"])
            else:
                self.assertIn("--no-build", action["command"])
            self.assertIn("--no-python-downloads", action["command"])
            self.assertIn("--no-config", action["command"])
            self.assertIn("--exclude-newer", action["command"])

    def test_linux_package_install_fails_before_mutation_without_privilege(self):
        unavailable = {"available": False, "executables": ["missing"]}
        denied = subprocess.CompletedProcess([], 1, "", "password required")
        with (
            patch.object(agent_harness, "detect_package_manager", return_value="apt-get"),
            patch.object(agent_harness, "probe_executables", return_value=unavailable),
            patch.object(agent_harness.os, "geteuid", return_value=1000),
            patch.object(agent_harness.shutil, "which", side_effect=lambda name: "/usr/bin/sudo" if name == "sudo" else None),
            patch.object(agent_harness, "run_text", return_value=denied) as run,
        ):
            with self.assertRaisesRegex(agent_harness.HarnessError, "sudo -v"):
                agent_harness.install_toolchain(
                    self.root / "runtime", PROJECT_ROOT, "full"
                )
        run.assert_called_once_with(["sudo", "-n", "true"], timeout=15)

    def test_npm_bundle_install_scrubs_credentials_and_disables_scripts(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        (bundle / "package-lock.json").write_text("{}\n")
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.dict(os.environ, {"HOME": str(self.root), "PATH": "/bin", "NPM_TOKEN": "not-forwarded"}, clear=True),
            patch.object(agent_harness, "command_available", return_value=True),
            patch.object(agent_harness, "run_text", return_value=completed) as run,
        ):
            result = agent_harness.npm_ci_for_bundle(bundle)
        self.assertTrue(result["ok"])
        self.assertEqual(run.call_args.args[0], ["npm", "ci", "--omit=dev", "--ignore-scripts"])
        self.assertNotIn("NPM_TOKEN", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["npm_config_ignore_scripts"], "true")
        self.assertEqual(run.call_args.kwargs["env"]["npm_config_userconfig"], os.devnull)
        self.assertTrue(run.call_args.kwargs["env"]["npm_config_globalconfig"].endswith("/empty-global.npmrc"))

    def test_playwright_dependency_lock_integrity_is_enforced(self):
        lock = agent_harness.load_json(
            PROJECT_ROOT / "runtime" / "lazy-playwright" / "package-lock.json", {}
        )
        agent_harness.validate_playwright_lock(lock)
        tampered = json.loads(json.dumps(lock))
        del tampered["packages"]["node_modules/playwright-core"]["integrity"]
        with self.assertRaisesRegex(agent_harness.HarnessError, "lacks SHA-512"):
            agent_harness.validate_playwright_lock(tampered)
        manifest = agent_harness.load_toolchain_manifest(PROJECT_ROOT)
        playwright = next(item for item in manifest["lazy_mcp"] if item["id"] == "playwright")
        self.assertEqual(playwright["args"], ["playwright", "--"])
        self.assertEqual(playwright["lock"], "runtime/lazy-playwright/package-lock.json")

    def test_package_client_environment_drops_registry_credentials(self):
        with patch.dict(
            os.environ,
            {
                "HOME": str(self.root),
                "PATH": "/bin",
                "NPM_TOKEN": "secret",
                "UV_INDEX_URL": "https://credential@example.invalid/simple",
                "PIP_INDEX_URL": "https://credential@example.invalid/simple",
            },
            clear=True,
        ):
            env = agent_harness.package_client_env(UV_NO_CONFIG="1")
        self.assertEqual(env, {"HOME": str(self.root), "PATH": "/bin", "UV_NO_CONFIG": "1"})

    def test_package_fallback_disables_npm_scripts_and_scrubs_environment(self):
        tool = next(
            item
            for item in agent_harness.load_toolchain_manifest(PROJECT_ROOT)["system_tools"]
            if item["id"] == "ast-grep"
        )
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.dict(os.environ, {"HOME": str(self.root), "PATH": "/bin", "NPM_TOKEN": "secret"}, clear=True),
            patch.object(agent_harness.shutil, "which", return_value="/bin/npm"),
            patch.object(agent_harness, "run_text", return_value=completed) as run,
        ):
            result = agent_harness.install_tool_fallback(tool, dry_run=False)
        self.assertEqual(result["returncode"], 0)
        self.assertIn("--ignore-scripts", run.call_args.args[0])
        self.assertNotIn("NPM_TOKEN", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["npm_config_ignore_scripts"], "true")

    def test_fallback_asset_selection_covers_supported_architectures(self):
        tool = next(
            item
            for item in agent_harness.load_toolchain_manifest(PROJECT_ROOT)["system_tools"]
            if item["id"] == "yq"
        )
        cases = {
            ("darwin", "arm64"): "yq_darwin_arm64",
            ("darwin", "x86_64"): "yq_darwin_amd64",
            ("linux", "aarch64"): "yq_linux_arm64",
            ("linux", "amd64"): "yq_linux_amd64",
        }
        for (system, machine), asset_name in cases.items():
            with self.subTest(system=system, machine=machine), patch.object(
                agent_harness.sys, "platform", system
            ), patch.object(agent_harness.platform, "machine", return_value=machine):
                result = agent_harness.install_tool_fallback(tool, dry_run=True)
            self.assertEqual(result["returncode"], None)
            self.assertTrue(result["command"][1].endswith(asset_name))

    def test_owned_tool_removal_requires_exact_download_hash(self):
        runtime = self.root / "runtime"
        binary = self.root / "bin" / "yq"
        binary.parent.mkdir()
        binary.write_bytes(b"installed")
        receipt_path = runtime / "state" / "adapters" / "toolchain-receipt.json"
        receipt = {
            "owned": ["yq", "git"],
            "actions": [{
                "kind": "fallback",
                "tool": "yq",
                "returncode": 0,
                "path": str(binary),
                "installed_sha256": hashlib.sha256(b"installed").hexdigest(),
            }],
        }
        agent_harness.write_json(receipt_path, receipt)
        binary.write_bytes(b"user-changed")

        result = agent_harness.remove_owned_tools(runtime, PROJECT_ROOT)

        self.assertFalse(result["ok"])
        self.assertTrue(binary.exists())
        self.assertEqual(result["removed"], [])
        self.assertEqual([item["tool"] for item in result["retained"]], ["git"])

    def test_toolchain_mcp_specs_use_receipt_paths_and_no_credentials(self):
        runtime = self.root / "runtime"
        agent_harness.write_json(
            runtime / "state" / "adapters" / "toolchain-receipt.json",
            {
                "profile": "full",
                "tools": {
                    "semble": {"path": "/portable/bin/semble"},
                    "serena": {"path": "/portable/bin/serena"},
                    "headroom": {"path": "/portable/bin/headroom"},
                },
            },
        )
        specs = agent_harness.toolchain_mcp_specs(runtime, "codex")
        self.assertEqual([item["name"] for item in specs], [
            "agent-harness-semble",
            "agent-harness-serena",
            "agent-harness-headroom",
            "agent-harness-context7",
        ])
        self.assertIn("--context=codex", specs[1]["args"])
        self.assertNotIn("env", json.dumps(specs).lower())

    def test_adapter_failure_propagates_to_setup_status(self):
        self.assertFalse(agent_harness.adapters_ok({"claude": {"status": "failed"}}))
        self.assertFalse(agent_harness.adapters_ok({"cursor": {"status": "partial"}}))
        self.assertTrue(agent_harness.adapters_ok({"claude": {"status": "skipped"}}))

    def test_claude_mcp_name_precedes_environment_flags(self):
        runtime = self.root / "runtime"
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(agent_harness.Path, "home", return_value=self.root),
            patch.object(agent_harness, "command_available", return_value=True),
            patch.object(agent_harness, "run_text", return_value=completed) as run,
        ):
            result = agent_harness.install_claude_adapters(
                runtime,
                {"workspace": "test", "mcp": {"name": "test-agent-harness"}},
                None,
            )
        command = next(
            call.args[0]
            for call in run.call_args_list
            if call.args[0][:3] == ["claude", "mcp", "add"]
        )
        self.assertLess(command.index("test-agent-harness"), command.index("--env"))
        self.assertTrue(result["mcp"]["ok"])

    def test_sensitive_scan_distinguishes_broker_reference_from_secret(self):
        broker = self.root / "authority" / "macos-broker.swift"
        broker.parent.mkdir()
        broker.write_text(
            "if let authorization = session.controllerAuthorization {\n"
        )
        authority_leak = self.root / "authority" / "leak.swift"
        authority_leak.write_text('let authorization = "' + "B" * 32 + '"\n')
        state = self.root / "state" / "leak.txt"
        state.parent.mkdir()
        state.write_text("authorization = " + "A" * 32 + "\n")

        failures = agent_harness.scan_tree_for_sensitive_material(self.root)

        self.assertCountEqual(
            failures,
            [
                f"possible sensitive material: {authority_leak}",
                f"possible sensitive material: {state}",
            ],
        )

    def test_run_check_does_not_leak_runtime_selection_to_child(self):
        runtime = self.root / "runtime"
        repo = self.root / "repo"
        repo.mkdir()
        agent_harness.ensure_runtime_dirs(runtime)
        agent_harness.write_json(
            runtime / "config.json", {"workspace": "test", "repos": {}}
        )
        task = agent_harness.task_dir(runtime, "env-check")
        task.mkdir()
        agent_harness.write_json(
            task / "task.json", {"repo_path": str(repo), "worktree": ""}
        )
        args = argparse.Namespace(
            runtime_root=str(runtime),
            task_id="env-check",
            command=[
                sys.executable,
                "-c",
                "import os,sys; sys.exit(7 if 'AGENT_HARNESS_ROOT' in os.environ else 0)",
            ],
            timeout=30,
            json=True,
        )

        with patch.dict(
            os.environ, {"AGENT_HARNESS_ROOT": "/unexpected/parent/runtime"}
        ):
            result = agent_harness.run_check(args)

        self.assertEqual(result, 0)
        self.assertTrue(agent_harness.load_checks(runtime, "env-check")[-1]["passed"])

    def test_agent_capabilities_accepts_json_for_cli_consistency(self):
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "bin" / "agent-harness"),
                "agent",
                "capabilities",
                "--json",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_codex_route_policy_is_role_risk_and_attempt_aware(self):
        cases = [
            ("planner", "auto", 0, "gpt-5.6-sol", "max", "planner"),
            ("researcher", "auto", 0, "gpt-5.6-luna", "max", "routine"),
            ("worker", "yellow", 0, "gpt-5.6-luna", "max", "routine"),
            ("qa", "green", 0, "gpt-5.6-luna", "max", "routine"),
            ("synthesizer", "medium", 0, "gpt-5.6-luna", "max", "routine"),
            ("reviewer", "green", 0, "gpt-5.6-terra", "high", "review"),
            ("security", "yellow", 0, "gpt-5.6-terra", "max", "security"),
            ("worker", "red", 0, "gpt-5.6-sol", "max", "high-risk"),
            ("reviewer", "critical", 0, "gpt-5.6-sol", "max", "high-risk"),
            ("worker", "green", 1, "gpt-5.6-sol", "max", "retry-escalation"),
        ]
        for role, risk, prior_attempts, model, effort, reason in cases:
            with self.subTest(role=role, risk=risk, prior_attempts=prior_attempts):
                route = agent_harness.resolve_codex_route(
                    role, risk, prior_attempts=prior_attempts
                )
                self.assertEqual(route["model"], model)
                self.assertEqual(route["reasoning_effort"], effort)
                self.assertEqual(route["reason"], reason)
                self.assertEqual(route["attempt"], prior_attempts + 1)
                self.assertEqual(route["speed"], "standard")

        override = agent_harness.resolve_codex_route(
            "worker",
            "critical",
            model="gpt-5.6-luna",
            reasoning_effort="high",
            fast=True,
        )
        self.assertEqual(
            (override["model"], override["reasoning_effort"], override["speed"]),
            ("gpt-5.6-luna", "high", "fast"),
        )
        self.assertEqual(override["reason"], "explicit-override")
        fast_args = agent_harness.codex_exec_args(
            Path("final.md"), "fast probe", override
        )
        self.assertIn("features.fast_mode=true", fast_args)
        self.assertIn('service_tier="fast"', fast_args)

        with self.assertRaises(agent_harness.HarnessError):
            agent_harness.resolve_codex_route("worker", "green", model="unknown")
        with self.assertRaises(agent_harness.HarnessError):
            agent_harness.resolve_codex_route(
                "worker", "green", reasoning_effort="ultra"
            )

    def test_agent_run_dry_run_records_codex_route_only_for_codex(self):
        runtime = self.root / "runtime"
        agent_harness.ensure_runtime_dirs(runtime)
        task = agent_harness.task_dir(runtime, "route-probe")
        task.mkdir()
        agent_harness.write_json(
            task / "task.json", {"risk": "green", "repo_path": str(self.root)}
        )

        base = {
            "runtime_root": str(runtime),
            "task_id": "route-probe",
            "role": "worker",
            "prompt": "route probe",
            "dry_run": True,
            "timeout": 30,
            "json": True,
            "codex_model": None,
            "codex_effort": None,
            "codex_fast": False,
        }
        with patch.object(agent_harness, "print_json"):
            self.assertEqual(
                agent_harness.agent_run(
                    argparse.Namespace(
                        **base, agent="codex", run_id="codex-route-probe"
                    )
                ),
                0,
            )
            self.assertEqual(
                agent_harness.agent_run(
                    argparse.Namespace(
                        **base, agent="claude", run_id="claude-route-probe"
                    )
                ),
                0,
            )

        codex_meta = agent_harness.load_json(
            task / "agent-runs" / "codex-route-probe" / "metadata.json", {}
        )
        self.assertEqual(codex_meta["route"]["model"], "gpt-5.6-luna")
        self.assertIn("--model", codex_meta["command"])
        self.assertIn(
            "model_reasoning_effort=\"max\"", codex_meta["command"]
        )
        self.assertIn("features.fast_mode=false", codex_meta["command"])

        claude_meta = agent_harness.load_json(
            task / "agent-runs" / "claude-route-probe" / "metadata.json", {}
        )
        self.assertNotIn("route", claude_meta)
        self.assertNotIn("--model", claude_meta["command"])

    def test_agent_run_executes_in_the_task_worktree(self):
        runtime = self.root / "runtime"
        worktree = self.root / "task-worktree"
        worktree.mkdir()
        agent_harness.ensure_runtime_dirs(runtime)
        task = agent_harness.task_dir(runtime, "cwd-probe")
        task.mkdir()
        agent_harness.write_json(
            task / "task.json",
            {
                "risk": "green",
                "repo_path": str(self.root / "repo"),
                "worktree": str(worktree),
            },
        )
        args = argparse.Namespace(
            runtime_root=str(runtime),
            task_id="cwd-probe",
            agent="codex",
            role="researcher",
            run_id="cwd-probe",
            prompt="cwd probe",
            timeout=30,
            dry_run=False,
            json=True,
            codex_model=None,
            codex_effort=None,
            codex_fast=False,
        )
        completed = subprocess.CompletedProcess([], 0, "cwd ok\n", "")
        with (
            patch.object(agent_harness, "run_text", return_value=completed) as run,
            patch.object(agent_harness, "print_json"),
        ):
            self.assertEqual(agent_harness.agent_run(args), 0)
        self.assertEqual(run.call_args.kwargs["cwd"], worktree.resolve())

    def test_task_execution_cwd_ignores_empty_or_missing_worktree(self):
        repo = self.root / "repo"
        worktree = self.root / "worktree"
        repo.mkdir()
        worktree.mkdir()

        self.assertEqual(
            agent_harness.task_execution_cwd(
                {"repo_path": str(repo), "worktree": str(worktree)}
            ),
            worktree.resolve(),
        )
        for manifest in (
            {"repo_path": str(repo), "worktree": ""},
            {"repo_path": str(repo)},
        ):
            with self.subTest(manifest=manifest):
                self.assertEqual(
                    agent_harness.task_execution_cwd(manifest), repo.resolve()
                )

    def test_cursor_cli_restore_preserves_preexisting_empty_deny_list(self):
        runtime = self.root / "runtime"
        cli_config = self.root / ".cursor" / "cli-config.json"
        original = {"permissions": {"deny": []}, "unrelated": {"keep": True}}
        agent_harness.write_json(cli_config, original)

        agent_harness.merge_cursor_cli_permissions(runtime, cli_config)
        agent_harness.restore_cursor_cli_permissions(runtime)

        self.assertEqual(json.loads(cli_config.read_text()), original)

    def test_cursor_cli_restore_retains_rule_ownership_across_reinstall(self):
        runtime = self.root / "runtime"
        cli_config = self.root / ".cursor" / "cli-config.json"
        original = {
            "permissions": {"deny": ["Read(existing-rule)"]},
            "unrelated": {"keep": True},
        }
        agent_harness.write_json(cli_config, original)

        agent_harness.merge_cursor_cli_permissions(runtime, cli_config)
        agent_harness.merge_cursor_cli_permissions(runtime, cli_config)
        agent_harness.restore_cursor_cli_permissions(runtime)

        self.assertEqual(json.loads(cli_config.read_text()), original)

    def test_cursor_adapter_does_not_modify_cli_config(self):
        runtime = self.root / "runtime"
        cursor_home = self.root / ".cursor"
        cli_config = cursor_home / "cli-config.json"
        original = '{"permissions":{"allow":["Shell(ls)"],"deny":[]}}\n'
        cursor_home.mkdir()
        cli_config.write_text(original)

        with patch.object(agent_harness.Path, "home", return_value=self.root):
            result = agent_harness.install_cursor_adapters(
                runtime,
                {"workspace": "test", "mcp": {"name": "test-agent-harness"}},
                None,
                force=True,
            )

        self.assertEqual(cli_config.read_text(), original)
        self.assertEqual(result["cli_permissions"]["status"], "skipped")
        rule = cursor_home / "rules" / "agent-harness.mdc"
        self.assertTrue(rule.read_text().startswith("---\n"))
        self.assertEqual(result["user_rule"]["path"], str(rule))

    def test_cursor_hooks_migrate_to_single_pre_tool_policy_entry(self):
        runtime = self.root / "runtime"
        hooks_path = self.root / ".cursor" / "hooks.json"
        bridge = agent_harness.cursor_bridge_command(runtime)
        original_entry = {"command": "rtk hook cursor", "matcher": "Shell"}
        agent_harness.write_json(
            hooks_path,
            {
                "version": 1,
                "hooks": {
                    "preToolUse": [original_entry],
                    "beforeShellExecution": [{"command": bridge}],
                    "beforeMCPExecution": [{"command": bridge}],
                },
            },
        )

        result = agent_harness.merge_cursor_hooks(runtime, hooks_path)
        hooks = json.loads(hooks_path.read_text())["hooks"]
        harness_entries = [
            (event, entry)
            for event, entries in hooks.items()
            for entry in entries
            if "cursor-bridge.py" in entry.get("command", "")
        ]

        self.assertEqual(result["events"], ["preToolUse"])
        self.assertEqual(hooks["preToolUse"][0], original_entry)
        self.assertEqual(harness_entries, [("preToolUse", {"command": bridge})])
        self.assertNotIn("beforeShellExecution", hooks)
        self.assertNotIn("beforeMCPExecution", hooks)

        agent_harness.restore_cursor_hooks(runtime)
        self.assertEqual(
            json.loads(hooks_path.read_text()),
            {"version": 1, "hooks": {"preToolUse": [original_entry]}},
        )


if __name__ == "__main__":
    unittest.main()
