"use client";

import React, { useState, useRef, useEffect } from "react";

interface ToolAction {
  tool: string;
  input: any;
  result: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  tokens?: number;
  actions?: ToolAction[];
}

const SUGGESTED_QUESTIONS = [
  "What should I buy right now from my watchlist and why?",
  "Which stock has the highest conviction setup?",
  "Am I too concentrated in semiconductors?",
  "Give me a deep-dive on LITE — all signals, targets, and risks.",
  "What happens to my portfolio if the Fed raises rates 100bp?",
  "Which stocks have triggered or warning kill conditions?",
  "Rank my watchlist by risk-adjusted upside.",
  "What are the biggest catalysts coming up across my portfolio?",
];

const TOOL_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  run_scout:          { label: "Ran Scout",         icon: "🔍", color: "#3b82f6" },
  regenerate_model:   { label: "Regenerated Model", icon: "🔄", color: "#8b5cf6" },
  what_if_scenario:   { label: "What-If Scenario",  icon: "📊", color: "#f59e0b" },
  search_stocks:      { label: "Searched Stocks",   icon: "🔎", color: "#10b981" },
  add_to_watchlist:   { label: "Added to Watchlist", icon: "➕", color: "#06b6d4" },
  get_portfolio_summary: { label: "Loaded Portfolio", icon: "📋", color: "#6b7280" },
};

export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("sr-theme") : null;
    if (saved === "light") {
      setTheme("light");
      document.documentElement.setAttribute("data-theme", "light");
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendQuestion = async (question: string) => {
    if (!question.trim() || loading) return;

    const userMsg: Message = { role: "user", content: question.trim(), timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const history = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }));
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim(), conversationHistory: history.slice(0, -1) }),
      });
      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Failed to get response");
        setLoading(false);
        return;
      }

      const assistantMsg: Message = {
        role: "assistant",
        content: data.answer,
        timestamp: new Date(),
        tokens: data.tokens_used,
        actions: data.actions || undefined,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      setError(err.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuestion(input);
    }
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next === "dark" ? "" : "light");
    window.localStorage.setItem("sr-theme", next);
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-[var(--border)] bg-[var(--bg)]">
        <div className="max-w-[900px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3">
              <a href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                <div className="w-8 h-8 rounded-lg bg-[var(--text)] flex items-center justify-center text-sm font-bold text-[var(--bg)]">SR</div>
                <div>
                  <h1 className="text-lg font-bold">Stock Radar</h1>
                  <p className="text-[10px] text-[var(--muted)]">Multi-AI Agent System</p>
                </div>
              </a>
            </div>
            <nav className="flex gap-4 text-xs ml-4">
              <a href="/" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Watchlist</a>
              <a href="/discovery" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Discovery</a>
              <a href="/model" className="text-[var(--muted)] hover:text-[var(--text)] transition-colors">Models</a>
              <span className="text-amber-500 font-medium">Ask AI</span>
            </nav>
          </div>
          <button
            onClick={toggleTheme}
            className="text-[var(--muted)] hover:text-[var(--text)] transition-colors p-1.5 rounded-md hover:bg-[var(--hover)]"
          >
            {theme === "dark" ? (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.5"/><path d="M8 1.5v1M8 13.5v1M1.5 8h1M13.5 8h1M3.4 3.4l.7.7M11.9 11.9l.7.7M3.4 12.6l.7-.7M11.9 4.1l.7-.7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M13.5 9.2A5.5 5.5 0 016.8 2.5a6 6 0 106.7 6.7z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            )}
          </button>
        </div>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[900px] mx-auto px-6 py-6">
          {messages.length === 0 ? (
            /* Empty state with suggestions */
            <div className="flex flex-col items-center justify-center min-h-[60vh]">
              <div className="text-center mb-8">
                <div className="w-16 h-16 rounded-2xl bg-[var(--hover)] flex items-center justify-center mx-auto mb-4">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M16 4C9.373 4 4 9.373 4 16s5.373 12 12 12 12-5.373 12-12S22.627 4 16 4z" stroke="currentColor" strokeWidth="1.5" fill="none" className="text-[var(--muted)]"/>
                    <path d="M12 15h8M12 19h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-[var(--secondary)]"/>
                    <circle cx="16" cy="11" r="1.5" fill="currentColor" className="text-[var(--secondary)]"/>
                  </svg>
                </div>
                <h2 className="text-xl font-bold text-[var(--text)] mb-2">Ask your portfolio anything</h2>
                <p className="text-sm text-[var(--muted)] max-w-md">
                  Get buy/sell recommendations, deep-dives on any stock, portfolio risk analysis, and what-if scenario modeling — all powered by your live signal data.
                </p>
                <div className="flex items-center gap-2 justify-center mt-3">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 text-[10px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400" /> Can run scouts
                  </span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 text-[10px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-400" /> Can regenerate models
                  </span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-[10px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> What-if scenarios
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 max-w-[700px] w-full">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendQuestion(q)}
                    className="text-left px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--hover)] hover:border-[var(--border-hover)] transition-all text-xs text-[var(--secondary)] leading-relaxed"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Message history */
            <div className="space-y-6">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-5 py-3 ${
                      msg.role === "user"
                        ? "bg-[var(--text)] text-[var(--bg)] rounded-br-md"
                        : "bg-[var(--card)] border border-[var(--border)] rounded-bl-md"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose-sm">
                        {/* Action indicators */}
                        {msg.actions && msg.actions.length > 0 && (
                          <ActionBadges actions={msg.actions} />
                        )}
                        <MarkdownContent content={msg.content} />
                        {msg.tokens && (
                          <div className="mt-2 pt-2 border-t border-[var(--border)] text-[9px] text-[var(--faint)] flex items-center justify-between">
                            <span>{msg.tokens.toLocaleString()} tokens</span>
                            {msg.actions && msg.actions.length > 0 && (
                              <span>{msg.actions.length} action{msg.actions.length > 1 ? "s" : ""} taken</span>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className="bg-[var(--card)] border border-[var(--border)] rounded-2xl rounded-bl-md px-5 py-3">
                    <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-[var(--muted)] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                        <span className="w-2 h-2 bg-[var(--muted)] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                        <span className="w-2 h-2 bg-[var(--muted)] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                      </div>
                      Analyzing — may run scouts or models...
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="max-w-[900px] mx-auto px-6 mb-2">
          <div className="px-4 py-2 rounded-lg border bg-red-500/10 border-red-500/20 flex items-center justify-between">
            <span className="text-xs text-red-400">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300 text-xs px-2">Dismiss</button>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-[var(--border)] bg-[var(--bg)]">
        <div className="max-w-[900px] mx-auto px-6 py-4">
          <div className="flex gap-3 items-end">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your portfolio, run scouts, test scenarios..."
                rows={1}
                className="w-full px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--card)] text-sm text-[var(--text)] placeholder:text-[var(--muted)] resize-none outline-none focus:border-[var(--border-hover)] transition-colors"
                style={{ minHeight: "44px", maxHeight: "120px" }}
                onInput={(e) => {
                  const t = e.target as HTMLTextAreaElement;
                  t.style.height = "auto";
                  t.style.height = Math.min(t.scrollHeight, 120) + "px";
                }}
                disabled={loading}
              />
            </div>
            <button
              onClick={() => sendQuestion(input)}
              disabled={!input.trim() || loading}
              className="px-4 py-3 rounded-xl bg-[var(--text)] text-[var(--bg)] text-sm font-medium disabled:opacity-30 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M14 2L7 9M14 2l-4.5 12-2-5.5L2 6.5 14 2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
          <p className="text-[9px] text-[var(--faint)] mt-2 text-center">
            Agent mode — can run scouts, regenerate models, and test what-if scenarios. Each question costs ~2-8K tokens.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ─── Action badges (shows which tools the AI used) ─── */
function ActionBadges({ actions }: { actions: ToolAction[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="mb-3 pb-2 border-b border-[var(--border)]">
      <div className="flex flex-wrap gap-1.5 mb-1">
        {actions.map((action, i) => {
          const meta = TOOL_LABELS[action.tool] || { label: action.tool, icon: "⚙️", color: "#6b7280" };
          const toolInput = formatToolInput(action);
          return (
            <button
              key={i}
              onClick={() => setExpanded(expanded === i ? null : i)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-all hover:brightness-110 cursor-pointer"
              style={{
                backgroundColor: meta.color + "18",
                color: meta.color,
                border: `1px solid ${meta.color}30`,
              }}
            >
              <span>{meta.icon}</span>
              <span>{meta.label}</span>
              {toolInput && <span className="opacity-70">({toolInput})</span>}
              <svg
                width="8" height="8" viewBox="0 0 8 8"
                className={`ml-0.5 transition-transform ${expanded === i ? "rotate-180" : ""}`}
              >
                <path d="M2 3l2 2 2-2" stroke="currentColor" strokeWidth="1" fill="none" strokeLinecap="round" />
              </svg>
            </button>
          );
        })}
      </div>
      {expanded !== null && actions[expanded] && (
        <div
          className="mt-1.5 px-3 py-2 rounded-md text-[10px] font-mono leading-relaxed overflow-x-auto"
          style={{
            backgroundColor: (TOOL_LABELS[actions[expanded].tool]?.color || "#6b7280") + "0a",
            border: `1px solid ${(TOOL_LABELS[actions[expanded].tool]?.color || "#6b7280")}20`,
            color: "var(--secondary)",
          }}
        >
          <div className="mb-1 font-sans font-medium text-[var(--muted)]">Input:</div>
          <pre className="whitespace-pre-wrap break-words">{JSON.stringify(actions[expanded].input, null, 2)}</pre>
          <div className="mt-2 mb-1 font-sans font-medium text-[var(--muted)]">Result (preview):</div>
          <pre className="whitespace-pre-wrap break-words">{actions[expanded].result.slice(0, 400)}{actions[expanded].result.length > 400 ? "..." : ""}</pre>
        </div>
      )}
    </div>
  );
}

function formatToolInput(action: ToolAction): string {
  const inp = action.input;
  switch (action.tool) {
    case "run_scout":
      return `${inp.scout}${inp.ticker ? ` → ${inp.ticker}` : ""}`;
    case "regenerate_model":
      return inp.ticker || "";
    case "what_if_scenario":
      return inp.ticker || "";
    case "search_stocks":
      return inp.query || "";
    case "add_to_watchlist":
      return inp.ticker || "";
    default:
      return "";
  }
}

/* ─── Simple markdown renderer ─── */
function MarkdownContent({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: React.JSX.Element[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Headers
    if (line.startsWith("### ")) {
      elements.push(<h3 key={i} className="text-sm font-bold text-[var(--text)] mt-3 mb-1">{line.slice(4)}</h3>);
    } else if (line.startsWith("## ")) {
      elements.push(<h2 key={i} className="text-base font-bold text-[var(--text)] mt-4 mb-1.5">{line.slice(3)}</h2>);
    } else if (line.startsWith("# ")) {
      elements.push(<h1 key={i} className="text-lg font-bold text-[var(--text)] mt-4 mb-2">{line.slice(2)}</h1>);
    }
    // Bullet lists
    else if (line.match(/^[-*] /)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^[-*] /)) {
        items.push(lines[i].replace(/^[-*] /, ""));
        i++;
      }
      elements.push(
        <ul key={`ul-${i}`} className="list-disc list-inside space-y-0.5 text-sm text-[var(--secondary)] my-1">
          {items.map((item, j) => <li key={j}><InlineMarkdown text={item} /></li>)}
        </ul>
      );
      continue;
    }
    // Numbered lists
    else if (line.match(/^\d+\. /)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\d+\. /)) {
        items.push(lines[i].replace(/^\d+\. /, ""));
        i++;
      }
      elements.push(
        <ol key={`ol-${i}`} className="list-decimal list-inside space-y-0.5 text-sm text-[var(--secondary)] my-1">
          {items.map((item, j) => <li key={j}><InlineMarkdown text={item} /></li>)}
        </ol>
      );
      continue;
    }
    // Horizontal rule
    else if (line.match(/^---+$/)) {
      elements.push(<hr key={i} className="border-[var(--border)] my-3" />);
    }
    // Empty line
    else if (!line.trim()) {
      elements.push(<div key={i} className="h-2" />);
    }
    // Normal paragraph
    else {
      elements.push(<p key={i} className="text-sm text-[var(--secondary)] leading-relaxed"><InlineMarkdown text={line} /></p>);
    }

    i++;
  }

  return <div>{elements}</div>;
}

function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={i} className="font-semibold text-[var(--text)]">{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("*") && part.endsWith("*")) {
          return <em key={i}>{part.slice(1, -1)}</em>;
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return <code key={i} className="px-1 py-0.5 rounded bg-[var(--hover)] text-[var(--text)] text-[11px] font-mono">{part.slice(1, -1)}</code>;
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}
