"""AI classifier using OpenAI-compatible API for email categorization."""

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

import requests

from .providers.base import Classification, Message

if TYPE_CHECKING:
    from .db.database import Database
    from .db.models import Feedback

logger = logging.getLogger(__name__)


@dataclass
class AIConfig:
    """AI classifier configuration for OpenAI-compatible API backends."""

    model: str = "claude-sonnet-4-20250514"
    endpoint: str = "http://localhost:18789"
    temperature: float = 0.3
    timeout: int = 30
    custom_tags: Optional[List[Dict[str, str]]] = None


class AIClassifier:
    """AI-powered email classifier using an OpenAI-compatible API."""

    # Default tag taxonomy
    DEFAULT_TAGS = [
        {"name": "work", "description": "Work-related emails from colleagues, managers, or work tools"},
        {"name": "personal", "description": "Personal correspondence from friends and family"},
        {"name": "finance", "description": "Bills, transactions, statements, invoices, payment confirmations"},
        {"name": "shopping", "description": "Receipts, order confirmations, shipping notifications"},
        {"name": "travel", "description": "Flight confirmations, hotel bookings, itineraries"},
        {"name": "dev", "description": "Developer notifications: GitHub, GitLab, CI/CD, code reviews"},
        {"name": "social", "description": "Social media notifications and updates"},
        {"name": "newsletter", "description": "Newsletters, digests, subscriptions"},
        {"name": "junk", "description": "Promotional emails, spam, marketing"},
    ]

    def __init__(self, config: AIConfig):
        """Initialize AI classifier.

        Args:
            config: AI configuration
        """
        self.config = config
        self.tags = config.custom_tags or self.DEFAULT_TAGS

    def _build_few_shot_block(self, feedback_examples: List["Feedback"]) -> str:
        """Build a few-shot learning block from user feedback examples.

        Args:
            feedback_examples: List of Feedback entries with corrections

        Returns:
            Formatted string for injection into the classification prompt
        """
        if not feedback_examples:
            return ""

        examples_text = []
        for fb in feedback_examples:
            # Format each correction as a learning example
            snippet = fb.context_snippet[:150] if fb.context_snippet else "(no snippet)"
            original = ", ".join(fb.original_tags) if fb.original_tags else "(none)"
            corrected = ", ".join(fb.corrected_tags) if fb.corrected_tags else "(none)"

            examples_text.append(
                f"  - From: *@{fb.sender_domain}\n"
                f"    Subject pattern: {fb.subject_pattern or '(no pattern)'}\n"
                f"    Snippet: {snippet}\n"
                f"    AI suggested: [{original}] → User corrected: [{corrected}]"
            )

        block = (
            "\nUSER PREFERENCE HISTORY:\n"
            "The user has made the following corrections to AI classifications.\n"
            "Learn from these examples and apply similar patterns:\n\n"
            + "\n\n".join(examples_text)
            + "\n\nIMPORTANT: Prioritize the user's preferences shown above when classifying similar emails.\n"
        )

        return block

    @staticmethod
    def _extract_domain(email: str) -> str:
        """Extract domain from email address.

        Args:
            email: Email address (e.g., "user@github.com")

        Returns:
            Domain part (e.g., "github.com")
        """
        if "@" in email:
            return email.split("@")[-1].lower()
        return email.lower()

    def _build_prompt(
        self, message: Message, feedback_examples: Optional[List["Feedback"]] = None
    ) -> str:
        """Build classification prompt for the LLM.

        Args:
            message: Message to classify
            feedback_examples: Optional list of user feedback for few-shot learning

        Returns:
            Prompt string
        """
        # Build tag descriptions
        tag_descriptions = "\n".join(
            [f'    - "{tag["name"]}": {tag["description"]}' for tag in self.tags]
        )

        # Build few-shot learning block if feedback available
        few_shot_block = self._build_few_shot_block(feedback_examples or [])

        prompt = f"""
Analyze this email and classify it with structured tags.

EMAIL CONTENT:
Subject: {message.subject}
From: {message.from_email}
To: {", ".join(message.to_emails)}
Date: {message.date}
Snippet: {message.snippet}

AVAILABLE TAGS:
{tag_descriptions}
{few_shot_block}
CLASSIFICATION RULES:
1. Select 1-3 most relevant tags from the list above
2. Set priority to "high" if:
   - From important senders (boss, family, banks)
   - Contains urgent language (ASAP, urgent, deadline)
   - Requires immediate attention
3. Set action_required to true if:
   - Requires a reply
   - Contains a task or to-do
   - Needs payment or form submission
4. Set can_archive to true ONLY if:
   - It's a receipt, shipping notification, or newsletter
   - AND requires no action from the user
   - When in doubt, set to false
5. Set confidence between 0.0 and 1.0:
   - 0.9-1.0: Very confident (clear category, obvious sender type)
   - 0.7-0.9: Confident (good match, some ambiguity)
   - 0.5-0.7: Uncertain (multiple categories possible)
   - Below 0.5: Low confidence (unclear content)

RESPOND WITH ONLY A JSON OBJECT (no markdown, no explanation):
{{
  "tags": ["tag1", "tag2"],
  "priority": "high" | "normal",
  "action_required": true | false,
  "can_archive": true | false,
  "confidence": 0.85
}}
"""
        return prompt

    def classify(
        self,
        message: Message,
        db: Optional["Database"] = None,
        account_id: Optional[str] = None,
    ) -> Classification:
        """Classify a message using the AI model.

        Args:
            message: Message to classify
            db: Optional database for DFSL feedback retrieval
            account_id: Optional account ID for DFSL feedback retrieval

        Returns:
            Classification result

        Raises:
            Exception: If classification fails
        """
        # Retrieve DFSL feedback examples if database available
        feedback_examples = []
        if db and account_id:
            try:
                sender_domain = self._extract_domain(message.from_email)
                feedback_examples = db.get_relevant_feedback(
                    account_id=account_id,
                    sender_domain=sender_domain,
                    limit=5,
                )
                if feedback_examples:
                    logger.debug(
                        f"DFSL: Using {len(feedback_examples)} feedback examples "
                        f"for classification of {message.id[:8]}"
                    )
            except Exception as e:
                logger.warning(f"Failed to retrieve DFSL feedback: {e}")

        prompt = self._build_prompt(message, feedback_examples)

        try:
            response = requests.post(
                f"{self.config.endpoint}/v1/chat/completions",
                json={
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": self.config.temperature,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.config.timeout,
            )

            response.raise_for_status()
            result = response.json()

            # Parse LLM response
            classification_json = result["choices"][0]["message"]["content"] or ""
            if not classification_json.strip():
                logger.error(
                    f"LLM returned empty content for message {message.id[:8]}, "
                    f"full response body: {json.dumps(result)[:500]}"
                )
            classification_data = json.loads(classification_json)

            # Validate and normalize
            tags = self._normalize_tags(classification_data.get("tags", []))
            priority = classification_data.get("priority", "normal")
            if priority not in ["high", "normal"]:
                priority = "normal"

            todo = classification_data.get("action_required", False)
            can_archive = classification_data.get("can_archive", False)

            # Parse confidence, default to 0.8 if not provided
            confidence = classification_data.get("confidence", 0.8)
            try:
                confidence = float(confidence)
                # Clamp to valid range
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.8

            classification = Classification(
                tags=tags,
                priority=priority,
                todo=todo,
                can_archive=can_archive,
                confidence=confidence,
            )

            logger.info(
                f"Classified message {message.id[:8]}: "
                f"tags={tags}, priority={priority}, todo={todo}, archive={can_archive}, "
                f"confidence={confidence:.2f}"
            )

            return classification

        except requests.exceptions.Timeout:
            logger.error(
                f"LLM request timed out after {self.config.timeout}s for message {message.id}"
            )
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API error for message {message.id}: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response for message {message.id}: {e}")
            # Return default classification with low confidence
            return Classification(
                tags=["personal"],
                priority="normal",
                todo=False,
                can_archive=False,
                confidence=0.5,  # Low confidence for fallback
            )
        except Exception as e:
            logger.error(f"Unexpected error classifying message {message.id}: {e}")
            raise

    def _normalize_tags(self, tags: List[str]) -> List[str]:
        """Normalize and validate tags.

        Args:
            tags: Raw tags from LLM

        Returns:
            Normalized tags
        """
        # Convert to lowercase, strip whitespace
        normalized = [tag.lower().strip() for tag in tags]

        # Remove duplicates
        normalized = list(dict.fromkeys(normalized))

        # Filter to valid tags only
        valid_tag_names = {tag["name"] for tag in self.tags}
        normalized = [tag for tag in normalized if tag in valid_tag_names]

        # Ensure at least one tag
        if not normalized:
            normalized = ["personal"]

        return normalized

    def classify_batch(
        self,
        messages: List[Message],
        db: Optional["Database"] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Classification]:
        """Classify multiple messages (sequential for now).

        Args:
            messages: List of messages to classify
            db: Optional database for DFSL feedback retrieval
            account_id: Optional account ID for DFSL feedback retrieval

        Returns:
            Dict mapping message ID to classification
        """
        results = {}

        for message in messages:
            try:
                classification = self.classify(message, db=db, account_id=account_id)
                results[message.id] = classification
            except Exception as e:
                logger.warning(f"Skipping message {message.id} due to error: {e}")
                continue

        logger.info(f"Classified {len(results)}/{len(messages)} messages")
        return results

    def _build_reply_prompt(self, message: Message) -> str:
        """Build prompt for generating smart reply suggestions.

        Args:
            message: Message to generate replies for

        Returns:
            Prompt string
        """
        prompt = f"""
Generate 3-4 short, contextual reply suggestions for this email.

EMAIL CONTENT:
Subject: {message.subject}
From: {message.from_email}
Date: {message.date}
Content: {message.snippet}

GUIDELINES:
1. Keep each reply to 1-2 sentences maximum
2. Be professional but friendly
3. Provide variety: include casual, neutral, and formal options if appropriate
4. Make replies contextually relevant to the message content
5. Don't include greetings or signatures - just the core message
6. Replies should be complete thoughts that can stand alone

RESPOND WITH ONLY A JSON OBJECT (no markdown, no explanation):
{{
  "replies": [
    "Reply suggestion 1",
    "Reply suggestion 2",
    "Reply suggestion 3"
  ]
}}
"""
        return prompt

    def generate_replies(self, message: Message) -> List[str]:
        """Generate smart reply suggestions for a message.

        Args:
            message: Message to generate replies for

        Returns:
            List of reply suggestion strings (3-4 items)

        Raises:
            Exception: If reply generation fails
        """
        prompt = self._build_reply_prompt(message)

        try:
            response = requests.post(
                f"{self.config.endpoint}/v1/chat/completions",
                json={
                    "model": self.config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,  # Higher temperature for more creative replies
                    "response_format": {"type": "json_object"},
                },
                timeout=self.config.timeout,
            )

            response.raise_for_status()
            result = response.json()

            # Parse LLM response
            response_json = result["choices"][0]["message"]["content"]
            response_data = json.loads(response_json)

            # Extract replies
            replies = response_data.get("replies", [])

            # Validate and filter
            if not isinstance(replies, list):
                logger.warning(f"Invalid replies format for message {message.id}")
                return []

            # Filter to strings only and limit length
            valid_replies = []
            for reply in replies:
                if isinstance(reply, str) and reply.strip():
                    # Truncate very long replies
                    cleaned = reply.strip()[:500]
                    valid_replies.append(cleaned)

            logger.info(
                f"Generated {len(valid_replies)} smart replies for message {message.id[:8]}"
            )

            return valid_replies[:4]  # Max 4 replies

        except requests.exceptions.Timeout:
            logger.error(
                f"LLM request timed out after {self.config.timeout}s "
                f"generating replies for message {message.id}"
            )
            raise
        except requests.exceptions.RequestException as e:
            logger.error(
                f"LLM API error generating replies for message {message.id}: {e}"
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse LLM response for replies on message {message.id}: {e}"
            )
            return []  # Return empty on parse error (graceful degradation)
        except Exception as e:
            logger.error(
                f"Unexpected error generating replies for message {message.id}: {e}"
            )
            raise
