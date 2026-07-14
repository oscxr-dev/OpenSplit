import { useMemo, useState } from 'react';
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps';
import geographyData from 'world-atlas/countries-110m.json';
import { ArrowUpRight, MapPin, Minus, Plus, RotateCcw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { countryCoordinates } from '@/lib/geo';
import { relativeTime } from '@/lib/time';
import { useTheme } from '@/hooks/useTheme';
import type { PublicTeamSummary } from '@/types/api';

// world-atlas ships a topojson object; react-simple-maps accepts it directly.
const GEOGRAPHY = geographyData as unknown as object;

interface LocatedTeam {
  team: PublicTeamSummary;
  coordinates: [number, number];
}

interface MapPosition {
  coordinates: [number, number];
  zoom: number;
}

const DEFAULT_POSITION: MapPosition = { coordinates: [0, 18], zoom: 1 };
const MIN_ZOOM = 1;
const MAX_ZOOM = 5;

export function PublicTeamsMap({ teams }: { teams: PublicTeamSummary[] }) {
  const { t } = useTranslation();
  const located = useMemo<LocatedTeam[]>(
    () =>
      teams
        .map((team) => {
          const coordinates = countryCoordinates(team.country);
          return coordinates ? { team, coordinates } : null;
        })
        .filter((entry): entry is LocatedTeam => entry !== null),
    [teams]
  );
  const unknownCount = teams.length - located.length;
  const [hovered, setHovered] = useState<PublicTeamSummary | null>(null);
  const [selected, setSelected] = useState<LocatedTeam | null>(null);
  const [position, setPosition] = useState<MapPosition>(DEFAULT_POSITION);
  const { theme } = useTheme();
  const active = hovered ?? selected?.team ?? null;
  const land =
    theme === 'light'
      ? { fill: 'rgba(17,19,31,0.06)', stroke: 'rgba(17,19,31,0.12)' }
      : { fill: 'rgba(245,245,247,0.05)', stroke: 'rgba(245,245,247,0.10)' };
  const landStyle = {
    default: { fill: land.fill, stroke: land.stroke, strokeWidth: 0.4, outline: 'none' },
    hover: { fill: land.fill, stroke: land.stroke, strokeWidth: 0.4, outline: 'none' },
    pressed: { fill: land.fill, stroke: land.stroke, strokeWidth: 0.4, outline: 'none' },
  };
  const adjustZoom = (delta: number) => {
    setPosition((current) => ({
      ...current,
      zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number((current.zoom + delta).toFixed(1)))),
    }));
  };
  const resetMap = () => {
    setPosition(DEFAULT_POSITION);
    setSelected(null);
    setHovered(null);
  };

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0A0B12]/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <div className="absolute right-3 top-3 z-10 flex overflow-hidden rounded-full border border-white/[0.12] bg-[#11131F]/90 shadow-[0_12px_36px_rgba(0,0,0,0.28)] backdrop-blur-md">
        <button
          type="button"
          onClick={() => adjustZoom(0.5)}
          className="inline-flex h-9 w-9 items-center justify-center text-[#F5F5F7] transition hover:bg-white/[0.08]"
          aria-label={t('public.map.zoomIn')}
        >
          <Plus className="h-4 w-4" strokeWidth={1.8} />
        </button>
        <button
          type="button"
          onClick={() => adjustZoom(-0.5)}
          className="inline-flex h-9 w-9 items-center justify-center border-l border-white/[0.10] text-[#F5F5F7] transition hover:bg-white/[0.08]"
          aria-label={t('public.map.zoomOut')}
        >
          <Minus className="h-4 w-4" strokeWidth={1.8} />
        </button>
        <button
          type="button"
          onClick={resetMap}
          className="inline-flex h-9 w-9 items-center justify-center border-l border-white/[0.10] text-[#F5F5F7] transition hover:bg-white/[0.08]"
          aria-label={t('public.map.reset')}
        >
          <RotateCcw className="h-4 w-4" strokeWidth={1.8} />
        </button>
      </div>

      <div className="h-[420px] sm:h-[500px]">
      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 165 }}
        width={900}
        height={500}
        style={{ width: '100%', height: '100%' }}
        aria-label={t('public.map.aria')}
      >
        <ZoomableGroup
          center={position.coordinates}
          zoom={position.zoom}
          minZoom={MIN_ZOOM}
          maxZoom={MAX_ZOOM}
          onMoveEnd={(nextPosition) => setPosition(nextPosition as MapPosition)}
        >
          <Geographies geography={GEOGRAPHY}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography key={geo.rsmKey} geography={geo} style={landStyle} />
              ))
            }
          </Geographies>

          {located.map((entry) => {
            const { team, coordinates } = entry;
            const isSelected = selected?.team.slug === team.slug;

            return (
              <Marker
                key={team.slug}
                coordinates={coordinates}
                onMouseEnter={() => setHovered(team)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => {
                  setSelected(entry);
                  setPosition((current) => ({
                    coordinates,
                    zoom: Math.max(current.zoom, 2.2),
                  }));
                }}
                style={{ default: { cursor: 'pointer' } }}
              >
                <circle r={isSelected ? 10 : 7} fill="#FF2D78" fillOpacity={isSelected ? 0.26 : 0.16} />
                <circle
                  r={isSelected ? 4.6 : 3.4}
                  fill="#FF2D78"
                  stroke={theme === 'light' ? '#FFFFFF' : '#0A0B12'}
                  strokeWidth={0.9}
                />
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>
      </div>

      {active && (
        <div className="pointer-events-auto absolute bottom-3 left-3 right-3 rounded-2xl border border-white/[0.12] bg-[#11131F]/95 p-4 shadow-[0_18px_50px_rgba(0,0,0,0.4)] backdrop-blur-md sm:left-4 sm:right-auto sm:w-72">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-base font-semibold text-[#F5F5F7]">{active.name}</p>
              <p className="mt-1 font-mono text-[11px] text-[#94A3B8]">/public/{active.slug}</p>
            </div>
            <span className="rounded-full border border-[#FF2D78]/25 bg-[#FF2D78]/10 px-2 py-1 text-[11px] font-semibold text-[#FF2D78]">
              {active.country ?? t('public.map.publicBadge')}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.04] p-3">
              <p className="text-[11px] text-[#94A3B8]">{t('public.map.completedSplits')}</p>
              <p className="mt-1 font-mono text-lg font-semibold text-[#F5F5F7]">{active.completed_splits}</p>
            </div>
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.04] p-3">
              <p className="text-[11px] text-[#94A3B8]">{t('public.map.lastActivity')}</p>
              <p className="mt-1 text-sm font-semibold text-[#F5F5F7]">{relativeTime(active.last_activity)}</p>
            </div>
          </div>
          <Link
            to={`/public/${active.slug}`}
            className="mt-4 inline-flex items-center justify-center gap-1 rounded-full border border-[#FF2D78]/25 bg-[#FF2D78]/10 px-3 py-2 text-xs font-semibold text-[#FF2D78] transition-colors hover:bg-[#FF2D78]/15 hover:text-[#FF6AB6]"
          >
            {t('public.map.viewPublicPage')} <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}

      {unknownCount > 0 && (
        <div className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-full border border-white/[0.10] bg-[#11131F]/90 px-3 py-1 text-[11px] font-medium text-[#94A3B8]">
          <MapPin className="h-3.5 w-3.5" />
          {t('public.map.unknownLocation', { count: unknownCount })}
        </div>
      )}
    </div>
  );
}
