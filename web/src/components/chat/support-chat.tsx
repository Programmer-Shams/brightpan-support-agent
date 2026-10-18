"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUp, ListTree, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { MAX_MESSAGE, MODELS, toAgentReply, type AgentReply, type ChatMessage, type ModelKey } from "@/lib/types";
import { AnswerText, HandoffBanner, OrderCard, SourceTags } from "./message-parts";
import { TracePanel } from "./trace-panel";
import { BrandMark } from "./brand-mark";

const STARTERS = [
  "How much is standard shipping?",
  "Where is order 1002? My email is maria.lopez@example.com",
  "Can I return a knife I've used once?",
  "My kettle from order 1012 arrived with a cracked lid. Email tom.walsh@example.com",
];

const newSession = () => `web-${crypto.randomUUID()}`;

export function SupportChat() {
  const [model, setModel] = useState<ModelKey>("claude");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Created on first send (not during render) and replaced by "New conversation".
  const sessionRef = useRef<string | null>(null);

  useEffect(() => {
    // Block body: scrollIntoView returns a Promise in newer browsers, and effects must not return one.
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  function reset(nextModel: ModelKey = model) {
    setModel(nextModel);
    setMessages([]);
    sessionRef.current = null;
    inputRef.current?.focus();
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    setDraft("");
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", text: question }]);
    setPending(true);
    sessionRef.current ??= newSession();
    const fail = (text: string, detail?: string) =>
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "error", text, detail, question }]);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, session_id: sessionRef.current, model }),
      });
      let data: Partial<AgentReply> & { error?: unknown };
      try {
        data = JSON.parse(await res.text());
      } catch {
        fail("The message wasn't answered.", `The app's server sent an unreadable reply (HTTP ${res.status}).`);
        return;
      }
      if (!res.ok) {
        fail("The message wasn't answered.", typeof data.error === "string" ? data.error : `HTTP ${res.status}.`);
        return;
      }
      const reply = toAgentReply(data);
      if (reply.error) {
        // The workflow's error branch: show its apology as an error the customer can retry.
        fail(reply.answer || "Something went wrong.", "The support team has been told about this error.");
        return;
      }
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", reply, question }]);
    } catch {
      fail("The message wasn't answered.", "The app's server couldn't be reached. Check that it's running.");
    } finally {
      setPending(false);
      inputRef.current?.focus();
    }
  }

  /** Remove the failed attempt (the question and its error card), then send the question again. */
  function retry(errorId: string, question: string) {
    setMessages((m) => {
      const i = m.findIndex((x) => x.id === errorId);
      if (i < 0) return m;
      const start = i > 0 && m[i - 1].role === "user" ? i - 1 : i;
      return [...m.slice(0, start), ...m.slice(i + 1)];
    });
    void send(question);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(draft);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send(draft);
    }
  }

  return (
    <div className="flex h-dvh flex-col">
      <header className="border-b border-steel-line bg-card">
        <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <BrandMark className="h-7 w-11 text-enamel" />
            <div className="leading-none">
              <p className="type-stamp text-xl font-extrabold tracking-tight">Brightpan</p>
              <p className="mt-1 hidden text-xs text-muted-foreground sm:block">Kitchen Supply customer support</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ModelToggle model={model} onChange={(k) => reset(k)} className="hidden sm:flex" />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => reset()}
              disabled={!messages.length || pending}
              aria-label="New conversation"
            >
              <RotateCcw data-icon="inline-start" aria-hidden />
              <span className="hidden sm:inline">New conversation</span>
            </Button>
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="lg:hidden">
                  <ListTree data-icon="inline-start" aria-hidden />
                  Steps
                </Button>
              </SheetTrigger>
              <SheetContent side="bottom" className="max-h-[80dvh] overflow-y-auto px-4 pb-8">
                <SheetHeader className="sr-only">
                  <SheetTitle>How each answer was made</SheetTitle>
                  <SheetDescription>Tools used for each reply</SheetDescription>
                </SheetHeader>
                <div className="pt-4 sm:hidden">
                  <p className="mb-2 text-sm font-medium">Model answering</p>
                  <ModelToggle model={model} onChange={(k) => reset(k)} />
                  <p className="mt-2 text-xs text-muted-foreground">Switching starts a new conversation.</p>
                </div>
                <TracePanel messages={messages} className="pt-4" />
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <div className="grid min-h-0 w-full flex-1 lg:grid-cols-[minmax(0,1fr)_380px]">
        <main className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite" aria-busy={pending}>
            <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
              {messages.length === 0 ? (
                <EmptyState onPick={(q) => void send(q)} model={model} />
              ) : (
                <div className="space-y-8">
                  {messages.map((m) => (
                    <MessageView key={m.id} message={m} onRetry={retry} />
                  ))}
                  {pending && <Working />}
                </div>
              )}
              <div ref={endRef} />
            </div>
          </div>

          <form onSubmit={onSubmit} className="border-t border-steel-line bg-steel/80 backdrop-blur">
            <div className="mx-auto max-w-3xl px-4 py-4 sm:px-6">
              <div className="flex items-end gap-2 rounded-xl border border-steel-line bg-card p-2 shadow-[0_1px_0_rgba(30,35,41,0.04)] focus-within:border-enamel focus-within:ring-3 focus-within:ring-enamel/15">
                <label htmlFor="chat-input" className="sr-only">
                  Message Brightpan support
                </label>
                <Textarea
                  id="chat-input"
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={1}
                  maxLength={MAX_MESSAGE}
                  placeholder="Ask about shipping, returns, care, or an order"
                  className="max-h-40 min-h-10 resize-none border-0 bg-transparent px-2 py-2 text-[15px] shadow-none focus-visible:ring-0"
                />
                <Button
                  type="submit"
                  size="icon-lg"
                  disabled={!draft.trim() || pending}
                  aria-label="Send message"
                  className="shrink-0 rounded-lg"
                >
                  <ArrowUp aria-hidden />
                </Button>
              </div>
              <p className="mt-2 px-1 text-xs text-muted-foreground">
                Answers come from the Brightpan help center. Refunds, damaged items and complaints go to a person.
              </p>
            </div>
          </form>
        </main>

        <aside className="hidden min-h-0 overflow-y-auto border-l border-steel-line bg-card/60 px-6 py-8 lg:block">
          <TracePanel messages={messages} />
        </aside>
      </div>
    </div>
  );
}

function EmptyState({ onPick, model }: { onPick: (q: string) => void; model: ModelKey }) {
  return (
    <div className="pt-6 sm:pt-14">
      <h1 className="type-stamp text-4xl leading-[1.05] font-extrabold tracking-tight sm:text-5xl">
        How can we help
        <br />
        in the kitchen today?
      </h1>
      <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
        Ask about shipping, returns, product care or an order. You get answers from our help center, with the
        article named, and a person takes over for refunds and damaged items.
      </p>
      <div className="mt-10">
        <p className="text-sm font-medium">Try a question</p>
        <ul className="mt-3 flex flex-col gap-2">
          {STARTERS.map((q) => (
            <li key={q}>
              <button
                type="button"
                onClick={() => onPick(q)}
                className="w-full rounded-lg border border-steel-line bg-card px-4 py-3 text-left text-sm transition-colors hover:border-enamel/60 hover:bg-accent focus-visible:ring-3 focus-visible:ring-enamel/30 focus-visible:outline-none"
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-6 text-xs text-muted-foreground">
          Answering with {MODELS[model].label}. Orders and customers are fictional demo data.
        </p>
      </div>
    </div>
  );
}

function MessageView({ message, onRetry }: { message: ChatMessage; onRetry: (id: string, q: string) => void }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-enamel px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-primary-foreground">
          {message.text}
        </p>
      </div>
    );
  }
  if (message.role === "error") {
    return (
      <div role="alert" className="rounded-md border border-destructive/30 bg-card px-4 py-3 text-sm">
        <p className="font-medium text-destructive">{message.text}</p>
        {message.detail && <p className="mt-1 text-muted-foreground">{message.detail}</p>}
        <Button variant="outline" size="sm" className="mt-3" onClick={() => onRetry(message.id, message.question)}>
          <RotateCcw data-icon="inline-start" aria-hidden />
          Send again
        </Button>
      </div>
    );
  }
  const r = message.reply;
  return (
    <div className="flex gap-3">
      <BrandMark className="mt-1 h-5 w-8 shrink-0 text-enamel" />
      <div className="min-w-0 flex-1 space-y-3">
        <AnswerText text={r.answer} hideSourceLine={r.sources.length > 0} />
        {r.order && <OrderCard order={r.order} />}
        {r.escalated && <HandoffBanner id={r.handoff_id} verified={r.handoff_verified} />}
        <SourceTags sources={r.sources} />
      </div>
    </div>
  );
}

function Working() {
  return (
    <div className="flex items-center gap-3 text-sm text-muted-foreground" role="status">
      <BrandMark className="h-5 w-8 shrink-0 animate-pulse text-enamel/70" />
      Checking the help center and your order details…
    </div>
  );
}

function ModelToggle({
  model,
  onChange,
  className,
}: {
  model: ModelKey;
  onChange: (k: ModelKey) => void;
  className?: string;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      spacing={0}
      value={model}
      aria-label="Model answering"
      onValueChange={(v) => v && v !== model && onChange(v as ModelKey)}
      className={className}
    >
      {(Object.keys(MODELS) as ModelKey[]).map((k) => (
        <ToggleGroupItem
          key={k}
          value={k}
          className="px-3 data-[state=on]:bg-enamel data-[state=on]:text-primary-foreground"
        >
          {MODELS[k].label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
