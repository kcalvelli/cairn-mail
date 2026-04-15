"""OAuth2 and IMAP authentication setup commands."""

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import parse_qs, urlparse, quote

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

console = Console()
auth_app = typer.Typer(help="Authentication setup for email accounts")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth2 callback."""

    auth_code: Optional[str] = None

    def do_GET(self) -> None:
        """Handle GET request from OAuth2 redirect."""
        query_components = parse_qs(urlparse(self.path).query)

        if "code" in query_components:
            OAuthCallbackHandler.auth_code = query_components["code"][0]

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            success_html = """
            <html>
            <head><title>Authentication Successful</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: green;">✓ Authentication Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Suppress HTTP server logs."""
        pass


@auth_app.command("setup")
def setup_account(
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Account name from config.yaml"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address (for custom setup)"),
) -> None:
    """Interactive account setup wizard.

    Reads accounts from Nix-generated config.yaml and sets up credentials.
    Can also set up custom accounts not in config.
    """
    from ..config.loader import ConfigLoader

    console.print(
        Panel.fit(
            "[bold blue]cairn-mail Account Setup[/bold blue]\n\n"
            "This wizard will help you configure authentication for your email accounts.",
            border_style="blue",
        )
    )

    # Load config
    config = ConfigLoader.load_config()
    accounts = config.get("accounts", {})

    if not account and not email:
        if not accounts:
            console.print("\n[yellow]No accounts found in config.yaml[/yellow]")
            console.print("You can:")
            console.print("  1. Add accounts to your Nix configuration and run 'home-manager switch'")
            console.print("  2. Use --email to set up a custom account")
            raise typer.Exit(1)

        # Show available accounts
        table = Table(title="Available Accounts", show_header=True, header_style="bold magenta")
        table.add_column("Account ID", style="cyan")
        table.add_column("Provider", style="green")
        table.add_column("Email", style="yellow")
        table.add_column("Status", style="dim")

        for account_id, account_config in accounts.items():
            provider = account_config.get("provider", "unknown")
            email_addr = account_config.get("email", "unknown")
            cred_file = Path(account_config.get("credential_file", ""))
            status = "✓ Configured" if cred_file.exists() else "⚠ Needs setup"
            table.add_row(account_id, provider, email_addr, status)

        console.print("\n")
        console.print(table)
        console.print("\n")

        # Prompt for account selection
        account = Prompt.ask(
            "[bold]Select account ID to configure[/bold]",
            choices=list(accounts.keys()) + ["custom"],
            default=list(accounts.keys())[0] if accounts else "custom"
        )

    if account == "custom" or email:
        # Custom account setup
        setup_custom_account(email)
    else:
        # Setup from config
        if account not in accounts:
            console.print(f"[red]Account '{account}' not found in config.yaml[/red]")
            raise typer.Exit(1)

        account_config = accounts[account]
        setup_from_config(account, account_config)


def setup_custom_account(email: Optional[str] = None) -> None:
    """Set up a custom account not in config.yaml."""
    console.print("\n[bold]Custom Account Setup[/bold]")
    console.print("[dim]This will create a standalone configuration.[/dim]\n")

    if not email:
        email = Prompt.ask("Email address")

    provider = Prompt.ask(
        "Provider type",
        choices=["gmail", "imap", "outlook"],
        default="imap"
    )

    if provider == "gmail":
        setup_gmail_oauth(email)
    elif provider == "imap":
        setup_imap_account(email, custom=True)
    elif provider == "outlook":
        console.print("[red]Outlook setup not yet implemented[/red]")
        raise typer.Exit(1)


def setup_from_config(account_id: str, account_config: Dict[str, Any]) -> None:
    """Set up authentication for an account from config.yaml."""
    provider = account_config.get("provider")
    email = account_config.get("email")
    settings = account_config.get("settings", {})

    console.print(f"\n[bold]Setting up account: {account_id}[/bold]")
    console.print(f"Provider: [cyan]{provider}[/cyan]")
    console.print(f"Email: [yellow]{email}[/yellow]\n")

    if provider == "gmail":
        setup_gmail_oauth(email, account_id)
    elif provider == "imap":
        # Extract IMAP/SMTP settings from config
        imap_host = settings.get("imap_host")
        imap_port = settings.get("imap_port", 993)
        imap_tls = settings.get("imap_tls", True)
        smtp_host = settings.get("smtp_host")
        smtp_port = settings.get("smtp_port", 465)
        smtp_tls = settings.get("smtp_tls", True)

        setup_imap_account(
            email,
            account_id=account_id,
            imap_host=imap_host,
            imap_port=imap_port,
            imap_tls=imap_tls,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_tls=smtp_tls,
            custom=False
        )
    elif provider == "outlook":
        console.print("[red]Outlook setup not yet implemented[/red]")
        raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)


@auth_app.command("setup-gmail")
def setup_gmail_command(
    email: str = typer.Option(..., "--email", "-e", help="Gmail address"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file for OAuth token (default: stdout)"
    ),
) -> None:
    """Set up Gmail OAuth2 authentication (legacy command).

    Use 'cairn-mail auth gmail' for the recommended workflow.
    """
    setup_gmail_oauth_legacy(email, output)


@auth_app.command("gmail")
def gmail_auth_command(
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Account name for this Gmail"),
    credentials: Optional[Path] = typer.Argument(None, help="Path to credentials.json (auto-detects from ~/Downloads if not provided)"),
) -> None:
    """Set up Gmail OAuth2 with streamlined wizard.

    This wizard guides you through creating Google OAuth credentials
    and sets everything up automatically.

    Example:
        cairn-mail auth gmail --account work
    """
    from google_auth_oauthlib.flow import InstalledAppFlow
    import glob
    import stat

    # Full Gmail access (required for permanent delete)
    SCOPES = [
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]

    # Use port 9004 to avoid conflict with web UI on 8080
    OAUTH_PORT = 9004

    console.print(Panel.fit(
        "[bold blue]Gmail OAuth2 Setup Wizard[/bold blue]\n\n"
        "This wizard will guide you through setting up Gmail API access.\n"
        "You'll need to create OAuth credentials in Google Cloud Console.",
        border_style="blue",
    ))

    # Prompt for account name if not provided
    if not account:
        console.print("\n[bold]Account Setup[/bold]\n")
        console.print("Enter a short name for this Gmail account (e.g., 'personal', 'work').")
        console.print("[dim]This name will be used consistently for:[/dim]")
        console.print("[dim]  • Your Nix config: programs.cairn-mail.accounts.[cyan]<name>[/cyan][/dim]")
        console.print("[dim]  • Your secret file: gmail-[cyan]<name>[/cyan].age[/dim]")
        console.print("[dim]  • The decrypted path: /run/agenix/gmail-[cyan]<name>[/cyan][/dim]\n")
        account = Prompt.ask("Account name").strip().lower().replace(" ", "-")
        if not account:
            console.print("[red]Account name is required[/red]")
            raise typer.Exit(1)

    # Show what will be created
    console.print(f"\n[green]✓ Account name: [bold]{account}[/bold][/green]")
    console.print(f"[dim]  • Config key: programs.cairn-mail.accounts.{account}[/dim]")
    console.print(f"[dim]  • Secret file: gmail-{account}.age[/dim]")
    console.print(f"[dim]  • Runtime path: /run/agenix/gmail-{account}[/dim]")

    # Step 1: Check if credentials file provided or auto-detect
    if credentials and credentials.exists():
        console.print(f"\n[green]✓ Using provided credentials: {credentials}[/green]")
    else:
        # Show instructions and open browser
        console.print("\n[bold]Step 1: Create OAuth Credentials[/bold]\n")
        console.print("Opening Google Cloud Console in your browser...\n")

        console.print(Panel(
            "[bold]In Google Cloud Console:[/bold]\n\n"
            "1. Create a new project (or select existing)\n"
            "   • Click 'Select a project' → 'New Project'\n"
            "   • Name: [cyan]cairn-mail[/cyan] → Create\n\n"
            "2. Enable Gmail API\n"
            "   • Search for [cyan]Gmail API[/cyan] → Enable\n\n"
            "3. Configure OAuth consent screen\n"
            "   • Go to 'OAuth consent screen'\n"
            "   • Choose 'External' → Create\n"
            "   • Fill in App name, email → Save\n"
            "   • [bold yellow]Click 'Publish App'[/bold yellow] (otherwise tokens expire in 7 days!)\n"
            "   • No verification needed for personal use (<100 users)\n\n"
            "4. Create OAuth credentials\n"
            "   • Go to 'Credentials' → 'Create Credentials'\n"
            "   • Choose 'OAuth client ID'\n"
            "   • Application type: [cyan]Desktop app[/cyan]\n"
            "   • Name: [cyan]cairn-mail[/cyan]\n"
            "   • Click 'Create'\n\n"
            "5. Download the JSON file\n"
            "   • Click the download icon (⬇)\n"
            "   • Save to [cyan]~/Downloads[/cyan]",
            title="Instructions",
            border_style="yellow",
        ))

        # Open browser to credentials page
        webbrowser.open("https://console.cloud.google.com/apis/credentials")

        console.print("\n[yellow]Press Enter when you've downloaded the JSON file to ~/Downloads...[/yellow]")
        input()

        # Auto-detect credentials file in ~/Downloads
        downloads_dir = Path.home() / "Downloads"
        patterns = [
            "client_secret_*.json",
            "credentials*.json",
            "*oauth*.json",
        ]

        found_files = []
        for pattern in patterns:
            found_files.extend(glob.glob(str(downloads_dir / pattern)))

        if not found_files:
            console.print("[red]No credentials file found in ~/Downloads[/red]")
            console.print("\nLooking for files matching:")
            for pattern in patterns:
                console.print(f"  • {downloads_dir / pattern}")
            console.print("\n[yellow]You can also specify the path directly:[/yellow]")
            console.print(f"  cairn-mail auth gmail /path/to/credentials.json")
            raise typer.Exit(1)

        # Use the most recently modified file
        found_files.sort(key=lambda f: Path(f).stat().st_mtime, reverse=True)
        credentials = Path(found_files[0])

        console.print(f"\n[green]✓ Found credentials: {credentials.name}[/green]")

    # Step 2: Run OAuth flow
    console.print("\n[bold]Step 2: Authorize Application[/bold]\n")
    console.print("Opening browser for Google authorization...")
    console.print(f"[dim](Using port {OAUTH_PORT} for callback)[/dim]\n")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials), SCOPES)
        creds = flow.run_local_server(port=OAUTH_PORT, prompt="consent")

        # Get user's email from the credentials
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        user_email = profile.get("emailAddress", "unknown@gmail.com")

        console.print(f"\n[green]✓ Authorized as: {user_email}[/green]")

    except Exception as e:
        console.print(f"\n[red]Authorization failed: {e}[/red]")
        raise typer.Exit(1)

    # Step 3: Save token
    console.print("\n[bold]Step 3: Saving Credentials[/bold]\n")

    # Build token data
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    # Save to credentials directory
    cred_dir = Path.home() / ".local" / "share" / "cairn-mail" / "credentials"
    cred_dir.mkdir(parents=True, exist_ok=True)

    token_file = cred_dir / f"{account}.json"
    with open(token_file, "w") as f:
        json.dump(token_data, f, indent=2)
    token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600

    console.print(f"[green]✓ Token saved to: {token_file}[/green]")

    # Step 4: Generate agenix configuration
    console.print("\n[bold]Step 4: Agenix Setup[/bold]\n")

    # Cairn users store secrets in ~/.config/nixos_config/secrets
    secrets_dir = Path.home() / ".config" / "nixos_config" / "secrets"

    console.print(Panel(
        f"[bold]Step 4a: Add secret to secrets.nix[/bold]\n\n"
        f"Edit [cyan]~/.config/nixos_config/secrets/secrets.nix[/cyan] and add:\n\n"
        f'[cyan]"gmail-{account}.age".publicKeys = users ++ systems;[/cyan]',
        title="1. Define Secret",
        border_style="yellow",
    ))

    console.print(Panel(
        f"[bold]Step 4b: Encrypt the token[/bold]\n\n"
        f"[cyan]cd ~/.config/nixos_config/secrets[/cyan]\n"
        f"[cyan]agenix -e gmail-{account}.age < {token_file}[/cyan]\n\n"
        f"[bold]Step 4c: Stage the secret for git (required for flakes)[/bold]\n\n"
        f"[cyan]cd ~/.config/nixos_config[/cyan]\n"
        f"[cyan]git add secrets/gmail-{account}.age[/cyan]",
        title="2. Encrypt & Stage",
        border_style="yellow",
    ))

    # Generate Nix config snippet
    nix_config = f'''# Add to your home.nix:
age.secrets.gmail-{account}.file = ../secrets/gmail-{account}.age;

programs.cairn-mail.accounts.{account} = {{
  provider = "gmail";
  email = "{user_email}";
  oauthTokenFile = config.age.secrets.gmail-{account}.path;
}};'''

    console.print(Panel(
        f"[bold]Step 4d: Add to your Nix configuration:[/bold]\n\n"
        f"[cyan]{nix_config}[/cyan]",
        title="3. Nix Configuration",
        border_style="green",
    ))

    console.print(Panel.fit(
        "[bold green]✓ Gmail Setup Complete![/bold green]\n\n"
        f"Email: [cyan]{user_email}[/cyan]\n"
        f"Account: [cyan]{account}[/cyan]\n"
        f"Token: [cyan]{token_file}[/cyan]\n\n"
        "Next steps:\n"
        "1. Encrypt the token with agenix (see above)\n"
        "2. Add the Nix configuration snippet\n"
        "3. Rebuild: [cyan]home-manager switch[/cyan] or [cyan]nixos-rebuild switch[/cyan]\n"
        f"4. Delete the plaintext token: [cyan]rm {token_file}[/cyan]",
        border_style="green",
    ))


def setup_gmail_oauth(email: str, account_id: Optional[str] = None) -> None:
    """Set up Gmail OAuth2.

    Args:
        email: Email address for the account
        account_id: Optional account ID from config
    """
    port = 8080
    output = None  # Will be determined based on account_id
    console.print(
        Panel.fit(
            "[bold blue]Gmail OAuth2 Setup[/bold blue]\n\n"
            "This wizard will guide you through setting up Gmail API access.",
            border_style="blue",
        )
    )

    # Step 1: Instructions for Google Cloud Console
    console.print("\n[bold]Step 1: Create OAuth Credentials in Google Cloud Console[/bold]")
    console.print("\n1. Go to: https://console.cloud.google.com/apis/credentials")
    console.print("2. Create a new project or select existing project")
    console.print("3. Enable the Gmail API: https://console.cloud.google.com/apis/library/gmail.googleapis.com")
    console.print("4. Configure OAuth consent screen → [bold yellow]Publish App[/bold yellow]")
    console.print("   (Otherwise refresh tokens expire in 7 days!)")
    console.print("5. Create OAuth 2.0 Client ID:")
    console.print("   - Application type: Desktop app")
    console.print("   - Name: cairn-mail")
    console.print("6. Download the credentials JSON file")
    console.print("\n[yellow]Press Enter when ready to continue...[/yellow]")
    input()

    # Step 2: Get client credentials
    console.print("\n[bold]Step 2: Enter OAuth Credentials[/bold]")

    client_id = Prompt.ask("Client ID")
    client_secret = Prompt.ask("Client Secret", password=True)

    if not client_id or not client_secret:
        console.print("[red]Client ID and Secret are required[/red]")
        raise typer.Exit(1)

    # Step 3: OAuth flow
    console.print("\n[bold]Step 3: Authorize Application[/bold]")
    console.print(f"Opening browser for authorization (callback on port {port})...")

    redirect_uri = f"http://localhost:{port}"
    # All scopes needed for full Gmail functionality (read, modify, send)
    scopes = (
        "https://www.googleapis.com/auth/gmail.modify "
        "https://www.googleapis.com/auth/gmail.send "
        "https://www.googleapis.com/auth/gmail.readonly"
    )

    console.print(f"\n[yellow]IMPORTANT: In Google Cloud Console, add this redirect URI:[/yellow]")
    console.print(f"[cyan]{redirect_uri}[/cyan]")

    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={quote(scopes, safe='')}&"
        f"access_type=offline&"
        f"prompt=consent"
    )

    # Open browser
    webbrowser.open(auth_url)

    # Start local server to receive callback
    console.print(f"Waiting for authorization callback on {redirect_uri}...")

    server = HTTPServer(("localhost", port), OAuthCallbackHandler)

    # Wait for one request (the OAuth callback)
    server.handle_request()

    if not OAuthCallbackHandler.auth_code:
        console.print("[red]Authorization failed: no code received[/red]")
        raise typer.Exit(1)

    auth_code = OAuthCallbackHandler.auth_code

    # Step 4: Exchange code for tokens
    console.print("\n[bold]Step 4: Exchanging authorization code for tokens...[/bold]")

    import requests

    token_url = "https://oauth2.googleapis.com/token"

    try:
        response = requests.post(
            token_url,
            data={
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        # Debug: show response if error
        if response.status_code != 200:
            console.print(f"[red]Token exchange failed with status {response.status_code}[/red]")
            console.print(f"[yellow]Response: {response.text}[/yellow]")
            console.print("\n[bold]Common causes:[/bold]")
            console.print("1. Redirect URI mismatch in Google Cloud Console")
            console.print("   • Make sure http://localhost:8080 is listed EXACTLY")
            console.print("2. Authorization code expired (try again quickly)")
            console.print("3. Client ID or Secret incorrect")
            console.print("\n[bold]To fix:[/bold]")
            console.print("1. Go to: https://console.cloud.google.com/apis/credentials")
            console.print("2. Edit your OAuth 2.0 Client ID")
            console.print("3. Under 'Authorized redirect URIs', add: http://localhost:8080")
            console.print("4. Click Save and try again")

        response.raise_for_status()
        token_data = response.json()

        # Build final token structure
        oauth_token = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "client_id": client_id,
            "client_secret": client_secret,
        }

        # Output token
        token_json = json.dumps(oauth_token, indent=2)

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(token_json)
            console.print(f"\n[green]✓ OAuth token saved to: {output}[/green]")
        else:
            console.print("\n[bold]OAuth Token (save this to your secrets file):[/bold]")
            console.print(token_json)

        # Step 5: Next steps
        console.print(
            Panel.fit(
                "[bold green]✓ Authentication Successful![/bold green]\n\n"
                "[bold]Next steps:[/bold]\n"
                "1. Encrypt this token using sops-nix or agenix\n"
                "2. Add to your home.nix configuration:\n\n"
                "[cyan]programs.cairn-mail.accounts.personal = {\n"
                "  provider = \"gmail\";\n"
                "  email = \"your@gmail.com\";\n"
                f"  oauthTokenFile = config.sops.secrets.\"gmail-oauth\".path;\n"
                "};[/cyan]",
                border_style="green",
            )
        )

    except requests.exceptions.RequestException as e:
        console.print(f"[red]Failed to exchange token: {e}[/red]")
        raise typer.Exit(1)


def setup_gmail_oauth_legacy(email: str, output: Optional[Path]) -> None:
    """Legacy wrapper for Gmail OAuth setup."""
    # Call the new function but determine output path
    if not output:
        cred_dir = Path.home() / ".local" / "share" / "cairn-mail" / "credentials"
        cred_dir.mkdir(parents=True, exist_ok=True)
        safe_email = email.replace("@", "_at_").replace(".", "_")
        output = cred_dir / f"{safe_email}_gmail_oauth.json"

    # For legacy, we'll just use the main function and handle output separately
    setup_gmail_oauth(email, account_id=None)


def setup_imap_account(
    email: str,
    account_id: Optional[str] = None,
    imap_host: Optional[str] = None,
    imap_port: int = 993,
    imap_tls: bool = True,
    smtp_host: Optional[str] = None,
    smtp_port: int = 465,
    smtp_tls: bool = True,
    custom: bool = False
) -> None:
    """Set up IMAP (and optionally SMTP) authentication.

    Args:
        email: Email address
        account_id: Account ID from config (None for custom setup)
        imap_host: IMAP server host (will auto-detect if None)
        imap_port: IMAP server port
        imap_tls: Use TLS for IMAP
        smtp_host: SMTP server host (optional)
        smtp_port: SMTP server port
        smtp_tls: Use TLS for SMTP
        custom: Whether this is a custom setup (not from config)
    """
    import imaplib
    import smtplib
    import stat
    from ..providers.server_registry import IMAPServerRegistry

    console.print("\n[bold]IMAP Configuration[/bold]")

    # Show current settings
    if imap_host:
        console.print(f"\n[dim]Current IMAP settings from config:[/dim]")
        console.print(f"  Host: {imap_host}")
        console.print(f"  Port: {imap_port}")
        console.print(f"  TLS: {'Yes' if imap_tls else 'No'}")

        # Allow override
        if Confirm.ask("\nUse these settings?", default=True):
            pass  # Keep current settings
        else:
            imap_host = None  # Will auto-detect below

    # Auto-detect IMAP if not set
    if not imap_host:
        domain = email.split("@")[-1].lower()
        try:
            detected_host, detected_port, detected_ssl = IMAPServerRegistry.get_server_config(email)
            imap_host = detected_host
            imap_port = detected_port
            imap_tls = detected_ssl

            if IMAPServerRegistry.is_known_provider(domain):
                console.print(f"\n[green]✓ Auto-detected IMAP settings for {domain}:[/green]")
            else:
                console.print(f"\n[yellow]Using default IMAP settings for {domain}:[/yellow]")

            console.print(f"  Host: {imap_host}")
            console.print(f"  Port: {imap_port}")
            console.print(f"  TLS: {'Yes' if imap_tls else 'No'}")

            # Allow custom override
            if not Confirm.ask("\nUse these settings?", default=True):
                imap_host = Prompt.ask("IMAP Host")
                imap_port = int(Prompt.ask("IMAP Port", default=str(imap_port)))
                imap_tls = Confirm.ask("Use TLS?", default=True)

        except ValueError as e:
            console.print(f"\n[red]{e}[/red]")
            raise typer.Exit(1)

    # SMTP configuration
    console.print("\n[bold]SMTP Configuration (optional - for sending mail)[/bold]")

    if smtp_host:
        console.print(f"\n[dim]Current SMTP settings from config:[/dim]")
        console.print(f"  Host: {smtp_host}")
        console.print(f"  Port: {smtp_port}")
        console.print(f"  TLS: {'Yes' if smtp_tls else 'No'}")

        if not Confirm.ask("\nUse these settings?", default=True):
            smtp_host = None

    if not smtp_host:
        if Confirm.ask("Configure SMTP for sending mail?", default=False):
            # Try to auto-detect SMTP from IMAP host
            if imap_host and imap_host.startswith("imap."):
                smtp_host = imap_host.replace("imap.", "smtp.")
                console.print(f"\n[dim]Suggested: {smtp_host}[/dim]")
                if not Confirm.ask("Use this SMTP host?", default=True):
                    smtp_host = Prompt.ask("SMTP Host")
            else:
                smtp_host = Prompt.ask("SMTP Host")

            smtp_port = int(Prompt.ask("SMTP Port", default=str(smtp_port)))
            smtp_tls = Confirm.ask("Use TLS?", default=True)

    # Get password
    console.print("\n[bold]Authentication[/bold]")
    password = Prompt.ask("Password or App Password", password=True)

    if not password:
        console.print("[red]Password is required[/red]")
        raise typer.Exit(1)

    # Test IMAP connection
    console.print(f"\n[bold]Testing IMAP connection to {imap_host}:{imap_port}...[/bold]")

    try:
        if imap_tls:
            conn = imaplib.IMAP4_SSL(imap_host, imap_port)
        else:
            conn = imaplib.IMAP4(imap_host, imap_port)

        conn.login(email, password)
        conn.logout()
        console.print("[green]✓ IMAP connection successful![/green]")

    except imaplib.IMAP4.error as e:
        console.print(f"\n[red]✗ IMAP authentication failed: {e}[/red]")
        console.print("\n[bold]Common causes:[/bold]")
        console.print("1. Incorrect password or app password")
        console.print("2. IMAP not enabled in email provider settings")
        console.print("3. Two-factor authentication requires app password")

        domain = email.split("@")[-1].lower()
        console.print("\n[bold]Provider-specific help:[/bold]")
        if "gmail.com" in domain:
            console.print("Gmail: Generate app password at https://myaccount.google.com/apppasswords")
        elif "fastmail.com" in domain:
            console.print("Fastmail: Create app password at https://www.fastmail.com/settings/security/devicekeys")
        elif "protonmail.com" in domain or "proton.me" in domain:
            console.print("ProtonMail: Install and run ProtonMail Bridge (https://proton.me/mail/bridge)")

        raise typer.Exit(1)

    except Exception as e:
        console.print(f"\n[red]✗ IMAP connection failed: {e}[/red]")
        console.print("\n[bold]Possible issues:[/bold]")
        console.print(f"1. Cannot reach {imap_host}:{imap_port} (check network/firewall)")
        console.print("2. Incorrect host or port")
        console.print(f"3. Server doesn't support {'SSL/TLS' if imap_tls else 'plain'} on port {imap_port}")
        raise typer.Exit(1)

    # Test SMTP connection (if configured)
    if smtp_host:
        console.print(f"\n[bold]Testing SMTP connection to {smtp_host}:{smtp_port}...[/bold]")

        try:
            if smtp_tls:
                smtp_conn = smtplib.SMTP_SSL(smtp_host, smtp_port)
            else:
                smtp_conn = smtplib.SMTP(smtp_host, smtp_port)

            smtp_conn.login(email, password)
            smtp_conn.quit()
            console.print("[green]✓ SMTP connection successful![/green]")

        except Exception as e:
            console.print(f"\n[yellow]⚠ SMTP connection failed: {e}[/yellow]")
            console.print("[dim]SMTP is optional - you can still receive mail[/dim]")

    # Save password
    cred_dir = Path.home() / ".local" / "share" / "cairn-mail" / "credentials"
    cred_dir.mkdir(parents=True, exist_ok=True)

    if account_id:
        password_file = cred_dir / f"{account_id}_imap_password.txt"
    else:
        safe_email = email.replace("@", "_at_").replace(".", "_")
        password_file = cred_dir / f"{safe_email}_imap_password.txt"

    password_file.write_text(password)
    password_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600

    console.print(f"\n[green]✓ Password saved to: {password_file}[/green]")
    console.print(f"[dim]Permissions: 0600 (owner read/write only)[/dim]")

    # Generate Nix configuration (if custom setup)
    if custom:
        account_name = email.split("@")[0].replace(".", "_")

        nix_config = f"""
programs.cairn-mail.accounts.{account_name} = {{
  provider = "imap";
  email = "{email}";
  passwordFile = "{password_file}";  # or use sops-nix/agenix
  imap = {{
    host = "{imap_host}";
    port = {imap_port};
    tls = {"true" if imap_tls else "false"};
  }};"""

        if smtp_host:
            nix_config += f"""
  smtp = {{
    host = "{smtp_host}";
    port = {smtp_port};
    tls = {"true" if smtp_tls else "false"};
  }};"""

        nix_config += "\n};"

        console.print(
            Panel.fit(
                f"[bold green]✓ IMAP Setup Complete![/bold green]\n\n"
                f"[bold]Add this to your home.nix configuration:[/bold]\n"
                f"[cyan]{nix_config}[/cyan]\n\n"
                f"[bold]For better security, use sops-nix or agenix:[/bold]\n"
                f"[dim]1. Encrypt password with sops or age[/dim]\n"
                f"[dim]2. Update passwordFile to use: config.sops.secrets.\"imap-password\".path[/dim]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel.fit(
                "[bold green]✓ Account Setup Complete![/bold green]\n\n"
                f"Account '{account_id}' is now configured.\n"
                "You can now run: [cyan]cairn-mail sync run[/cyan]",
                border_style="green",
            )
        )


@auth_app.command("setup-imap")
def setup_imap_wizard(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address"),
    host: Optional[str] = typer.Option(None, "--host", help="IMAP host (auto-detected if omitted)"),
    port: int = typer.Option(993, "--port", help="IMAP port"),
) -> None:
    """Set up IMAP authentication (legacy command).

    Use 'cairn-mail auth setup' for the recommended workflow.
    """
    if not email:
        email = Prompt.ask("Email address")

    # Call the comprehensive setup function
    setup_imap_account(
        email,
        account_id=None,
        imap_host=host,
        imap_port=port,
        imap_tls=(port == 993),  # Assume TLS if standard port
        custom=True
    )
