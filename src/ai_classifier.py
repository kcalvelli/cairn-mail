import json
import os
import sys
import argparse
import email
from email.policy import default
import requests
import pathlib

# Try to import notmuch, warn if missing (for dev environments without system pkgs)
try:
    import notmuch
except ImportError:
    notmuch = None

def load_config():
    config_dir = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    settings_path = pathlib.Path(config_dir) / "cairn-mail" / "config.json"
    
    if not settings_path.exists():
        return {}
            
    with open(settings_path, 'r') as f:
        return json.load(f)

def classify_email(text, endpoint, model):
    prompt = f"""
    Analyze this email and return ONLY a JSON object matching this schema:
    {{
      "tags": ["personal", "work", "finance", "travel", "dev", "junk", "marketing"],
      "priority": "high" | "normal",
      "action_required": boolean,
      "can_archive": boolean
    }}
    
    Rules:
    - "action_required": true if it's a direct message, bill, or requires reply.
    - "can_archive": true ONLY for receipts, shipping notifications, or newsletters that contain no tasks.
    - If unsure, "can_archive" must be false.
    - "tags" should include "junk" if it is spam/scam.
    
    Email:
    {text}
    """
    
    try:
        response = requests.post(f"{endpoint}/api/generate", json={
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False
        }, timeout=30)
        
        response.raise_for_status()
        return response.json().get("response", "")
        
    except Exception as e:
        print(f"Ollama Error: {e}", file=sys.stderr)
        return None

def extract_text(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))
            
            # skip attachments
            if 'attachment' in cdispo:
                continue
                
            if ctype == 'text/plain':
                body += part.get_payload(decode=True).decode(errors='replace')
    else:
        body = msg.get_payload(decode=True).decode(errors='replace')
        
    # Limit body size to save tokens
    return body[:2000]

def main():
    if not notmuch:
        print("Error: Python 'notmuch' bindings not installed.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="AI Email Classifier")
    parser.add_argument("--dry-run", action="store_true", help="Do not apply tags")
    parser.add_argument("--limit", type=int, default=50, help="Max emails to process")
    args = parser.parse_args()
    
    config = load_config()
    ai_config = config.get("ai", {})
    
    if not ai_config.get("enable", False):
        print("AI classification is disabled in config.")
        sys.exit(0)
        
    endpoint = ai_config.get("endpoint", "http://localhost:11434")
    model = ai_config.get("model", "llama3")
    
    # Explicitly find database path from config to avoid Python binding discovery issues
    try:
        # Check Env, then XDG default, then Legacy default
        xdg_config = os.path.expanduser("~/.config/notmuch/default/config")
        legacy_config = os.path.expanduser("~/.notmuch-config")
        
        config_path = os.environ.get("NOTMUCH_CONFIG")
        if not config_path:
             if os.path.exists(xdg_config):
                 config_path = xdg_config
             else:
                 config_path = legacy_config
        # Simple manual parse because configparser might struggle with some notmuch versions or we just want 'path'
        db_path = None
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                for line in f:
                    if line.strip().startswith("path="):
                        db_path = line.split("=", 1)[1].strip()
                        break
        
        # Open DB with explicit path if found, else rely on defaults
        if db_path:
             db = notmuch.Database(path=db_path, mode=notmuch.Database.MODE.READ_WRITE)
        else:
             db = notmuch.Database(mode=notmuch.Database.MODE.READ_WRITE)

    except Exception as e:
        print(f"Error opening Notmuch DB: {e}", file=sys.stderr)
        sys.exit(1)

    query = db.create_query("tag:new")
    
    processed = 0
    for msg in query.search_messages():
        if processed >= args.limit:
            break
            
        file_path = msg.get_filename()
        try:
            with open(file_path, 'rb') as f:
                email_obj = email.message_from_binary_file(f, policy=default)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            continue
            
        subject = email_obj.get("subject", "")
        sender = email_obj.get("from", "")
        body = extract_text(email_obj)
        
        content = f"From: {sender}\nSubject: {subject}\n\n{body}"
        
        print(f"Classifying: {subject[:50]}...", end=" ", flush=True)
        result_json_str = classify_email(content, endpoint, model)
        
        if result_json_str:
            try:
                result = json.loads(result_json_str)
                print(f"-> {result}")
                
                if not args.dry_run:
                    tags = result.get("tags", [])
                    priority = result.get("priority", "normal")
                    action = result.get("action_required", False)
                    archive = result.get("can_archive", False)
                    
                    # 1. Apply Categorical Tags
                    for t in tags:
                        # Clean tag name
                        t = t.lower().strip()
                        if t: msg.add_tag(t)
                        
                    # 2. Metadata Tags
                    msg.add_tag(f"prio-{priority}")
                    if action:
                        msg.add_tag("todo")
                        
                    # 3. Lifecycle
                    msg.remove_tag("new")
                    
                    # Junk handling (explicit tag take precedence)
                    if "junk" in tags:
                         msg.remove_tag("inbox")
                         msg.add_tag("junk")
                    # Archive logic: Only archive if SAFE and NO ACTION required
                    elif archive and not action:
                        msg.remove_tag("inbox")
                        msg.add_tag("archive")
                        
            except json.JSONDecodeError:
                 print(f"-> Failed to parse JSON: {result_json_str[:50]}...")
        else:
             print("-> Failed (API Error)")
            
        processed += 1

if __name__ == "__main__":
    main()
