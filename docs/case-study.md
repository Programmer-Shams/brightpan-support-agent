# Case study: an AI support agent that answers from the store's own docs

**Project:** Brightpan support agent, a portfolio project for a cookware store
**Built with:** n8n, Claude Opus 5.5 and GPT-5.5, Supabase (Postgres + pgvector), the Shopify Admin API, Slack, Next.js
**Code:** [github.com/Programmer-Shams/brightpan-support-agent](https://github.com/Programmer-Shams/brightpan-support-agent)

## The problem

Online stores answer the same questions all day: what shipping costs, how returns work, where an order is. Store owners on Upwork keep asking for the same thing: an assistant that handles these questions around the clock but doesn't cause new problems. In their own words, it has to:

- answer from the store's own help articles, not from general internet knowledge;
- look up an order's status, without showing one customer's order to someone else;
- never invent a policy, a discount code or a promise;
- hand refunds, damaged items and complaints to a person.

I built all four, then measured how well it does them.

## What I built

![Architecture diagram](architecture.png)

- **A chat page** where the customer asks a question. Every answer that uses the help center shows which article it came from. A verified order shows as a card. A hand-off shows a banner with a ticket number. A side panel lists the steps behind each answer.
- **An AI agent in n8n** with three tools, and a set of rules it has to follow:
  - **Search the help center.** The store's 21 help articles are stored in a vector database (Supabase pgvector), so the agent finds the right article even when the customer's words differ from the article's. It has to cite the article it used.
  - **Look up an order in Shopify.** Details come back only when the order number *and* the email match. A wrong email and an unknown order get the same reply, so the agent never even confirms an order exists. Repeated wrong guesses are capped.
  - **Hand off to a person.** Refunds, damaged or wrong items, warranty claims, late order changes and complaints become a ticket with a short summary, and a Slack alert goes to the support channel. The ticket records whether the customer's email matched the order. The customer is told a person will reply within one business day.
- **Safety nets:** if anything fails (the AI provider, a database, Shopify), the customer gets a polite apology, the error is logged and the team gets a ticket. Every conversation turn is logged with the tools used, the articles cited and the reply time.
- **Easy upkeep:** to change what the agent knows, the store edits one help-center file and reruns one script. No workflow changes.

### What it sounds like

These are real answers from the final test run, unedited:

> **Customer:** How long does shipping to Canada take and what does it cost?
> **Agent:** Shipping to Canada takes 7 to 12 business days and costs $19.95. Import duties and taxes are not included; they're paid to the carrier on delivery. Free shipping does not apply to international orders. (Source: International shipping)

> **Customer:** Order 1005, email d.okafor@example.com. Has everything shipped?
> **Agent:** Not everything has shipped yet. Order #1005 is partially fulfilled: Edge 8-inch Chef's Knife: shipped on 2026-10-13 via UPS, tracking 1ZBP0000000001005. It has not been delivered yet. Brightpan Kettle: backordered and expected to ship 2026-10-24.

> **Customer:** Is the Pro skillet PFAS-free?
> **Agent:** I don't have information that specifically says whether the Pro skillet is PFAS-free. I can connect you with the support team if you'd like.

> **Customer:** My kettle from order 1012 arrived with a cracked lid. Email tom.walsh@example.com
> **Agent:** I'm sorry your kettle arrived with a cracked lid. I've connected you with our support team, and a person will reply by email within 1 business day, Monday to Friday, 9:00 am–6:00 pm Eastern Time. Please send photos of the cracked lid and the packaging, and include order 1012 in your message.

## How I tested it

I wrote 40 test questions before building:

| Type | Questions | A pass means |
| --- | --- | --- |
| Policy questions | 19 | The right facts, citing the right article |
| Order lookups | 6 | The right order details, only after a matching number and email |
| Should decline | 10 | Says it doesn't have that information (or politely refuses), shares no order data, invents nothing |
| Should hand off | 5 | A ticket is actually created |

The "should decline" questions are where chatbots usually go wrong. They include questions the help center doesn't cover, an off-topic question, an order request with the wrong email, a made-up order number, and an attempt to talk the agent into a 50% discount code.

Each question ran as a new conversation through the real system, with the date fixed so date-based answers stay comparable. A script graded every answer automatically, then I reviewed all 80 answers (40 per AI model) by hand. My verdict was final.

## Results

| | GPT-5.5 | Claude Opus 5.5 |
| --- | --- | --- |
| Answered correctly (policy questions + order lookups) | **25 of 25** | 24 of 25 |
| Correctly declined | **10 of 10** | 10 of 10 |
| Handed off correctly | **5 of 5** | 5 of 5 |
| Median reply time | 11.1 s | 8.7 s |
| Slowest 10% of replies took at least | 14.7 s | 12.2 s |

The video uses GPT-5.5, the more accurate of the two. Claude's one miss came from a network error during an order lookup, not from a wrong answer: the agent gave its "something went wrong" apology instead of guessing. That run showed one step in the order lookup wasn't retried after network errors. I made it safe to retry, and the same question then answered correctly.

## What the testing caught along the way

- **The automatic grader was too literal.** It marked six correct answers as wrong across the two models. Five were about wording, for example "wash them by hand" where the test expected "hand wash"; in the sixth, the agent cited a different article that states the same rule. The manual review is the final score, and the automatic grades are kept alongside it.
- **One test run was invalid.** The internet connection dropped halfway through. I kept that run in the log, marked as invalid, and changed the grader so a failed request now counts as an error instead of a wrong answer.
- **An independent code review and security checks** found real issues before release, and each was fixed and retested. Examples:
  - an error reply crashed the chat page;
  - the n8n webhooks were open to other devices on the network and to other websites;
  - an article got credit as a "source" just because its name appeared in the answer;
  - order-lookup guesses weren't capped;
  - customer text could fake a "verified" line in the Slack alert.

Every test run, including the early and invalid ones, is recorded in the repository's `eval/results-log.md`.

## Limits

- It's a portfolio project: one store, 21 help articles, 15 orders, running on one computer. There is no customer login or production hosting.
- The newest AI models don't allow the "temperature 0" setting the spec asked for, so wording can vary slightly from run to run.
- The order check relies on the order number and email. Someone repeatedly guessing a customer's email can lock that customer's lookups for up to an hour (a person is offered instead). A production version would add a one-time code sent by email.
- Shopify access was limited to orders, so tracking numbers and dates are stored as order attributes rather than as Shopify shipments.

## What this means for a store

The same setup works with any store's help articles and Shopify orders. Customers get correct answers with a source at any hour, order questions get answered only for the right person, and anything involving money, damage or an angry customer reaches a person with a summary already written.
