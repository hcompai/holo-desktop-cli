import { useEffect, useRef, useState } from "react";

import { isBroken } from "../regressions.js";

// Scripted on purpose: the QA spec needs a deterministic Expected Result, so the
// "AI assistant" is keyword-matched canned replies, not a model.
const REPLIES = [
  {
    match: /refund/i,
    text: "Refunds are processed within 5 business days of approval. Annual plans are refundable pro-rata within 30 days.",
    escalate: true,
  },
  {
    match: /hours|open|available/i,
    text: "Support is available Monday to Friday, 9:00–18:00 CET. Outside those hours, leave a message and we'll follow up.",
  },
  {
    match: /password|reset|login/i,
    text: "You can reset your password from Settings → Security, or via the 'Forgot password' link on the sign-in page.",
  },
];

const FALLBACK =
  "I'm not sure about that one. Try asking about refunds, support hours, or password resets — or I can connect you to a human.";

const GREETING = { from: "bot", text: "Hi! I'm the Nimbus assistant. How can I help today?" };

function composeReply(text) {
  const reply = REPLIES.find((r) => r.match.test(text));
  if (!reply) return { text: FALLBACK, escalate: true };
  return { text: reply.text, escalate: reply.escalate };
}

const TYPING_DELAY_MS = 800;
const FIRST_TICKET_NUMBER = 1042;

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([GREETING]);
  const [draft, setDraft] = useState("");
  const [typing, setTyping] = useState(false);
  const [unread, setUnread] = useState(0);
  const [escalating, setEscalating] = useState(false);
  const [ticketCount, setTicketCount] = useState(0);
  const openRef = useRef(open);
  const logRef = useRef(null);

  openRef.current = open;

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [messages, typing, escalating]);

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    // chat-badge-stuck: the unread counter never resets when the widget opens.
    if (next && !isBroken("chat-badge-stuck")) {
      setUnread(0);
    }
  }

  function pushBotMessage(message) {
    setMessages((m) => [...m, { from: "bot", ...message }]);
    if (!openRef.current) {
      setUnread((u) => u + 1);
    }
  }

  function send(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || typing) return;
    setMessages((m) => [...m, { from: "user", text }]);
    setDraft("");
    setTyping(true);

    // chat-no-reply: the bot "types" forever and the reply never arrives.
    if (isBroken("chat-no-reply")) return;

    setTimeout(() => {
      setTyping(false);
      // Surface reply-pipeline failures in the chat itself: an on-screen error a
      // black-box (visual) QA tester can read and relay verbatim.
      try {
        pushBotMessage(composeReply(text));
      } catch (err) {
        pushBotMessage({ text: `Assistant error: ${err.message}`, error: true });
      }
    }, TYPING_DELAY_MS);
  }

  function submitEscalation(event) {
    event.preventDefault();
    const form = new FormData(event.target);
    const ticket = FIRST_TICKET_NUMBER + ticketCount;
    setTicketCount((c) => c + 1);
    setEscalating(false);
    pushBotMessage({
      text: `Done — I've opened ticket ND-${ticket} for "${form.get("summary")}". A human will reply to ${form.get("email")} within one business day.`,
    });
  }

  return (
    <div className="chat-root">
      {open && (
        <div className="chat-panel" data-testid="chat-panel">
          <div className="chat-header">
            <span>Nimbus assistant</span>
            <button className="btn btn-ghost" onClick={toggleOpen} aria-label="Close chat">
              ✕
            </button>
          </div>

          <div className="chat-log" ref={logRef} data-testid="chat-log">
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg chat-msg-${m.from}${m.error ? " chat-msg-error" : ""}`} {...(m.error && { role: "alert", "data-testid": "chat-error" })}>
                <p>{m.text}</p>
                {m.from === "bot" && m.escalate && !escalating && (
                  <button className="btn btn-link" onClick={() => setEscalating(true)} data-testid="escalate">
                    Talk to a human
                  </button>
                )}
              </div>
            ))}
            {typing && (
              <div className="chat-msg chat-msg-bot chat-typing" data-testid="chat-typing">
                <span>•</span>
                <span>•</span>
                <span>•</span>
              </div>
            )}
            {escalating && (
              <form className="escalation-form" onSubmit={submitEscalation} data-testid="escalation-form">
                <strong>Contact a human</strong>
                <input name="email" type="email" placeholder="Your email" required />
                <input name="summary" type="text" placeholder="One-line summary" required />
                <div className="escalation-actions">
                  <button className="btn btn-ghost" type="button" onClick={() => setEscalating(false)}>
                    Cancel
                  </button>
                  <button className="btn btn-primary" type="submit">
                    Open ticket
                  </button>
                </div>
              </form>
            )}
          </div>

          <form className="chat-input" onSubmit={send}>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask about refunds, hours, passwords…"
              data-testid="chat-input"
            />
            <button className="btn btn-primary" type="submit" disabled={!draft.trim() || typing}>
              Send
            </button>
          </form>
        </div>
      )}

      <button className="chat-bubble" onClick={toggleOpen} data-testid="chat-bubble" aria-label="Open chat">
        💬
        {unread > 0 && (
          <span className="chat-unread" data-testid="chat-unread">
            {unread}
          </span>
        )}
      </button>
    </div>
  );
}
