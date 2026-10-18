import { BookOpen, CircleSlash, Package, UserRound } from "lucide-react";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = { icon: typeof BookOpen; text: string; tone?: "verified" | "amber" | "muted" };

function stepsFor(m: Extract<ChatMessage, { role: "assistant" }>): Step[] {
  const r = m.reply;
  const steps: Step[] = [];
  if (r.tools_called.includes("search_help_center")) {
    steps.push({
      icon: BookOpen,
      text: r.sources.length
        ? `Searched the help center, cited ${r.sources.map((s) => s.title).join(" and ")}`
        : `Searched the help center, found nothing that answers this`,
      tone: r.sources.length ? undefined : "muted",
    });
  }
  if (r.tools_called.includes("lookup_order")) {
    steps.push(
      r.lookup === "match"
        ? { icon: Package, text: `Looked up order ${r.order?.number ?? ""}, email matched`, tone: "verified" }
        : { icon: Package, text: "Looked up an order, no match, so no details shared", tone: "muted" },
    );
  }
  if (r.escalated) {
    steps.push({
      icon: UserRound,
      text:
        `Handed off to the support team${r.handoff_id ? `, ticket #${r.handoff_id}` : ""}` +
        (r.handoff_verified ? ", email matches the order" : ", not verified against an order"),
      tone: "amber",
    });
  }
  if (!steps.length) steps.push({ icon: CircleSlash, text: "Answered without looking anything up", tone: "muted" });
  return steps;
}

export function TracePanel({ messages, className }: { messages: ChatMessage[]; className?: string }) {
  const turns = messages.filter((m): m is Extract<ChatMessage, { role: "assistant" }> => m.role === "assistant");
  return (
    <div className={cn("flex flex-col gap-5", className)}>
      <div>
        <h2 className="type-display text-lg">How each answer was made</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Every reply comes from a help center article, a verified order or a hand-off to a person.
        </p>
      </div>
      {turns.length === 0 ? (
        <p className="text-sm text-muted-foreground">Ask a question and its steps appear here.</p>
      ) : (
        <ol className="relative space-y-6 border-l border-steel-line pl-5">
          {turns.map((t, i) => (
            <li key={t.id} className="relative">
              <span
                aria-hidden
                className="absolute top-1 -left-[25px] size-2.5 rounded-full border-2 border-background bg-enamel"
              />
              <p className="text-xs text-muted-foreground">
                Reply {i + 1} by {t.reply.model === "gpt-5.5" ? "GPT-5.5" : "Claude Opus 5.5"} in{" "}
                {(t.reply.latency_ms / 1000).toFixed(1)} s
              </p>
              <p className="mt-1 line-clamp-2 text-sm font-medium" title={t.question}>
                {t.question}
              </p>
              <ul className="mt-2 space-y-1.5">
                {stepsFor(t).map((s, j) => (
                  <li
                    key={j}
                    className={cn(
                      "flex gap-2 text-sm",
                      s.tone === "verified" && "text-verified",
                      s.tone === "amber" && "text-[#8a5a10]",
                      s.tone === "muted" && "text-muted-foreground",
                    )}
                  >
                    <s.icon className="mt-0.5 size-4 shrink-0" aria-hidden />
                    <span>{s.text}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
