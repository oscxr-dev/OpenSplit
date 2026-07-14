import { Building2 } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { formatDateShort, formatSats } from '@/lib/utils';
import type { Member, SplitRule } from '@/types/api';

interface TeamMapProps {
  members: Member[];
  workspaceName: string;
  /** When provided, the graph renders THIS rule's targets (enriched with payout
   *  stats from `members`, matched by label). Switching tabs in MembersPage swaps
   *  selectedRule, which swaps the rule shown in the graph. */
  selectedRule?: SplitRule | null;
  /** Optional content rendered between the summary card and the graph card —
   *  used to attach the active-rule tabs to the top border of the graph. */
  tabsSlot?: ReactNode;
}

type MapSelection = { type: 'team' } | { type: 'member'; index: number };

const orbitNodes = [
  { x: 50, y: 15 },
  { x: 79, y: 36 },
  { x: 64, y: 83 },
  { x: 21, y: 66 },
  { x: 22, y: 31 },
  { x: 50, y: 85 },
];

function memberKey(member: Member, index: number) {
  return `${member.label}-${member.nostr_pubkey ?? member.ln_address ?? index}`;
}

function channelAngle(node: { x: number; y: number }) {
  const dx = node.x - 50;
  const dy = node.y - 50;
  return (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
}

function allocationRing(share: number, angle: number) {
  const degrees = Math.min(360, Math.max(0, share * 3.6));
  const connectionAngle = (angle + 180) % 360;
  const start = connectionAngle - degrees / 2;

  return `
    conic-gradient(from ${start}deg, rgba(255,46,147,0.94) 0deg ${degrees}deg, rgba(154,164,178,0.14) ${degrees}deg 360deg)
  `;
}

function compactName(name: string) {
  const [first, last] = name.split(' ');
  return last ? `${first} ${last.charAt(0).replace('.', '')}.` : first;
}

function responsiveNodeSize(size: number) {
  const viewportSize = Math.max(20, size / 6).toFixed(2);
  return `clamp(82px, ${viewportSize}vw, ${size}px)`;
}

/** i18n key for a member's coarse payout status chip. */
function memberStatusKey(member: Member) {
  if (member.failed_count > 0) return 'team.map.needsRetry';
  if (member.collision) return 'team.map.checkIdentity';
  return 'team.map.active';
}

export function TeamMap({ members, workspaceName, selectedRule, tabsSlot }: TeamMapProps) {
  const { t } = useTranslation();
  const [selection, setSelection] = useState<MapSelection>({ type: 'member', index: 0 });
  const [centerBlinking, setCenterBlinking] = useState(false);
  // The graph renders the selected rule's targets, enriched with payout stats
  // from the members feed (matched by label). Falls back to the raw members list
  // when no rule is provided.
  const visibleMembers = useMemo<Member[]>(() => {
    if (selectedRule) {
      const statsByLabel = new Map(members.map((member) => [member.label, member]));
      return selectedRule.targets
        .filter((target) => target.percentage > 0)
        .slice()
        .sort((a, b) => a.order - b.order)
        .map((target) => {
          const stats = statsByLabel.get(target.label);
          return {
            label: target.label,
            ln_address: target.ln_address ?? stats?.ln_address ?? null,
            nostr_pubkey: stats?.nostr_pubkey ?? null,
            current_percentage: target.percentage,
            total_paid_sats: stats?.total_paid_sats ?? 0,
            payment_count: stats?.payment_count ?? 0,
            last_payment_at: stats?.last_payment_at ?? null,
            failed_count: stats?.failed_count ?? 0,
            target_count: stats?.target_count ?? 1,
            collision: stats?.collision ?? false,
          };
        });
    }
    return members.filter((member) => (member.current_percentage ?? 0) > 0);
  }, [selectedRule, members]);
  const normalizedSelectedIndex = selection.type === 'member' && visibleMembers[selection.index] ? selection.index : 0;
  const selectedMember = selection.type === 'member' ? visibleMembers[normalizedSelectedIndex] : undefined;
  const teamSelected = selection.type === 'team';
  const totalAllocation = visibleMembers.reduce((sum, member) => sum + (member.current_percentage ?? 0), 0);
  const totalReceived = visibleMembers.reduce((sum, member) => sum + member.total_paid_sats, 0);
  const flowSignature = visibleMembers
    .map((member) => `${member.label}:${member.current_percentage ?? 0}:${member.payment_count}:${member.last_payment_at ?? ''}`)
    .join('|');

  useEffect(() => {
    if (!visibleMembers.length) return;

    const timers: number[] = [];
    setCenterBlinking(false);

    timers.push(window.setTimeout(() => setCenterBlinking(true), 80));
    timers.push(window.setTimeout(() => setCenterBlinking(false), 1780));

    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [flowSignature, visibleMembers.length]);

  return (
    <section className="proof-canvas space-y-4">
      {(selectedMember || teamSelected) && (
        <div className="rounded-lg border border-[#2A2D3A] bg-[#151722] p-4 shadow-[inset_0_1px_0_rgba(245,245,247,0.04)] sm:p-5">
          <div className="grid gap-4 lg:grid-cols-[minmax(220px,0.42fr)_1fr] lg:items-center">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#FF2E93]">
                {teamSelected ? t('team.map.selectedTeam') : t('team.map.selectedPartner')}
              </p>
              <div className="mt-2 flex flex-wrap items-end gap-3">
                <h3 className="text-2xl font-semibold tracking-tight text-[#F5F5F7]">
                  {teamSelected ? workspaceName : compactName(selectedMember?.label ?? '')}
                </h3>
                <span className="mb-1 rounded-full border border-[#2A2D3A] bg-[#181A26] px-2.5 py-1 text-xs font-medium text-[#9AA4B2]">
                  {teamSelected ? t('team.map.btcpaySource') : t(memberStatusKey(selectedMember as Member))}
                </span>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-[#2A2D3A] bg-[#181A26] px-4 py-3">
                <p className="text-xs text-[#9AA4B2]">{t('team.map.allocation')}</p>
                <p className="mt-1 font-mono text-xl font-semibold text-[#F5F5F7]">
                  {teamSelected ? `${totalAllocation}%` : `${selectedMember?.current_percentage ?? 0}%`}
                </p>
              </div>
              <div className="rounded-lg border border-[#2A2D3A] bg-[#181A26] px-4 py-3">
                <p className="text-xs text-[#9AA4B2]">{teamSelected ? t('team.map.partners') : t('team.map.received')}</p>
                <p className="mt-1 font-mono text-xl font-semibold text-[#F5F5F7]">
                  {teamSelected ? visibleMembers.length : formatSats(selectedMember?.total_paid_sats ?? 0)}
                </p>
              </div>
              <div className="rounded-lg border border-[#2A2D3A] bg-[#181A26] px-4 py-3">
                <p className="text-xs text-[#9AA4B2]">{teamSelected ? t('team.map.settled') : t('team.map.lastPayout')}</p>
                <p className="mt-1 font-mono text-xl font-semibold text-[#F5F5F7]">
                  {teamSelected ? formatSats(totalReceived) : formatDateShort(selectedMember?.last_payment_at ?? null)}
                </p>
              </div>
            </div>
          </div>

          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[#2A2D3A]">
            <span
              className="block h-full rounded-full bg-[#FF2E93]"
              style={{ width: `${teamSelected ? Math.min(100, totalAllocation) : selectedMember?.current_percentage ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Tabs + graph share one container so the tabs attach flush to the graph
          card's top border (no space-y gap between them). */}
      <div className="relative">
        {tabsSlot}

        <div
        className="relative min-h-[540px] overflow-hidden rounded-lg border border-[#2A2D3A] bg-[#11121A] p-4 shadow-[inset_0_1px_0_rgba(245,245,247,0.055),0_24px_70px_rgba(0,0,0,0.28)] sm:min-h-[620px] sm:p-6 lg:min-h-[700px] lg:p-10"
        style={{
          background:
            'radial-gradient(circle at 50% 50%, rgba(255,46,147,0.13), rgba(82,34,64,0.12) 25%, rgba(24,26,38,0.86) 54%, rgba(17,18,26,0.98) 100%), linear-gradient(145deg, #181A26 0%, #12111B 54%, #11121A 100%)',
        }}
      >
        <div className="absolute left-1/2 top-1/2 h-[78%] w-[78%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#9AA4B2]/[0.035] sm:h-[86%] sm:w-[86%]" />
        <div className="absolute left-1/2 top-1/2 h-[58%] w-[58%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#FF2E93]/[0.055] sm:h-[66%] sm:w-[66%]" />
        <div className="absolute left-1/2 top-1/2 h-[36%] w-[36%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#9AA4B2]/[0.045] sm:h-[42%] sm:w-[42%]" />

        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
          {visibleMembers.map((member, index) => {
            const node = orbitNodes[index % orbitNodes.length];
            const share = member.current_percentage ?? 0;

            return (
              <g key={memberKey(member, index)}>
                <line
                  className="allocation-flow-line"
                  x1="50"
                  y1="50"
                  x2={node.x}
                  y2={node.y}
                  stroke="rgba(255,46,147,0.28)"
                  strokeLinecap="round"
                  strokeWidth={Math.max(0.65, Math.min(2.4, share / 24))}
                />
              </g>
            );
          })}
        </svg>

        <button
          type="button"
          onClick={() => setSelection({ type: 'team' })}
          aria-label={t('team.map.selectAria', { name: workspaceName })}
          className={`allocation-hub absolute left-1/2 top-1/2 z-20 flex h-32 w-32 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border bg-[#151722] text-center transition hover:scale-[1.015] sm:h-40 sm:w-40 lg:h-48 lg:w-48 ${
            teamSelected
              ? 'border-[#FF2E93]/50 shadow-[0_0_0_10px_rgba(255,46,147,0.07),0_0_68px_rgba(255,46,147,0.18)] lg:shadow-[0_0_0_14px_rgba(255,46,147,0.07),0_0_78px_rgba(255,46,147,0.18)]'
              : 'border-[#FF2E93]/32 shadow-[0_0_0_10px_rgba(255,46,147,0.045),0_0_58px_rgba(255,46,147,0.16)] lg:shadow-[0_0_0_14px_rgba(255,46,147,0.045),0_0_72px_rgba(255,46,147,0.16)]'
          } ${centerBlinking ? 'allocation-hub-blink' : ''}`}
        >
          <Building2 className="h-5 w-5 text-[#FF2E93] sm:h-6 sm:w-6 lg:h-7 lg:w-7" strokeWidth={1.8} />
          <p className="mt-3 px-4 text-xs font-semibold leading-4 text-[#F5F5F7] sm:text-sm lg:mt-4 lg:px-6 lg:text-base lg:leading-5">{workspaceName}</p>
          <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.16em] text-[#9AA4B2] sm:mt-3 sm:text-[10px] sm:tracking-[0.18em]">{t('team.map.btcpayStore')}</p>
        </button>

        {visibleMembers.map((member, index) => {
          const node = orbitNodes[index % orbitNodes.length];
          const share = member.current_percentage ?? 0;
          const size = Math.max(100, Math.min(140, 92 + share * 1.05));
          const isSelected = selection.type === 'member' && normalizedSelectedIndex === index;
          const angle = channelAngle(node);
          const showSplitCount = size >= 106 && member.payment_count > 0;

          return (
            <button
              key={memberKey(member, index)}
              type="button"
              onClick={() => setSelection({ type: 'member', index })}
              aria-label={t('team.map.selectAria', { name: member.label })}
              className="allocation-member-node absolute z-30 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full p-[2px] text-center transition hover:scale-[1.015]"
              style={{
                left: `${node.x}%`,
                top: `${node.y}%`,
                width: responsiveNodeSize(size),
                height: responsiveNodeSize(size),
                background: allocationRing(share, angle),
                boxShadow: isSelected
                  ? '0 0 0 7px rgba(255,46,147,0.08), 0 0 34px rgba(255,46,147,0.18)'
                  : '0 16px 36px rgba(0,0,0,0.30)',
              }}
            >
              <span
                className="flex h-full w-full flex-col items-center justify-center rounded-full border bg-[#171722] px-3"
                style={{ borderColor: isSelected ? 'rgba(255,46,147,0.42)' : 'rgba(154,164,178,0.16)' }}
              >
                <span className="max-w-[82px] truncate text-[12px] font-semibold leading-tight text-[#F5F5F7] sm:max-w-[104px] sm:text-sm">
                  {compactName(member.label)}
                </span>
                <span className="mt-1 font-mono text-[24px] font-semibold leading-none tracking-tight text-[#FF2E93] sm:text-[28px]">{share}%</span>
                {showSplitCount && (
                  <span className="mt-1 text-[10px] font-medium leading-none text-[#9AA4B2]">{t('team.map.splitCount', { count: member.payment_count })}</span>
                )}
              </span>
            </button>
          );
        })}
        </div>
      </div>
    </section>
  );
}
