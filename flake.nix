{
  description = "cairn-mail: Declarative AI-enhanced email workflow";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }: let
    supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
    forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
  in {
    # Overlay - adds packages to pkgs (required for modules)
    overlays.default = final: prev: {
      cairn-mail = self.packages.${final.system}.default;
      cairn-mail-web = self.packages.${final.system}.web;
    };

    # NixOS Module - manages package and web service
    # Import this AND apply the overlay in your NixOS config
    nixosModules.default = import ./modules/nixos;

    # Home-Manager Module - user config (accounts, AI settings)
    # Requires overlay to be applied for pkgs.cairn-mail
    homeManagerModules.default = import ./modules/home-manager;

    # Python package
    packages = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};

      # Build web frontend separately
      web-frontend = pkgs.buildNpmPackage {
        pname = "cairn-mail-web";
        version = "2.0.0";

        src = ./web;

        npmDepsHash = "sha256-vbCBc6YlO/qCL0G4mrnfvUYfS0vu3tQZeKJ9y2jxbRs=";

        npmBuildScript = "build";

        installPhase = ''
          mkdir -p $out
          cp -r dist/* $out/
        '';
      };
    in {
      # Export web frontend package
      web = web-frontend;

      default = pkgs.python3Packages.buildPythonApplication {
        pname = "cairn-mail";
        version = "2.0.0";

        src = ./.;

        format = "pyproject";

        nativeBuildInputs = with pkgs; [
          python3Packages.setuptools
          python3Packages.wheel
        ];

        propagatedBuildInputs = with pkgs.python3Packages; [
          # Core dependencies
          pydantic
          pydantic-settings
          sqlalchemy
          alembic

          # Email providers
          google-api-python-client
          google-auth-httplib2
          google-auth-oauthlib
          msal

          # HTTP/API
          httpx
          requests

          # CLI
          click
          typer
          rich
          python-dateutil
          pyyaml

          # MCP (Model Context Protocol)
          mcp

          # Push notifications
          pywebpush

          # Web API (Phase 2)
          fastapi
          uvicorn
          websockets
          python-multipart  # Required for file uploads (Phase 7)
        ];

        # Build frontend before building Python package
        preBuild = ''
          echo "Copying pre-built frontend..."
          # Create directory for web assets in package
          mkdir -p src/cairn_mail/web_assets
          cp -r ${web-frontend}/* src/cairn_mail/web_assets/
        '';

        # Skip tests for now (no tests written yet)
        doCheck = false;

        meta = with pkgs.lib; {
          description = "AI-enhanced email workflow with two-way sync";
          homepage = "https://github.com/kcalvelli/cairn-mail";
          license = licenses.mit;
        };
      };
    });

    # Dev Shell for working on the python agents
    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      default = pkgs.mkShell {
        packages = with pkgs; [
          python311
          python311Packages.black
          python311Packages.ruff
          python311Packages.mypy
          python311Packages.pytest
          python311Packages.pip
          python311Packages.venvShellHook

          # For testing/dev
        ];

        venvDir = "./.venv";

        postVenvCreation = ''
          unset SOURCE_DATE_EPOCH
          pip install -e .[dev]
        '';

        postShellHook = ''
          unset SOURCE_DATE_EPOCH
          echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
          echo "  cairn-mail v2.0 development environment"
          echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
          echo ""
          echo "Python virtual environment: $VIRTUAL_ENV"
          echo "Installed in editable mode with [dev] dependencies"
          echo ""
          echo "Available commands:"
          echo "  cairn-mail --help      Show CLI help"
          echo "  cairn-mail auth setup gmail"
          echo "  cairn-mail sync run"
          echo "  cairn-mail status"
          echo ""
          echo "Run tests: pytest"
          echo "Format code: black ."
          echo "Lint: ruff check ."
          echo ""
        '';
      };
    });
    
    # Apps for easy running
    apps = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      cairn-mail = self.packages.${system}.default;
    in {
      default = {
        type = "app";
        program = "${cairn-mail}/bin/cairn-mail";
      };

      # Legacy v1 scripts (kept for backward compatibility)
      auth-v1 = {
        type = "app";
        program = "${pkgs.writeShellScriptBin "auth" ''
          ${pkgs.python3}/bin/python3 ${./src/mutt_oauth2.py} "$@"
        ''}/bin/auth";
      };
    });
  };
}
