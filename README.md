# Rust code actions missing through agent-lsp 0.19.2

A dependency-free, four-line Rust crate reproduces empty code-action responses
from agent-lsp 0.19.2 with rust-analyzer 2026-08-03. Adding only the missing
client capability makes the same request return an explicit-type edit.

```rust
fn main() {
    let value = 1 + 2;
    std::hint::black_box(value);
}
```

## Reproduce with existing tools

Requirements: a POSIX host, Python 3, Cargo/Rust, rust-analyzer, and agent-lsp
0.19.2 on PATH. No Python or Rust dependencies are needed. The tested versions
are pinned by the optional Nix setup below.

```sh
cargo check --locked
python3 reproduce.py --expect empty
```

The script launches its own stdio MCP bridge, starts a Rust session for this
crate, opens `src/main.rs`, and waits until hover at line 2, column 9 reports
`i32`. It then calls `suggest_fixes` with:

```json
{
  "file_path": "/absolute/path/to/this/repository/src/main.rs",
  "language_id": "rust",
  "start_line": 2,
  "start_column": 9,
  "end_line": 2,
  "end_column": 9
}
```

Observed unpatched result: `[]`, despite semantic hover succeeding.
Expected useful result: an ``Insert explicit type `i32` `` action carrying the
edit that changes `let value = ...` to `let value: i32 = ...`.

The script checks the expected result and source preservation, prints JSON
evidence, and terminates only its own process group. Startup retries are bounded
and specific to empty hover or `content modified`. It never calls an edit,
rename, or execution tool and does not connect to an editor. Public tool
positions are 1-based; positions inside returned LSP edits are 0-based.

## Pinned before/after experiment with Nix

The lock pins agent-lsp to `c7ea45e5a3f1d971293a7f56337deb2afb5bbe71`
(v0.19.2) and nixpkgs to the tested Rust toolchain. Verified on x86_64 Linux.

```sh
nix develop -c cargo check --locked
nix develop -c python reproduce.py --expect empty
patched=$(nix build .#patched --no-link --print-out-paths)
nix develop -c python reproduce.py --agent-lsp "$patched/bin/agent-lsp" --expect edits
```

The first probe must return no actions. The second must return an explicit-type
action with a real `: i32` edit; an action title or unresolved data alone does
not pass. Both use the same Rust crate and rust-analyzer binary. Build outputs
are not installed globally.

Without Nix, build the pinned upstream Go source, apply
[the patch](patches/code-action-literals.patch) in a disposable checkout, rebuild,
and pass that executable with `--agent-lsp /absolute/path/to/patched/agent-lsp`.
The `--rust-analyzer` argument can select a particular analyzer executable.

## Cause and scope

Agent-lsp's initialization message advertises only `dynamicRegistration` under
`textDocument.codeAction`; it omits `codeActionLiteralSupport`.
Rust-analyzer checks that capability and returns no code actions when absent.
The patch adds the standard literal-support capability and kind value set.
It does **not** advertise lazy resolution. This analyzer supplies edits eagerly
when lazy resolution is absent, so no `codeAction/resolve` implementation is
needed for this experiment.

- [Pinned bridge initialization](https://github.com/blackwell-systems/agent-lsp/blob/c7ea45e5a3f1d971293a7f56337deb2afb5bbe71/internal/lsp/client.go#L974)
- [Pinned analyzer handler](https://github.com/rust-lang/rust-analyzer/blob/2026-08-03/crates/rust-analyzer/src/handlers/request.rs#L1507)
- [Pinned analyzer capability check](https://github.com/rust-lang/rust-analyzer/blob/2026-08-03/crates/rust-analyzer/src/lsp/capabilities.rs#L378)

[Unpatched](results/unpatched.json) and [patched](results/patched.json) outputs
record the verified runs. `/REPRO` replaces the checkout's absolute path;
document versions may vary with startup retries. This demonstrates action
discovery and edit delivery, not correctness of every returned refactoring.

Prepared with AI assistance. The commands and before/after results were run
against the pinned tools. This repository is a reproduction, not an upstream
issue or pull request.
