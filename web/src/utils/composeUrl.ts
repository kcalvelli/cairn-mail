/**
 * The one place that knows what query params Compose wants for reply/forward.
 *
 * These used to be hand-rolled at every Reply/Forward button. They drifted:
 * the mobile message page forgot forward_from, so phones forwarded a blank
 * page while desktop worked fine. Build the URL here, nowhere else.
 */

import type { Message } from '../api/types';

type ComposeSource = Pick<
  Message,
  'id' | 'from_email' | 'subject' | 'thread_id' | 'account_id' | 'date'
>;

const prefixed = (prefix: string, subject: string) =>
  subject.startsWith(prefix) ? subject : `${prefix}${subject}`;

/** Compose URL for replying to `message`, quoting it. `body` pre-fills above the quote. */
export function replyUrl(message: ComposeSource, body?: string): string {
  const params = new URLSearchParams({
    reply_to: message.id,
    to: message.from_email,
    subject: prefixed('Re: ', message.subject),
    thread_id: message.thread_id || '',
    account_id: message.account_id,
    quote_from: message.from_email,
    quote_date: message.date,
  });
  if (body) params.set('body', body);
  return `/compose?${params.toString()}`;
}

/** Compose URL for forwarding `message` (body + attachments get pulled in by Compose). */
export function forwardUrl(message: ComposeSource): string {
  const params = new URLSearchParams({
    forward_from: message.id,
    subject: prefixed('Fwd: ', message.subject),
    account_id: message.account_id,
  });
  return `/compose?${params.toString()}`;
}
