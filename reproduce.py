#!/usr/bin/env python3
"""Read-only stdio MCP reproduction; Python standard library, POSIX host."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-lsp", default="agent-lsp")
    parser.add_argument("--rust-analyzer", default="rust-analyzer")
    parser.add_argument("--expect", required=True, choices=("empty", "edits"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = root / "src/main.rs"
    before = source.read_bytes()
    messages = queue.Queue()
    process = subprocess.Popen(
        [args.agent_lsp, "rust:" + args.rust_analyzer],
        cwd=root,
        env={**os.environ, "AGENT_LSP_OUTPUT_FORMAT": "json"},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    def receive():
        try:
            for line in process.stdout:
                messages.put(json.loads(line))
        except Exception as error:
            messages.put(error)
        finally:
            messages.put(None)

    threading.Thread(target=receive, daemon=True).start()
    request_id = 0

    def request(method, params):
        nonlocal request_id
        request_id += 1
        process.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
        }) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 60
        while True:
            response = messages.get(timeout=max(0, deadline - time.monotonic()))
            if response is None:
                raise RuntimeError("MCP server exited")
            if isinstance(response, Exception):
                raise response
            if response.get("id") == request_id:
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response["result"]

    def call(name, arguments):
        for attempt in range(5):
            result = request("tools/call", {"name": name, "arguments": arguments})
            if not result.get("isError"):
                return result
            if "content modified" not in json.dumps(result) or attempt == 4:
                raise RuntimeError(result)
            time.sleep(1)

    try:
        request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "rust-code-actions-repro", "version": "1"},
        })
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        call("start_lsp", {
            "root_dir": str(root), "language_id": "rust", "ready_timeout_seconds": 30,
        })
        document = {"file_path": str(source), "language_id": "rust"}
        call("open_document", document)
        position = {**document, "line": 2, "column": 9}
        deadline = time.monotonic() + 60
        while True:
            hover = call("inspect_symbol", position)
            if "i32" in json.dumps(hover):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Hover never established semantic readiness (expected i32)")
            time.sleep(1)
        action_args = {
            **document, "start_line": 2, "start_column": 9,
            "end_line": 2, "end_column": 9,
        }
        result = call("suggest_fixes", action_args)
        # Ignore the bridge's separate next-step hint; retain the actual action JSON.
        actions = json.loads(result["content"][0]["text"])
        if args.expect == "empty":
            assert actions == [], actions
        else:
            typed = [a for a in actions if a["title"] == "Insert explicit type `i32`"]
            assert typed, actions
            edits = [e for change in typed[0]["edit"]["documentChanges"]
                     for e in change.get("edits", [])]
            assert any(e["newText"] == ": i32" for e in edits), typed
        assert source.read_bytes() == before, "Reproduction changed Rust source"
        report = {
            "expected": args.expect,
            "agent_lsp_version": subprocess.check_output(
                [args.agent_lsp, "--version"], text=True).strip(),
            "rust_analyzer_version": subprocess.check_output(
                [args.rust_analyzer, "--version"], text=True).strip(),
            "semantic_hover": hover,
            "suggest_fixes_arguments": action_args,
            "actions": actions,
            "source_sha256": hashlib.sha256(before).hexdigest(),
            "source_unchanged": True,
        }
        # Make published evidence independent of the runner's home directory.
        print(json.dumps(report, indent=2).replace(str(root), "/REPRO"))
    finally:
        process.stdin.close()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


if __name__ == "__main__":
    main()
