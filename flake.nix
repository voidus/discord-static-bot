{
  description = "A very basic flake";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }: flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShell = pkgs.mkShell {
        packages = [
          pkgs.black
        ];
        buildInputs = [
          (pkgs.python310.withPackages (ps: with ps; [
            ipython

            pytest
            discordpy
          ]))
        ];
      };
    });

}
