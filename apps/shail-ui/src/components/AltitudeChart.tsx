import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { api, MemoryRecord } from '../api';

interface DayBucket {
  date: Date;
  count: number;
}

interface Props {
  daysBack?: number;
}

export function AltitudeChart({ daysBack = 7 }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [buckets, setBuckets] = useState<DayBucket[]>([]);
  const [wkChange, setWkChange] = useState<number>(0);

  const fetchData = async () => {
    setRefreshing(true);
    try {
      const since = new Date(); since.setDate(since.getDate() - daysBack * 2); // pull double for wk/wk
      const r = await api.search({ query: '', k: 500, after: since.toISOString() });
      const items: MemoryRecord[] = r.items;
      const dayMs = 24 * 60 * 60 * 1000;
      const today = new Date(); today.setHours(0,0,0,0);

      // build empty bucket map for last `daysBack` days
      const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const byDay = new Map<string, number>();
      const out: DayBucket[] = [];
      for (let i = daysBack - 1; i >= 0; i--) {
        const d = new Date(today.getTime() - i * dayMs);
        out.push({ date: d, count: 0 });
        byDay.set(dayKey(d), 0);
      }

      // and the previous week for wk/wk
      let thisWeek = 0;
      let lastWeek = 0;
      const thisWeekStart = new Date(today.getTime() - daysBack * dayMs);
      const lastWeekStart = new Date(today.getTime() - 2 * daysBack * dayMs);

      for (const m of items) {
        const t = new Date(m.timestamp);
        if (Number.isNaN(t.getTime())) continue;
        if (t >= thisWeekStart) thisWeek++;
        else if (t >= lastWeekStart) lastWeek++;

        const d0 = new Date(t); d0.setHours(0,0,0,0);
        const k = dayKey(d0);
        if (byDay.has(k)) byDay.set(k, (byDay.get(k) || 0) + 1);
      }
      for (const b of out) b.count = byDay.get(dayKey(b.date)) || 0;
      setBuckets(out);
      setWkChange(lastWeek === 0 ? (thisWeek > 0 ? 100 : 0) : Math.round(((thisWeek - lastWeek) / lastWeek) * 100));
    } catch {
      setBuckets([]);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  useEffect(() => {
    if (!svgRef.current || !wrapRef.current || buckets.length === 0) return;
    const wrap = wrapRef.current.getBoundingClientRect();
    const W = Math.max(320, wrap.width);
    const H = 220;
    const M = { top: 24, right: 24, bottom: 28, left: 24 };
    const innerW = W - M.left - M.right;
    const innerH = H - M.top - M.bottom;

    const svg = d3.select(svgRef.current);
    svg.attr('viewBox', `0 0 ${W} ${H}`).attr('width', '100%').attr('height', H);
    svg.selectAll('*').remove();

    const g = svg.append('g').attr('transform', `translate(${M.left},${M.top})`);
    const x = d3.scaleTime()
      .domain([buckets[0].date, buckets[buckets.length - 1].date])
      .range([0, innerW]);
    const yMax = Math.max(1, d3.max(buckets, b => b.count) ?? 1);
    const y = d3.scaleLinear().domain([0, yMax]).range([innerH, 0]).nice();

    // x-axis tick labels (compact, ALL CAPS)
    const tickFmt = d3.timeFormat('%b %d');
    const tickCount = Math.min(4, buckets.length);
    const ticks = d3.scaleTime().domain(x.domain()).ticks(tickCount);
    g.append('g')
      .attr('transform', `translate(0,${innerH})`)
      .call(
        d3.axisBottom(x)
          .tickValues(ticks)
          .tickFormat(d => tickFmt(d as Date).toUpperCase())
          .tickSize(0)
      )
      .call(s => s.select('.domain').remove())
      .selectAll('text')
        .attr('fill', '#3a3a3a')
        .attr('font-size', 10)
        .attr('font-family', 'ui-monospace, "SF Mono", Menlo, monospace')
        .attr('dy', '1.2em');

    // baseline
    g.append('line')
      .attr('x1', 0).attr('x2', innerW).attr('y1', innerH).attr('y2', innerH)
      .attr('stroke', '#161616');

    // gradient fill under line
    const defs = svg.append('defs');
    const grad = defs.append('linearGradient')
      .attr('id', 'altitude-grad')
      .attr('x1', '0').attr('y1', '0').attr('x2', '0').attr('y2', '1');
    grad.append('stop').attr('offset', '0%').attr('stop-color', '#fff').attr('stop-opacity', 0.18);
    grad.append('stop').attr('offset', '100%').attr('stop-color', '#fff').attr('stop-opacity', 0);

    const area = d3.area<DayBucket>()
      .x(d => x(d.date))
      .y0(innerH)
      .y1(d => y(d.count))
      .curve(d3.curveMonotoneX);

    g.append('path').datum(buckets).attr('d', area).attr('fill', 'url(#altitude-grad)');

    const line = d3.line<DayBucket>()
      .x(d => x(d.date))
      .y(d => y(d.count))
      .curve(d3.curveMonotoneX);

    g.append('path').datum(buckets)
      .attr('d', line)
      .attr('fill', 'none')
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5);

    // dots at each point
    g.selectAll('circle.pt').data(buckets).enter().append('circle')
      .attr('class', 'pt')
      .attr('cx', d => x(d.date))
      .attr('cy', d => y(d.count))
      .attr('r', 2.5)
      .attr('fill', '#fff');
  }, [buckets]);

  const totalLast7 = useMemo(() => buckets.reduce((s, b) => s + b.count, 0), [buckets]);

  return (
    <div ref={wrapRef} style={{
      background: '#0d0d0d',
      border: '1px solid #161616',
      borderRadius: 9,
      padding: 18,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{
            fontSize: 13,
            color: '#fff',
            fontWeight: 500,
          }}>
            Altitude · {daysBack} days
          </div>
          <div style={{ marginTop: 3, fontSize: 11, color: '#666' }}>
            Memory accumulation rate, low → high
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{
            fontSize: 11,
            color: wkChange >= 0 ? '#22c55e' : '#ef4444',
            fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
          }}>
            {wkChange >= 0 ? '+' : ''}{wkChange}% wk/wk
          </span>
          <button
            onClick={fetchData}
            disabled={refreshing}
            style={{
              background: 'none',
              border: '1px solid #1f1f1f',
              borderRadius: 5,
              padding: '4px 9px',
              fontSize: 10,
              color: '#666',
              cursor: refreshing ? 'wait' : 'pointer',
              fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
              opacity: refreshing ? 0.5 : 1,
            }}
            title="Refresh"
          >
            {refreshing ? '…' : '↻'}
          </button>
        </div>
      </div>

      <svg ref={svgRef} />

      <div style={{ marginTop: 8, fontSize: 10, color: '#3a3a3a', fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace' }}>
        {totalLast7} captures in last {daysBack} days
      </div>
    </div>
  );
}
