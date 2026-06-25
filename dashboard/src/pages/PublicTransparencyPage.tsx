import { CheckCircle, ReceiptText, ShieldCheck } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { usePublicTransparency } from '@/hooks/usePublicTransparency';
import { BrandMark } from '@/components/brand/BrandMark';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatDateShort, formatSats } from '@/lib/utils';
import { truncateMiddle } from '@/lib/transparency';
import type { PublicSplitMember } from '@/types/api';

const publicNodePositions = [
  { x: 50, y: 16 },
  { x: 78, y: 42 },
  { x: 63, y: 79 },
  { x: 24, y: 63 },
  { x: 25, y: 35 },
  { x: 50, y: 82 },
];

function publicLabel(member: PublicSplitMember) {
  if (member.label) return member.label;
  if (member.nostr_pubkey) return truncateMiddle(member.nostr_pubkey);
  return 'Public partner';
}

function PublicTeamMap({ members, name }: { members: PublicSplitMember[]; name: string }) {
  return (
    <div
      className="relative min-h-[320px] overflow-hidden rounded-lg border border-white/[0.08] bg-[#0A0B12]"
      style={{
        background:
          'radial-gradient(circle at 50% 50%, rgba(255,45,120,0.11), rgba(17,19,31,0.54) 33%, rgba(10,11,18,0.98) 74%)',
      }}
    >
      <div className="absolute left-1/2 top-1/2 h-[74%] w-[74%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.055]" />
      <div className="absolute left-1/2 top-1/2 h-[46%] w-[46%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#FF2D78]/12" />

      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {members.map((member, index) => {
          const node = publicNodePositions[index % publicNodePositions.length];

          return (
            <line
              key={member.nostr_pubkey || member.label || index}
              x1="50"
              y1="50"
              x2={node.x}
              y2={node.y}
              stroke="rgba(255,45,120,0.46)"
              strokeLinecap="round"
              strokeWidth={Math.max(0.45, member.percentage / 18)}
            />
          );
        })}
      </svg>

      <div className="absolute left-1/2 top-1/2 z-20 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border border-[#FF2D78]/32 bg-[#11131F] text-center shadow-[0_0_38px_rgba(255,45,120,0.18)]">
        <p className="px-3 text-sm font-semibold leading-4 text-[#F5F5F7]">{name}</p>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#94A3B8]">BTCPay</p>
      </div>

      {members.map((member, index) => {
        const node = publicNodePositions[index % publicNodePositions.length];
        const size = 46 + member.percentage * 0.78;

        return (
          <div
            key={member.nostr_pubkey || member.label || index}
            className="absolute z-30 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border border-white/[0.11] bg-[#11131F]/95 text-center shadow-[0_14px_32px_rgba(0,0,0,0.30)]"
            style={{
              left: `${node.x}%`,
              top: `${node.y}%`,
              width: size,
              height: size,
            }}
          >
            <span className="max-w-[74px] truncate px-2 text-[11px] font-semibold text-[#F5F5F7]">{publicLabel(member)}</span>
            <span className="mt-1 font-mono text-[11px] text-[#FF2D78]">{member.percentage}%</span>
          </div>
        );
      })}
    </div>
  );
}

export function PublicTransparencyPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, isLoading, isError } = usePublicTransparency(slug);

  return (
    <div
      className="public-proof-page min-h-screen bg-[#0A0B12] text-[#F5F5F7]"
      style={{
        background:
          'radial-gradient(circle at 22% 0%, rgba(255,45,120,0.11), transparent 28%), linear-gradient(180deg, #11131F 0%, #0A0B12 42%, #0A0B12 100%)',
      }}
    >
      <header className="border-b border-white/[0.06]">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <BrandMark size="sm" />
            <div>
              <p className="font-semibold text-[#F5F5F7]">{data?.name ?? 'OpenSplit'}</p>
              <p className="mt-1 font-mono text-xs text-[#94A3B8]">/public/{slug ?? 'workspace'}</p>
            </div>
          </div>

          <div className="hidden items-center gap-2 rounded-full border border-[#FF2D78]/20 bg-[#FF2D78]/[0.055] px-3 py-1.5 text-xs font-semibold text-[#F5F5F7] sm:inline-flex">
            <CheckCircle className="h-3.5 w-3.5 text-[#FF2D78]" strokeWidth={1.8} />
            Public proof
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
        {isLoading && (
          <div className="space-y-6">
            <Skeleton className="h-12 w-64" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-56 w-full" />
          </div>
        )}

        {(!slug || isError) && (
          <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
            <h1 className="text-3xl font-semibold text-[#F5F5F7]">Public page unavailable</h1>
            <p className="mt-3 max-w-md text-sm text-[#94A3B8]">
              This proof page is disabled, missing, or not published yet.
            </p>
          </div>
        )}

        {data && (
          <>
            <section className="grid gap-6 lg:grid-cols-[1.08fr_0.92fr]">
              <div className="rounded-lg border border-white/[0.08] bg-[#11131F]/62 p-5 shadow-[inset_0_1px_0_rgba(245,245,247,0.07)] sm:p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#FF2D78]">Public split proof</p>
                <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#F5F5F7] sm:text-4xl">
                  {data.name}
                </h1>
                <p className="mt-3 max-w-2xl text-base leading-7 text-[#94A3B8]">
                  Incoming Bitcoin payments are published as split proofs: clear percentages, public identities,
                  and no private wallet details.
                </p>

                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border border-white/[0.07] bg-[#0A0B12]/64 p-4">
                    <p className="text-xs text-[#94A3B8]">Active partners</p>
                    <p className="mt-2 font-mono text-sm font-semibold text-[#F5F5F7]">{data.distribution.length}</p>
                  </div>
                  <div className="rounded-lg border border-white/[0.07] bg-[#0A0B12]/64 p-4">
                    <p className="text-xs text-[#94A3B8]">Published payments</p>
                    <p className="mt-2 font-mono text-sm font-semibold text-[#F5F5F7]">{data.recent_payments.length}</p>
                  </div>
                  <div className="rounded-lg border border-white/[0.07] bg-[#0A0B12]/64 p-4">
                    <p className="text-xs text-[#94A3B8]">Total routed</p>
                    <p className="mt-2 font-mono text-sm font-semibold text-[#F5F5F7]">
                      {data.show_amounts && data.total_sats != null ? formatSats(data.total_sats) : 'redacted'}
                    </p>
                  </div>
                </div>
              </div>

              <aside className="rounded-lg border border-[#FF2D78]/18 bg-[#11131F]/72 p-5 shadow-[0_24px_70px_rgba(0,0,0,0.34),inset_0_1px_0_rgba(245,245,247,0.07)]">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[#FF2D78]/24 bg-[#FF2D78]/10">
                    <ReceiptText className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                  </div>
                  <div>
                    <p className="font-semibold text-[#F5F5F7]">Transparency status</p>
                    <p className="mt-1 text-xs text-[#94A3B8]">No private wallet data published</p>
                  </div>
                </div>

                <dl className="mt-6 space-y-3 text-sm">
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-[#94A3B8]">Amounts</dt>
                    <dd className="font-mono font-semibold text-[#F5F5F7]">{data.show_amounts ? 'public' : 'redacted'}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-[#94A3B8]">Split total</dt>
                    <dd className="font-mono font-semibold text-[#F5F5F7]">
                      {data.distribution.reduce((sum, member) => sum + member.percentage, 0)}%
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-[#94A3B8]">Route</dt>
                    <dd className="font-mono font-semibold text-[#F5F5F7]">/public/{data.slug}</dd>
                  </div>
                </dl>
              </aside>
            </section>

            <section className="grid gap-6 lg:grid-cols-[0.88fr_1.12fr]">
              <div className="rounded-lg border border-white/[0.08] bg-[#11131F]/56 p-5 shadow-[inset_0_1px_0_rgba(245,245,247,0.07)]">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#94A3B8]">Active split</p>
                    <h2 className="mt-2 text-xl font-semibold text-[#F5F5F7]">Published distribution</h2>
                  </div>
                  <ShieldCheck className="h-5 w-5 text-[#FF2D78]" strokeWidth={1.8} />
                </div>

                {!data.distribution.length ? (
                  <p className="mt-6 text-sm text-[#94A3B8]">No active split has been published.</p>
                ) : (
                  <div className="mt-6 space-y-4">
                    <div className="flex h-2 overflow-hidden rounded-full border border-white/[0.07] bg-[#0A0B12]/70">
                      {data.distribution.map((member, index) => (
                        <span
                          key={member.nostr_pubkey || member.label || index}
                          className="bg-[#FF2D78]"
                          style={{ width: `${member.percentage}%`, opacity: 1 - index * 0.12 }}
                        />
                      ))}
                    </div>
                    <div className="divide-y divide-white/[0.06]">
                      {data.distribution.map((member, index) => (
                        <div key={member.nostr_pubkey || member.label || index} className="flex items-center justify-between gap-4 py-3">
                          <div className="flex min-w-0 items-center gap-2">
                            <span className="h-2 w-2 shrink-0 rounded-full bg-[#FF2D78]" style={{ opacity: 1 - index * 0.12 }} />
                            <span className="truncate text-sm text-[#F5F5F7]">{publicLabel(member)}</span>
                          </div>
                          <span className="font-mono font-semibold text-[#F5F5F7]">{member.percentage}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-white/[0.08] bg-[#11131F]/56 p-3 shadow-[inset_0_1px_0_rgba(245,245,247,0.07)]">
                <PublicTeamMap members={data.distribution} name={data.name} />
              </div>
            </section>

            <section className="rounded-lg border border-white/[0.08] bg-[#11131F]/56 shadow-[inset_0_1px_0_rgba(245,245,247,0.07)]">
              <div className="flex items-center justify-between gap-4 border-b border-white/[0.06] p-5">
                <div>
                  <h2 className="font-semibold text-[#F5F5F7]">Recent payment proofs</h2>
                  <p className="mt-1 text-sm text-[#94A3B8]">Public amounts when enabled, verified split records always.</p>
                </div>
              </div>

              {!data.recent_payments.length ? (
                <p className="p-5 text-sm text-[#94A3B8]">No public payments yet.</p>
              ) : (
                <div className="divide-y divide-white/[0.06]">
                  {data.recent_payments.map((payment, index) => (
                    <div key={index} className="grid gap-4 p-5 sm:grid-cols-[1fr_auto] sm:items-center">
                      <div className="min-w-0">
                        <p className="font-mono text-base font-semibold text-[#F5F5F7]">
                          {data.show_amounts && payment.amount_sats != null ? formatSats(payment.amount_sats) : 'amount redacted'}
                        </p>
                        <p className="mt-1 font-mono text-xs text-[#94A3B8]">{formatDateShort(payment.paid_at)}</p>
                      </div>
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-[#FF2D78]/22 bg-[#FF2D78]/[0.055] px-3 py-1 text-xs font-semibold text-[#FF2D78]">
                        <CheckCircle className="h-3.5 w-3.5" strokeWidth={1.8} />
                        {payment.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
