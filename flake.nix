{
  description = "Discord bot to manage private static channels";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs";
    poetry2nix.url = "github:nix-community/poetry2nix";
  };

  outputs = { self, nixpkgs, flake-utils, poetry2nix }:
    {
      # Nixpkgs overlay providing the application
      overlay = nixpkgs.lib.composeManyExtensions [
        poetry2nix.overlay
        (final: prev: {
          discord-static-bot = prev.poetry2nix.mkPoetryApplication {
            projectDir = ./.;
          };
        })
      ];
    } // (flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ self.overlay ];
        };
      in
      {
        packages = {
          default = pkgs.discord-static-bot;
        };
        apps = {
          # Note that we manually need to remove setuptools from poetry.lock or this will
          # break: https://github.com/nix-community/poetry2nix/issues/648
          default = {
            type = "app";
            program = "${pkgs.discord-static-bot}/bin/discord-static-bot";
          };
        };

        devShell = pkgs.mkShell {
          packages = [ pkgs.poetry ];
        };
      }));
}
