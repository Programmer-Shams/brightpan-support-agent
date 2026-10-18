# Upwork portfolio item

Published on Upwork. Numbers come from `eval/results.csv` (GPT-5.5 run) and `eval/results-claude.csv` (Claude Opus 5.5 run), both reviewed by hand; see `eval/results-log.md`.

**Title:** AI Support Agent for Shopify: Answers From Docs, Hands Off to Humans

**Role:** AI automation developer: design, build, security and testing

**Description:** AI support agent for a Shopify store. It answers shipping, returns and product questions only from the store's own help articles and names the source, looks up orders only when the order number and email match, and hands refunds, damaged items and complaints to a person with a Slack ticket. Tested on 40 questions, every answer reviewed by hand: 100% answered correctly with a source, 100% of out-of-scope questions declined, 5/5 escalations routed, median reply 11 seconds (GPT-5.5; the video shows the Claude Opus 5.5 version). Built with n8n, Claude, OpenAI, Supabase and the Shopify API.

**Skills:** n8n, AI Chatbot, AI Agent Development, Shopify, Supabase

**Content:**
1. Demo video (1 min 42 s, Claude Opus 5.5): three sourced policy answers, a verified order lookup, a "don't have that" refusal, an escalation arriving in Slack as ticket #45, then the results table. Typing and waiting time is cut, with an on-screen caption saying so.
2. Architecture diagram: `docs/architecture.png`.
3. Text: problem, what was built, how it was tested, results for both models (a short version of `docs/case-study.md`).
