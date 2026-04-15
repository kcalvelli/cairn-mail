#!/usr/bin/env python3
import os
import sys
import getpass
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Securely store email password for Cairn AI Mail.")
    parser.add_argument("name", help="Name of the account (e.g. 'work', 'fastmail')")
    args = parser.parse_args()

    account_name = args.name

    print(f"--- Secure Password Storage for Account: {account_name} ---")
    print("This will store your password in a file with 600 permissions.")
    
    password = getpass.getpass("Enter Password: ")
    if not password:
        print("Password cannot be empty.")
        sys.exit(1)

    # Use XDG config home or default
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    secrets_dir = Path(xdg_config) / "cairn-mail" / "secrets"
    
    try:
        secrets_dir.mkdir(parents=True, exist_ok=True)
        # Ensure directory is secure-ish
        secrets_dir.chmod(0o700)
    except Exception as e:
        print(f"Error creating directory {secrets_dir}: {e}")
        sys.exit(1)

    secret_file = secrets_dir / f"{account_name}_pass"
    
    try:
        # Write file with explicit 600 mode
        # We open with O_CREAT | O_WRONLY and mode 0600
        fd = os.open(str(secret_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(password)
        
        print(f"\n[+] Password saved to: {secret_file}")
        print("[+] Permissions set to 600 (Read/Write by owner only)")
        
        print("\n=== Configuration to add to home.nix ===")
        print(f'passwordCommand = "cat {secret_file}";')
        print("========================================\n")

    except Exception as e:
        print(f"Error writing password file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
