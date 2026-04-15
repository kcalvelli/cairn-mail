# Home-manager module for cairn-mail user configuration
# Handles: email accounts, AI settings, config file generation
# Services (web, sync, tailscale-serve) are handled by the NixOS module
{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.programs.cairn-mail;

  # Submodule for individual email accounts
  accountOption = types.submodule ({ name, config, ... }: {
    options = {
      provider = mkOption {
        type = types.enum [ "gmail" "imap" "outlook" ];
        description = "Email provider type.";
        example = "gmail";
      };

      email = mkOption {
        type = types.str;
        description = "Email address for this account.";
        example = "user@gmail.com";
      };

      realName = mkOption {
        type = types.str;
        default = "";
        description = "Real name to display for this account.";
        example = "John Doe";
      };

      # OAuth2 configuration (for Gmail, Outlook)
      oauthTokenFile = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = ''
          Path to OAuth2 token file (decrypted by sops-nix, agenix, or systemd-creds).
          Required for Gmail and Outlook providers.
        '';
        example = literalExpression ''config.sops.secrets."email/gmail-oauth".path'';
      };

      # IMAP configuration (for IMAP provider)
      passwordFile = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = ''
          Path to password file for IMAP authentication.
          Required for IMAP provider.
        '';
        example = literalExpression ''config.sops.secrets."email/fastmail-password".path'';
      };

      imap = mkOption {
        type = types.nullOr (types.submodule {
          options = {
            host = mkOption {
              type = types.str;
              description = "IMAP server hostname.";
              example = "imap.fastmail.com";
            };

            port = mkOption {
              type = types.port;
              default = 993;
              description = "IMAP server port.";
            };

            tls = mkOption {
              type = types.bool;
              default = true;
              description = "Use TLS for IMAP connection.";
            };
          };
        });
        default = null;
        description = "IMAP server configuration (required for IMAP provider).";
      };

      smtp = mkOption {
        type = types.nullOr (types.submodule {
          options = {
            host = mkOption {
              type = types.str;
              description = "SMTP server hostname.";
              example = "smtp.fastmail.com";
            };

            port = mkOption {
              type = types.port;
              default = 465;
              description = "SMTP server port.";
            };

            tls = mkOption {
              type = types.bool;
              default = true;
              description = "Use TLS for SMTP connection.";
            };
          };
        });
        default = null;
        description = "SMTP server configuration (for sending mail).";
      };

      sync = mkOption {
        type = types.submodule {
          options = {
            enableWebhooks = mkOption {
              type = types.bool;
              default = false;
              description = "Enable real-time webhooks (Gmail Pub/Sub, MS Graph notifications).";
            };
          };
        };
        default = {};
        description = "Per-account sync configuration.";
      };

      hidden = mkOption {
        type = types.bool;
        default = false;
        description = ''
          Hide this account from the default inbox view.
          Hidden accounts still sync normally but are excluded from
          GET /accounts and GET /messages unless explicitly requested.
          Useful for agent/bot accounts that shouldn't appear in the UI.
        '';
      };

      labels = mkOption {
        type = types.submodule {
          options = {
            prefix = mkOption {
              type = types.str;
              default = "AI";
              description = "Prefix for AI-generated labels.";
              example = "MyAI";
            };

            colors = mkOption {
              type = types.attrsOf types.str;
              default = {};
              description = ''
                Label color overrides (provider-specific format).
                Usually not needed - all 35 default tags have category-based colors.
              '';
            };
          };
        };
        default = {};
        description = "Label configuration for AI tags.";
      };
    };
  });

  # Runtime configuration file
  runtimeConfig = {
    database_path = "${config.xdg.dataHome}/cairn-mail/mail.db";

    accounts = mapAttrs (name: account: {
      id = name;
      provider = account.provider;
      email = account.email;
      real_name = account.realName;

      credential_file =
        if account.oauthTokenFile != null then account.oauthTokenFile
        else if account.passwordFile != null then account.passwordFile
        else throw "Account ${name}: either oauthTokenFile or passwordFile must be set";

      settings = {
        label_prefix = account.labels.prefix;
        label_colors = account.labels.colors;
        enable_webhooks = account.sync.enableWebhooks;
        ai_model = cfg.ai.model;
        ai_endpoint = cfg.ai.endpoint;
        ai_temperature = cfg.ai.temperature;
      } // optionalAttrs account.hidden {
        hidden = true;
      } // optionalAttrs (account.imap != null) {
        imap_host = account.imap.host;
        imap_port = account.imap.port;
        imap_tls = account.imap.tls;
      } // optionalAttrs (account.smtp != null) {
        smtp_host = account.smtp.host;
        smtp_port = account.smtp.port;
        smtp_tls = account.smtp.tls;
        smtp_password_file = account.passwordFile;
      };
    }) cfg.accounts;

    ai = {
      enable = cfg.ai.enable;
      model = cfg.ai.model;
      endpoint = cfg.ai.endpoint;
      temperature = cfg.ai.temperature;
      useDefaultTags = cfg.ai.useDefaultTags;
      tags = cfg.ai.tags;
      excludeTags = cfg.ai.excludeTags;
      labelPrefix = cfg.ai.labelPrefix;
      labelColors = cfg.ai.labelColors;
    };

    sync = {
      maxMessagesPerSync = cfg.sync.maxMessagesPerSync;
      enableWebhooks = cfg.sync.enableWebhooks;
    };

  } // optionalAttrs cfg.push.enable {
    push = {
      enable = true;
      vapidPrivateKeyFile = cfg.push.vapidPrivateKeyFile;
      vapidPublicKey = cfg.push.vapidPublicKey;
      contactEmail = cfg.push.contactEmail;
    };

  } // optionalAttrs cfg.gateway.enable {
    gateway = {
      enable = true;
      url = cfg.gateway.url;
      addressbook = cfg.gateway.addressbook;
      calendar = cfg.gateway.calendar;
    };

    actions = mapAttrs (name: action: {
      description = action.description;
      server = action.server;
      tool = action.tool;
    } // optionalAttrs (action.extractionPrompt != null) {
      extractionPrompt = action.extractionPrompt;
    } // optionalAttrs (action.defaultArgs != {}) {
      defaultArgs = action.defaultArgs;
    } // optionalAttrs (!action.enabled) {
      enabled = false;
    }) cfg.actions;
  };

in {
  options.programs.cairn-mail = {
    enable = mkEnableOption "cairn-mail user configuration";

    package = mkOption {
      type = types.package;
      default = pkgs.cairn-mail;
      defaultText = literalExpression "pkgs.cairn-mail";
      description = "The cairn-mail package to use (from overlay).";
    };

    accounts = mkOption {
      type = types.attrsOf accountOption;
      default = {};
      description = "Email accounts to manage with cairn-mail.";
      example = literalExpression ''
        {
          personal = {
            provider = "gmail";
            email = "user@gmail.com";
            realName = "John Doe";
            oauthTokenFile = config.sops.secrets."gmail-oauth".path;
          };

          work = {
            provider = "imap";
            email = "user@fastmail.com";
            passwordFile = config.sops.secrets."fastmail-password".path;
            imap = {
              host = "imap.fastmail.com";
              port = 993;
            };
          };
        }
      '';
    };

    ai = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Enable AI classification.";
      };

      model = mkOption {
        type = types.str;
        default = "claude-sonnet-4-20250514";
        description = "Model name for the OpenAI-compatible API.";
        example = "llama3.2";
      };

      endpoint = mkOption {
        type = types.str;
        default = "http://localhost:18789";
        description = "OpenAI-compatible API endpoint (any /v1/chat/completions provider).";
      };

      temperature = mkOption {
        type = types.float;
        default = 0.3;
        description = "LLM temperature (0.0-1.0, lower = more deterministic).";
      };

      useDefaultTags = mkOption {
        type = types.bool;
        default = true;
        description = ''
          Use the expanded default tag taxonomy (35 tags).
          Custom tags in 'tags' will be appended to defaults.
        '';
      };

      tags = mkOption {
        type = types.listOf (types.submodule {
          options = {
            name = mkOption {
              type = types.str;
              description = "Tag name (lowercase, no spaces).";
            };

            description = mkOption {
              type = types.str;
              description = "Tag description for LLM prompt.";
            };
          };
        });
        default = [];
        description = "Custom tags for AI classification.";
      };

      excludeTags = mkOption {
        type = types.listOf types.str;
        default = [];
        description = "Tag names to exclude from the default taxonomy.";
      };

      labelPrefix = mkOption {
        type = types.str;
        default = "AI";
        description = "Prefix for AI-generated labels in email providers.";
      };

      labelColors = mkOption {
        type = types.attrsOf types.str;
        default = {};
        description = ''
          Override colors for specific tags.
          Usually not needed - all 35 default tags have category-based colors:
          priority=red, work=blue, personal=purple, finance=green,
          shopping=yellow, travel=cyan, developer=cyan, marketing=orange,
          social=teal, system=gray.
        '';
      };
    };

    sync = mkOption {
      type = types.submodule {
        options = {
          maxMessagesPerSync = mkOption {
            type = types.int;
            default = 100;
            description = "Maximum messages to fetch per sync.";
          };

          enableWebhooks = mkOption {
            type = types.bool;
            default = false;
            description = "Enable real-time webhooks (provider-specific).";
          };
        };
      };
      default = {};
      description = ''
        Global sync configuration.
        Note: Sync frequency/timing is configured in the NixOS module (services.cairn-mail.sync).
      '';
    };

    gateway = mkOption {
      type = types.submodule {
        options = {
          enable = mkEnableOption "mcp-gateway integration for action tags";

          url = mkOption {
            type = types.str;
            default = "http://localhost:8085";
            description = "mcp-gateway REST API URL for action tag execution.";
            example = "http://mcp-gateway.tailnet:8085";
          };

          addressbook = mkOption {
            type = types.str;
            default = "";
            description = ''
              vdirsyncer addressbook name for the add-contact action.
              Must match a configured addressbook in vdirsyncer/khard.
            '';
            example = "google";
          };

          calendar = mkOption {
            type = types.str;
            default = "";
            description = ''
              vdirsyncer calendar name for the create-reminder action.
              Must match a configured calendar in vdirsyncer.
            '';
            example = "personal";
          };
        };
      };
      default = {};
      description = "mcp-gateway configuration for action tag processing.";
    };

    push = mkOption {
      type = types.submodule {
        options = {
          enable = mkEnableOption "Web Push notifications for new emails";

          vapidPrivateKeyFile = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = ''
              Path to VAPID private key file (PEM format, decrypted by agenix or sops-nix).
              Generate with: openssl ecparam -genkey -name prime256v1 -noout -out vapid_private.pem
            '';
            example = literalExpression ''config.age.secrets.vapid-private-key.path'';
          };

          vapidPublicKey = mkOption {
            type = types.str;
            default = "";
            description = ''
              VAPID public key (base64url-encoded, safe to store in config).
              Generate from private key: openssl ec -in vapid_private.pem -pubout -outform DER | tail -c 65 | base64 | tr '/+' '_-' | tr -d '='
            '';
          };

          contactEmail = mkOption {
            type = types.str;
            default = "";
            description = ''
              Contact email for VAPID claims (mailto: URI).
              Required by push services to contact the app operator.
            '';
            example = "mailto:admin@example.com";
          };
        };
      };
      default = {};
      description = "Web Push notification configuration for mobile PWA.";
    };

    actions = mkOption {
      type = types.attrsOf (types.submodule {
        options = {
          description = mkOption {
            type = types.str;
            default = "";
            description = "Human-readable description of this action.";
          };

          server = mkOption {
            type = types.str;
            description = "MCP server ID in mcp-gateway (e.g., 'mcp-dav').";
            example = "mcp-dav";
          };

          tool = mkOption {
            type = types.str;
            description = "MCP tool name to call (e.g., 'create_contact').";
            example = "create_contact";
          };

          extractionPrompt = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = ''
              Custom LLM prompt for extracting data from the email.
              If null, the built-in prompt is used (for built-in actions).
            '';
          };

          defaultArgs = mkOption {
            type = types.attrsOf types.str;
            default = {};
            description = ''
              Default arguments to pass to the MCP tool.
              Extracted data is merged on top (does not override defaults).

              Note: For built-in actions, addressbook and calendar are
              configured via gateway.addressbook and gateway.calendar.
            '';
            example = literalExpression ''{ priority = "high"; }'';
          };

          enabled = mkOption {
            type = types.bool;
            default = true;
            description = "Whether this action is enabled.";
          };
        };
      });
      default = {};
      description = ''
        Action tags that trigger MCP tool calls via mcp-gateway.
        Built-in actions (add-contact, create-reminder) are always available
        when gateway is enabled. Use this to override built-in defaults
        (e.g., set addressbook/calendar names) or define custom actions.
      '';
      example = literalExpression ''
        {
          # Custom action
          "save-receipt" = {
            description = "Save receipt to expense tracker";
            server = "expenses";
            tool = "add_expense";
          };
        }
      '';
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.accounts != {};
        message = "cairn-mail: at least one account must be configured";
      }
      {
        assertion = cfg.push.enable -> cfg.push.vapidPrivateKeyFile != null;
        message = "cairn-mail: push.vapidPrivateKeyFile must be set when push notifications are enabled";
      }
      {
        assertion = cfg.push.enable -> cfg.push.vapidPublicKey != "";
        message = "cairn-mail: push.vapidPublicKey must be set when push notifications are enabled";
      }
      {
        assertion = cfg.push.enable -> cfg.push.contactEmail != "";
        message = "cairn-mail: push.contactEmail must be set when push notifications are enabled (e.g., mailto:you@example.com)";
      }
      {
        assertion = cfg.gateway.enable -> cfg.gateway.addressbook != "";
        message = "cairn-mail: gateway.addressbook must be set when gateway is enabled (vdirsyncer addressbook name)";
      }
      {
        assertion = cfg.gateway.enable -> cfg.gateway.calendar != "";
        message = "cairn-mail: gateway.calendar must be set when gateway is enabled (vdirsyncer calendar name)";
      }
    ] ++ (lib.flatten (lib.mapAttrsToList (name: account: [
      {
        assertion = (account.provider == "gmail" || account.provider == "outlook") -> account.oauthTokenFile != null;
        message = "cairn-mail account '${name}': OAuth providers require oauthTokenFile";
      }
      {
        assertion = account.provider == "imap" -> (account.passwordFile != null && account.imap != null);
        message = "cairn-mail account '${name}': IMAP provider requires passwordFile and imap configuration";
      }
    ]) cfg.accounts));

    # Add CLI to user's PATH
    home.packages = [ cfg.package ];

    # Create data directory
    home.file."${config.xdg.dataHome}/cairn-mail/.keep".text = "";

    # Generate runtime configuration
    xdg.configFile."cairn-mail/config.yaml".text = builtins.toJSON runtimeConfig;

    # Note: Sync service and timer are now in the NixOS module (services.cairn-mail.sync)
  };
}
