{
  description = "Minimal agent-lsp / rust-analyzer code-action reproduction";

  inputs = {
    nixpkgs.url = "nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
    agent-lsp-src = {
      url = "github:blackwell-systems/agent-lsp/v0.19.2";
      flake = false;
    };
  };

  outputs = { nixpkgs, flake-utils, agent-lsp-src, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        original = pkgs.buildGoModule {
          pname = "agent-lsp";
          version = "0.19.2";
          src = agent-lsp-src;
          vendorHash = "sha256-aBokNk3GGCkMX5UYotiQHzWRKfHF6Tc0EA4hIj5XIKg=";
          subPackages = [ "cmd/agent-lsp" ];
          ldflags = [ "-s" "-w" "-X main.Version=0.19.2" ];
        };
      in {
        packages.unpatched = original;
        packages.patched = original.overrideAttrs (_: {
          patches = [ ./patches/code-action-literals.patch ];
        });
        devShells.default = pkgs.mkShell {
          packages = [ original pkgs.rust-analyzer pkgs.cargo pkgs.rustc pkgs.python3 ];
          RUST_SRC_PATH = "${pkgs.rustPlatform.rustLibSrc}";
        };
      });
}
