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
          discord-static-bot = (prev.poetry2nix.mkPoetryApplication {
            projectDir = ./.;
            doCheck = false;
          });
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
          docker = pkgs.makeOverridable pkgs.dockerTools.streamLayeredImage {
            name = "discord-static-bot";
            config = {
              Env = [
                "SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
              ];
              EntryPoint = [ "${pkgs.discord-static-bot}/bin/discord-static-bot" ];
            };
          };
          docker-latest = self.packages.${system}.docker.override (_: {
            tag = "latest";
          });
          deploy =
            let
              image_name = "registry.fly.io/discord-static-bot:latest";
            in pkgs.writeShellScriptBin "deploy" ''
              ${self.packages.${system}.docker} | gzip --fast \
                | ${pkgs.skopeo}/bin/skopeo copy \
                  docker-archive:/dev/stdin \
                  docker://${image_name}

              exec ${pkgs.flyctl}/bin/flyctl deploy \
                --image ${image_name}
            '';
        };
        apps = {
          # Note that we manually need to remove setuptools from poetry.lock or this will
          # break: https://github.com/nix-community/poetry2nix/issues/648
          bot = {
            type = "app";
            program = "${pkgs.discord-static-bot}/bin/discord-static-bot";
          };
          deploy = { type = "app"; program = "${self.packages.${system}.deploy}/bin/deploy"; };
        };

        devShell = pkgs.mkShell {
          packages = with pkgs; [
            poetry
            flyctl
          ];
        };
      }));
}
