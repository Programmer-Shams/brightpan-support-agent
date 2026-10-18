import { Fragment, type ReactNode } from "react";
import { BookOpen, PackageCheck, UserRound } from "lucide-react";
import type { AgentReply, Order } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Minimal rendering for agent replies: paragraphs, "-" / "1." lists and **bold**. */
export function AnswerText({ text, hideSourceLine }: { text: string; hideSourceLine?: boolean }) {
  // When source tags are shown, drop the trailing "(Source: …)" line they duplicate.
  const body = hideSourceLine ? text.replace(/\(Source:[^()]*(?:\([^()]*\)[^()]*)*\)\s*$/, "") : text;
  const blocks = body.trim().split(/\n{2,}/);
  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-foreground">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        const bullet = lines.every((l) => /^\s*[-•]\s+/.test(l));
        const numbered = lines.every((l) => /^\s*\d+[.)]\s+/.test(l));
        if (bullet || numbered) {
          const List = numbered ? "ol" : "ul";
          return (
            <List key={i} className={cn("space-y-1.5 pl-5", numbered ? "list-decimal" : "list-disc")}>
              {lines.map((l, j) => (
                <li key={j} className="pl-1 marker:text-muted-foreground">
                  {inline(l.replace(/^\s*(?:[-•]|\d+[.)])\s+/, ""))}
                </li>
              ))}
            </List>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

export function SourceTags({ sources }: { sources: AgentReply["sources"] }) {
  if (!sources.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 pt-1">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <BookOpen className="size-3.5" aria-hidden />
        From the help center
      </span>
      {sources.map((s) => (
        <span
          key={s.id}
          className="rounded-full border border-enamel/25 bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-foreground"
        >
          {s.title}
        </span>
      ))}
    </div>
  );
}

const STATUS_COPY: Record<string, string> = {
  fulfilled: "Shipped",
  partially_fulfilled: "Partly shipped",
  unfulfilled: "Being prepared",
  cancelled: "Cancelled",
};

function prettyDate(iso: string | null) {
  if (!iso) return null;
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function OrderCard({ order }: { order: Order }) {
  const status = order.cancelled
    ? "Cancelled"
    : order.delivered
      ? "Delivered"
      : (STATUS_COPY[order.status] ?? order.status);
  const payment = order.payment === "PAID" ? null : order.payment.charAt(0) + order.payment.slice(1).toLowerCase();
  const facts: [string, string | null][] = [
    ["Placed", prettyDate(order.placed)],
    ["Shipped", prettyDate(order.shipped)],
    ["Delivered", prettyDate(order.delivered)],
    ["Carrier", order.carrier],
    ["Tracking", order.tracking],
    ["Total", order.total],
    ["Payment", payment],
  ];
  return (
    <section
      aria-label={`Order ${order.number}`}
      className="max-w-md overflow-hidden rounded-md border border-verified/30 bg-card"
    >
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 bg-verified-soft px-4 py-2.5">
        <span className="flex items-center gap-2">
          <PackageCheck className="size-4 text-verified" aria-hidden />
          <span className="text-sm font-semibold">Order {order.number}</span>
          <span className="text-xs whitespace-nowrap text-verified">Email verified</span>
        </span>
        <span className="text-sm font-semibold text-foreground">{status}</span>
      </header>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:grid-cols-3">
        {facts
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className={cn("min-w-0", k === "Tracking" && "col-span-2")}>
              <dt className="text-xs text-muted-foreground">{k}</dt>
              <dd className="font-medium break-all">{v}</dd>
            </div>
          ))}
      </dl>
      <ul className="border-t border-border/70 px-4 py-2.5 text-sm">
        {order.items.map((item, i) => (
          <li key={i} className="flex items-baseline justify-between gap-4 py-0.5">
            <span className="min-w-0">
              {item.qty} × {item.title}
              {item.status && (
                <span className="block text-xs text-muted-foreground">
                  {item.status.replace(/\d{4}-\d{2}-\d{2}/g, (d) => prettyDate(d) ?? d)}
                </span>
              )}
            </span>
            <span className="shrink-0 text-muted-foreground">{item.price}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function HandoffBanner({ id, verified }: { id: number | null; verified: boolean | null }) {
  return (
    <div
      role="status"
      className="flex max-w-md items-start gap-3 rounded-md border border-amber/50 bg-amber-soft px-4 py-3 text-sm"
    >
      <UserRound className="mt-0.5 size-4 shrink-0 text-[#9a6514]" aria-hidden />
      <p>
        <span className="font-semibold">Passed to the support team{id ? ` (ticket #${id})` : ""}.</span>{" "}
        A person replies by email within 1 business day, Monday to Friday, 9 am–6 pm ET.
        {verified === false && (
          <span className="mt-1 block text-xs text-muted-foreground">
            The team will confirm your order details before acting on this.
          </span>
        )}
      </p>
    </div>
  );
}
