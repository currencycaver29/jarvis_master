import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { api, MemoryRecord, SOURCE_COLOR, SOURCE_LABEL } from '../api';
import { MemoryCard } from '../components/MemoryCard';

const SOURCES = ['chatgpt', 'claude', 'gemini', 'perplexity', 'web'] as const;

interface Node extends d3.SimulationNodeDatum {
  id: string;
  record: MemoryRecord;
}
interface Link {
  source: string;
  target: string;
}

export function Graph() {
  const svgRef    = useRef<SVGSVGElement>(null);
  const [records, setRecords]   = useState<MemoryRecord[]>([]);
  const [filter, setFilter]     = useState('all');
  const [selected, setSelected] = useState<MemoryRecord | null>(null);
  const simRef = useRef<d3.Simulation<Node, Link> | null>(null);

  useEffect(() => {
    api.search({ query: '', k: 200 })
      .then(r => setRecords(r.items))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!svgRef.current || records.length === 0) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const filtered = filter === 'all' ? records : records.filter(r => r.sourceApp === filter);
    const nodes: Node[] = filtered.map(r => ({ id: r.id, record: r }));

    // Edges: records sharing at least one tag
    const links: Link[] = [];
    for (let i = 0; i < filtered.length; i++) {
      for (let j = i + 1; j < filtered.length; j++) {
        const tagsI = new Set(filtered[i].tags ?? []);
        const hasShared = (filtered[j].tags ?? []).some(t => tagsI.has(t));
        if (hasShared) links.push({ source: filtered[i].id, target: filtered[j].id });
      }
    }

    const w = svgRef.current.clientWidth || 800;
    const h = svgRef.current.clientHeight || 600;

    const sim = d3.forceSimulation<Node>(nodes)
      .force('link', d3.forceLink<Node, Link>(links).id(d => d.id).distance(80).strength(0.4))
      .force('charge', d3.forceManyBody().strength(-120))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide(18));
    simRef.current = sim;

    const g = svg.append('g');

    // Zoom
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.2, 4])
        .on('zoom', ev => g.attr('transform', ev.transform)),
    );

    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#1c1c1c')
      .attr('stroke-width', 1);

    const node = g.append('g')
      .selectAll<SVGCircleElement, Node>('circle')
      .data(nodes)
      .join('circle')
      .attr('r', 7)
      .attr('fill', d => SOURCE_COLOR[d.record.sourceApp] ?? '#444')
      .attr('stroke', '#000')
      .attr('stroke-width', 1.5)
      .style('cursor', 'pointer')
      .on('click', (_ev, d) => setSelected(d.record))
      .call(
        d3.drag<SVGCircleElement, Node>()
          .on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on('drag',  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
          .on('end',   (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }),
      );

    sim.on('tick', () => {
      link
        .attr('x1', d => (d.source as Node).x!)
        .attr('y1', d => (d.source as Node).y!)
        .attr('x2', d => (d.target as Node).x!)
        .attr('y2', d => (d.target as Node).y!);
      node.attr('cx', d => d.x!).attr('cy', d => d.y!);
    });

    return () => { sim.stop(); };
  }, [records, filter]);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '40px 48px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 500, color: '#fff', letterSpacing: '-0.4px' }}>Graph</h1>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: '#3a3a3a' }}>Memories connected by shared tags</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {['all', ...SOURCES].map(s => {
            const isActive = filter === s;
            const color = s === 'all' ? '#888' : (SOURCE_COLOR[s] ?? '#888');
            return (
              <button key={s} onClick={() => setFilter(s)} style={{ padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 500, cursor: 'pointer', border: `1px solid ${isActive ? color + '50' : '#1a1a1a'}`, background: isActive ? color + '18' : 'transparent', color: isActive ? color : '#444' }}>
                {s === 'all' ? 'All' : SOURCE_LABEL[s]}
              </button>
            );
          })}
        </div>
      </div>

      {/* Canvas + detail */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <svg ref={svgRef} style={{ flex: 1, background: '#050505' }} />
        {selected && (
          <div style={{ width: 320, background: '#0a0a0a', borderLeft: '1px solid #161616', padding: 20, overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <span style={{ fontSize: 12, color: '#444' }}>Memory detail</span>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#333', fontSize: 16, lineHeight: 1 }}>×</button>
            </div>
            <MemoryCard record={selected} onDeleted={() => setSelected(null)} />
          </div>
        )}
      </div>
    </div>
  );
}
