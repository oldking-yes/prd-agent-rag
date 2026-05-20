"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  CheckCircle,
  CreditCard,
  Database,
  List,
  MessageSquare,
  Search,
  Star,
  XCircle,
} from "lucide-react";
import { OnboardingBanner } from "@/components/dashboard/onboarding-banner";
import { QuickActions } from "@/components/dashboard/quick-actions";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { StatCard } from "@/components/dashboard/stat-card";
import { useAuth } from "@/hooks";
import { apiClient } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { listCollections, getCollectionInfo } from "@/lib/rag-api";
import type { HealthResponse } from "@/types";

interface ConversationsResponse {
  total?: number;
  items: Array<{ id: string }>;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [conversations, setConversations] = useState<{ total: number } | null>(null);
  const [convLoading, setConvLoading] = useState(true);
  const [ragStats, setRagStats] = useState<{ collections: number; vectors: number } | null>(null);

  useEffect(() => {
    apiClient
      .get<HealthResponse>("/health")
      .then((d) => {
        setHealth(d);
        setHealthError(false);
      })
      .catch(() => setHealthError(true));

    apiClient
      .get<ConversationsResponse>("/conversations?limit=1")
      .then((d) => setConversations({ total: d.total ?? d.items?.length ?? 0 }))
      .catch(() => setConversations({ total: 0 }))
      .finally(() => setConvLoading(false));
    listCollections()
      .then(async (list) => {
        let totalVectors = 0;
        for (const name of list.items) {
          try {
            const info = await getCollectionInfo(name);
            totalVectors += info.total_vectors;
          } catch {
            /* ignore */
          }
        }
        setRagStats({ collections: list.items.length, vectors: totalVectors });
      })
      .catch(() => setRagStats({ collections: 0, vectors: 0 }));
  }, []);

  return (
    <div className="space-y-6 pb-8">
      <OnboardingBanner />

      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-foreground/55 font-mono text-[11px] tracking-wider uppercase">
            Dashboard
          </p>
          <h1 className="font-display text-foreground mt-1 text-3xl font-bold tracking-tight sm:text-4xl">
            {getGreeting()}
            {user?.full_name
              ? `, ${user.full_name.split(" ")[0]}`
              : user?.email
                ? `, ${user.email.split("@")[0]}`
                : ""}
            <span className="text-foreground/30">.</span>
          </h1>
          <p className="text-foreground/65 mt-1 text-sm">
            Here&apos;s what&apos;s happening with your workspace.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <SearchHint />
          <Link
            href={ROUTES.CHAT}
            className="bg-foreground text-background hover:bg-foreground/90 inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors"
          >
            <MessageSquare className="h-4 w-4" />
            New chat
          </Link>
        </div>
      </div>

      {/* Stat cards */}
      <div className="flex items-center justify-between">
        <h2 className="text-foreground/55 font-mono text-[11px] tracking-wider uppercase">
          Workspace metrics
        </h2>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Conversations"
          value={convLoading ? "—" : (conversations?.total ?? 0).toLocaleString()}
          icon={MessageSquare}
          loading={convLoading}
        />
        <StatCard
          label="Knowledge base"
          value={ragStats ? ragStats.vectors.toLocaleString() : "—"}
          unit={ragStats ? `vector${ragStats.vectors === 1 ? "" : "s"}` : undefined}
          icon={Database}
          loading={!ragStats}
        />
      </div>

      {/* Status strip */}
      <div className="border-border bg-card flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border px-5 py-3 text-xs">
        <span className="inline-flex items-center gap-2">
          {healthError ? (
            <>
              <XCircle className="text-destructive h-4 w-4" />
              <span className="text-destructive font-mono tracking-wider uppercase">
                API offline
              </span>
            </>
          ) : (
            <>
              <CheckCircle className="text-brand h-4 w-4" />
              <span className="text-foreground/70 font-mono tracking-wider uppercase">
                {health?.status || "Operational"}
              </span>
            </>
          )}
        </span>
        {health?.version && (
          <span className="text-foreground/45 font-mono tracking-wider uppercase">
            v{health.version}
          </span>
        )}
        <span className="text-foreground/45 font-mono tracking-wider uppercase">
          {ragStats
            ? `${ragStats.collections} collection${ragStats.collections === 1 ? "" : "s"}`
            : "—"}
        </span>
        <Link
          href={ROUTES.BILLING}
          className="text-foreground/55 hover:text-foreground ml-auto inline-flex items-center gap-1 font-mono tracking-wider uppercase"
        >
          <CreditCard className="h-3.5 w-3.5" />
          Manage billing →
        </Link>
      </div>

      {/* Activity + behavior insights */}
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <RecentActivity />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
      </div>

      <QuickActions />

      {/* Admin row */}
      {user?.role === "admin" && (
        <div>
          <h2 className="font-display text-foreground mb-3 text-base font-semibold">
            Admin actions
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <AdminTile
              icon={Star}
              label="Response ratings"
              description="View and manage ratings"
              href={ROUTES.ADMIN_RATINGS}
            />
            <AdminTile
              icon={List}
              label="All conversations"
              description="Inspect any user's chats"
              href={ROUTES.ADMIN_CONVERSATIONS}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function SearchHint() {
  return (
    <div className="border-foreground/15 bg-background hidden items-center gap-2 rounded-full border px-3 py-1.5 text-xs sm:inline-flex">
      <Search className="text-foreground/45 h-3.5 w-3.5" />
      <span className="text-foreground/55">Search</span>
      <kbd className="border-foreground/15 bg-card text-foreground/65 rounded-md border px-1.5 py-0.5 font-mono text-[10px]">
        ⌘K
      </kbd>
    </div>
  );
}

function AdminTile({
  icon: Icon,
  label,
  description,
  href,
}: {
  icon: typeof Star;
  label: string;
  description: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="lift border-border hover:border-foreground/30 bg-card flex items-center gap-3 rounded-2xl border p-4 transition-colors"
    >
      <span className="bg-foreground/8 text-foreground flex h-9 w-9 items-center justify-center rounded-full">
        <Icon className="h-4 w-4" />
      </span>
      <div className="flex-1">
        <p className="text-foreground text-sm font-semibold">{label}</p>
        <p className="text-foreground/55 text-xs">{description}</p>
      </div>
    </Link>
  );
}
