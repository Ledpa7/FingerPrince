"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { RealtimePostgresInsertPayload } from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "@/lib/supabase-browser";

type CommandRow = {
  id: string;
  user_id: string;
  command_text: string;
  status: "pending" | "processing" | "completed" | "error";
  response_log: string | null;
  image_url: string | null;
  created_at: string;
};

const quickActions = [
  { label: "Status Check", command: "/sh whoami" },
  { label: "Screen Capture", command: "/capture" },
  { label: "Open VS Code", command: "/open vscode" },
  { label: "IDE Status", command: "/ide status" },
  { label: "IDE Debug Screen", command: "/ide debug screen" },
  { label: "Locate Input", command: "/ide debug locate input" },
  { label: "Locate Output", command: "/ide debug locate output" },
  { label: "Learn Input", command: "/ide learn input" },
  { label: "Learn Output", command: "/ide learn output" },
];

export function ChatClient() {
  const [userId, setUserId] = useState<string | null>(null);
  const [commands, setCommands] = useState<CommandRow[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authDebug, setAuthDebug] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const sortedCommands = useMemo(
    () => [...commands].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    [commands],
  );

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Ignore registration errors in unsupported/private contexts.
      });
    }
  }, []);

  useEffect(() => {
    let active = true;
    const maybeClient = getSupabaseBrowserClient();

    if (!maybeClient) {
      setError("NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY가 필요합니다.");
      return;
    }
    const client = maybeClient;

    async function initAuthAndData() {
      try {
        const sessionResult = await client.auth.getSession();
        let currentUserId = sessionResult.data.session?.user?.id ?? null;
        setAuthDebug(
          [
            `getSession: user=${currentUserId ? "yes" : "no"}`,
            `sessionError=${sessionResult.error?.message ?? "none"}`,
          ].join(" | "),
        );

        if (!currentUserId) {
          const signInResult = await client.auth.signInAnonymously();
          currentUserId = signInResult.data.user?.id ?? null;
          setAuthDebug((prev) =>
            [
              prev ?? "",
              `signInAnonymously: user=${currentUserId ? "yes" : "no"}`,
              `anonError=${signInResult.error?.message ?? "none"}`,
            ]
              .filter(Boolean)
              .join(" | "),
          );
        }

        if (!currentUserId) {
          currentUserId = process.env.NEXT_PUBLIC_DEMO_USER_ID || null;
          setAuthDebug((prev) =>
            [
              prev ?? "",
              `fallback DEMO_USER_ID: ${currentUserId ? "yes" : "no"}`,
            ]
              .filter(Boolean)
              .join(" | "),
          );
        }

        if (!active) {
          return;
        }

        if (!currentUserId) {
          setError(
            "사용자 인증에 실패했습니다. Supabase Anonymous Auth(및 Captcha 설정) 또는 DEMO_USER_ID를 확인하세요.",
          );
          return;
        }

        setUserId(currentUserId);

        const initial = await client
          .from("commands")
          .select("id,user_id,command_text,status,response_log,image_url,created_at")
          .eq("user_id", currentUserId)
          .order("created_at", { ascending: true })
          .limit(100);

        if (initial.error) {
          setError(initial.error.message);
        } else {
          setCommands((initial.data as CommandRow[]) ?? []);
        }

        // Fallback refresh: if Realtime isn't configured, keep UI in sync via periodic fetch.
        const refreshTimer = window.setInterval(async () => {
          const latest = await client
            .from("commands")
            .select("id,user_id,command_text,status,response_log,image_url,created_at")
            .eq("user_id", currentUserId)
            .order("created_at", { ascending: true })
            .limit(100);

          if (!latest.error) {
            setCommands((latest.data as CommandRow[]) ?? []);
          }
        }, 2000);

        const channel = client
          .channel(`commands-${currentUserId}`)
          .on(
            "postgres_changes",
            {
              event: "INSERT",
              schema: "public",
              table: "commands",
              filter: `user_id=eq.${currentUserId}`,
            },
            (payload: RealtimePostgresInsertPayload<CommandRow>) => {
              const row = payload.new;
              setCommands((prev) => {
                if (prev.some((it) => it.id === row.id)) {
                  return prev;
                }
                return [...prev, row];
              });
            },
          )
          .on(
            "postgres_changes",
            {
              event: "UPDATE",
              schema: "public",
              table: "commands",
              filter: `user_id=eq.${currentUserId}`,
            },
            (payload) => {
              const row = payload.new as CommandRow;
              setCommands((prev) => prev.map((it) => (it.id === row.id ? row : it)));
            },
          )
          .subscribe();

        return () => {
          window.clearInterval(refreshTimer);
          client.removeChannel(channel);
        };
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(`초기화 실패: ${msg}`);
        setAuthDebug((prev) => [prev ?? "", `exception=${msg}`].filter(Boolean).join(" | "));
      }
    }

    const cleanupPromise = initAuthAndData();

    return () => {
      active = false;
      cleanupPromise.then((cleanup) => {
        if (typeof cleanup === "function") {
          cleanup();
        }
      });
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sortedCommands]);

  async function sendCommand(rawText: string) {
    const commandText = rawText.trim();
    if (!commandText || !userId) {
      return;
    }
    const client = getSupabaseBrowserClient();
    if (!client) {
      setError("Supabase 환경변수가 설정되지 않았습니다.");
      return;
    }

    setSending(true);
    setError(null);

    const result = await client.from("commands").insert({
      user_id: userId,
      command_text: commandText,
      status: "pending",
    });

    if (result.error) {
      setError(result.error.message);
    } else {
      setInput("");
    }

    setSending(false);
  }

  async function resetSession() {
    const client = getSupabaseBrowserClient();
    if (!client) {
      return;
    }
    setError(null);
    setAuthDebug(null);
    setUserId(null);
    setCommands([]);
    await client.auth.signOut();
    window.location.reload();
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await sendCommand(input);
  }

  return (
    <main className="mx-auto flex h-[min(100dvh,820px)] w-[min(100%,390px)] flex-col overflow-hidden rounded-[32px] border border-[var(--line)] bg-[color-mix(in_srgb,var(--panel)_70%,transparent)] px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-[max(0.75rem,env(safe-area-inset-top))] shadow-2xl">
      <header className="rounded-3xl border border-[var(--line)] bg-[var(--panel)] px-4 py-3 shadow-bubble backdrop-blur">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-brand-slate">SERVER VIBE</p>
            <h1 className="text-lg font-semibold">Mobile Commander</h1>
          </div>
          <Link
            href="https://remotedesktop.google.com/access/"
            target="_blank"
            className="rounded-full bg-brand-ink px-3 py-2 text-xs font-semibold text-white transition hover:opacity-90"
          >
            원격 접속
          </Link>
        </div>
      </header>

      <section className="mt-3 flex gap-2 overflow-x-auto pb-1">
        {quickActions.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => sendCommand(action.command)}
            className="shrink-0 rounded-full border border-[var(--line)] bg-white/85 px-3 py-2 text-xs font-medium text-brand-ink shadow-sm transition hover:bg-white"
          >
            {action.label}
          </button>
        ))}
      </section>

      <section className="mt-3 min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-3xl border border-[var(--line)] bg-white/70 p-3 shadow-bubble backdrop-blur">
        {sortedCommands.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--line)] bg-white/60 p-4 text-sm text-[var(--muted)]">
            첫 명령을 보내서 PC를 제어해보세요.
          </div>
        ) : (
          <div className="space-y-3">
            {sortedCommands.map((item) => (
              <article key={item.id} className="space-y-2 animate-floatIn">
                <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-brand-ink px-3 py-2 text-sm text-white shadow-sm">
                  {item.command_text}
                </div>

                <div className="w-fit max-w-[92%] rounded-2xl rounded-bl-md border border-[var(--line)] bg-brand-paper px-3 py-2 text-sm text-brand-ink shadow-sm">
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-slate">
                    {item.status}
                  </p>
                  {item.response_log ? <pre className="whitespace-pre-wrap text-xs leading-5">{item.response_log}</pre> : null}
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt="Captured screen"
                      className="mt-2 max-h-[40vh] w-full rounded-xl border border-[var(--line)] object-contain"
                    />
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </section>

      {error ? (
        <div className="mt-2 space-y-2 rounded-xl bg-red-100 px-3 py-2 text-xs text-red-700">
          <p>{error}</p>
          {authDebug ? <p className="text-[11px] text-red-600/90">debug: {authDebug}</p> : null}
          <button
            type="button"
            onClick={resetSession}
            className="rounded-lg border border-red-200 bg-white px-2 py-1 text-[11px] font-semibold text-red-700"
          >
            세션 초기화
          </button>
        </div>
      ) : null}

      <form onSubmit={onSubmit} className="mt-3 flex gap-2 rounded-2xl border border-[var(--line)] bg-white px-2 py-2 shadow-bubble">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="대화/명령 입력... (쉘은 /sh whoami 처럼)"
          className="h-10 flex-1 rounded-xl border border-transparent px-3 text-sm outline-none focus:border-brand-sky"
        />
        <button
          type="submit"
          disabled={sending || !input.trim() || !userId}
          className="h-10 rounded-xl bg-brand-ink px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          전송
        </button>
      </form>
    </main>
  );
}

