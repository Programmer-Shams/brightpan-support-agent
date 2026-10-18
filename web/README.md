# Brightpan chat app

The customer-facing chat for the Brightpan support agent. Built with Next.js 16 (App Router), Tailwind CSS v4 and shadcn/ui. See the root [README](../README.md) for the whole system.

## Run it

```
cp .env.example .env.local   # n8n/deploy.py fills in N8N_WEBHOOK_SECRET
npm install
npm run dev                  # http://127.0.0.1:3100
```

n8n must be running with the workflows deployed (see the root README).

## How it fits together

- `src/app/api/chat/route.ts` is the server route the page calls. It accepts only same-origin JSON and validates the message. It turns the browser's session id into a keyed hash and forwards the message to the n8n webhook with the `X-Brightpan-Key` header. The webhook URLs and key never reach the browser.
- `src/components/chat/support-chat.tsx` holds the conversation, the model switch (Claude Opus 5.5 or GPT-5.5) and the composer.
- `src/components/chat/message-parts.tsx` renders the reply text, the help-center source tags, a verified order card and the hand-off banner.
- `src/components/chat/trace-panel.tsx` lists each reply's steps and response time ("How each answer was made").
- `src/lib/types.ts` defines the reply shape, which matches `n8n/js/build_turn.js`. `toAgentReply` fills any missing field, so an unexpected reply can't crash the page.

Answers are rendered as plain React text (no HTML injection). The page works down to 375 px wide; on small screens, the steps and the model switch are in the "Steps" sheet.
