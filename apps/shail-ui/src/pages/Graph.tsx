import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import { api, MemoryGraphEdge, MemoryGraphNode, MemoryRecord, SOURCE_COLOR, SOURCE_LABEL } from '../api';
import { MemoryCard } from '../components/MemoryCard';
import { useUIStore } from '../stores/ui';
import { flag } from '../lib/featureFlags';

const SOURCES = ['chatgpt', 'claude', 'gemini', 'perplexity', 'web'] as const;

interface Node extends d3.SimulationNodeDatum {
  id: string;
  graphNode: MemoryGraphNode;
}
interface Link {
  source: string | Node;
  target: string | Node;
}

export function Graph() {
  const svgRef    = useRef<SVGSVGElement>(null);
  const [filter, setFilter]     = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const simRef = useRef<d3.Simulation<Node, Link> | null>(null);

  const citedIds = useUIStore(s => s.lastAnswerCitations)
    .filter(c => c.type === 'memory')
    .map(c => (c as { id: string }).id);

  const { data, isLoading, error } = useQuery({
    queryKey: ['memories', 'graph'],
    queryFn: () => api.memoryGraph(),
    staleTime: 2 * 60_000,
  });
  const graphNodes = data?.nodes ?? [];
  const graphEdges = data?.edges ?? [];

  const selectedMemory = useQuery({
    queryKey: ['memories', 'detail', selectedId],
    queryFn: () => api.getMemory(selectedId!),
    enabled: !!selectedId,
    staleTime: 2 * 60_000,
  });

  const filteredGraph = useMemo(() => {
    const nodes = filter === 'all'
      ? graphNodes
      : graphNodes.filter(node => node.sourceApp === filter);
    const nodeIds = new Set(nodes.map(node => node.id));
    const edges = graphEdges.filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target));
    return { nodes, edges };
  }, [filter, graphEdges, graphNodes]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    if (filteredGraph.nodes.length === 0) {
      simRef.current?.stop();
      simRef.current = null;
      return;
    }

    const nodes: Node[] = filteredGraph.nodes.map(graphNode => ({ id: graphNode.id, graphNode }));
    const links: Link[] = filteredGraph.edges.map((edge: MemoryGraphEdge) => ({
      source: edge.source,
      target: edge.target,
    }));

    const w = svgRef.current.clientWidth || 800;
    const h = svgRef.current.clientHeight || 600;

    const sim = d3.forceSimulation<Node>(nodes)
      .alphaDecay(0.06)
      .force('link', d3.forceLink<Node, Link>(links).id(d => d.id).distance(96).strength(0.35))
      .force('charge', d3.forceManyBody().strength(-180))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide<Node>().radius(d => 18 + (d.graphNode.importance ?? 0.5) * 14));
    simRef.current = sim;

    const g = svg.append('g');

    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.2, 4])
        .on('zoom', ev => g.attr('transform', ev.transform)),
    );

    const edgeLines = g.append('g').selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#00D4FF')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2);

    const evidenceSet = new Set(showEvidence ? citedIds : []);

    const node = g.append('g')
      .selectAll<SVGCircleElement, Node>('circle')
      .data(nodes)
      .join('circle')
      .attr('r', d => {
        const baseRadius = 8 + (d.graphNode.importance ?? 0.5) * 10;
        return evidenceSet.has(d.id) ? baseRadius + 4 : baseRadius;
      })
      .attr('fill', d => evidenceSet.has(d.id) ? 'var(--shail-evidence, #8a8ad4)' : '#FFFFFF')
      .attr('fill-opacity', 0.95)
      .attr('stroke', d => evidenceSet.has(d.id) ? 'var(--shail-evidence, #8a8ad4)' : '#00D4FF')
      .attr('stroke-width', d => evidenceSet.has(d.id) ? 3 : 2)
      .style('cursor', 'pointer')
      .on('click', (_ev, d) => setSelectedId(d.id));

    node.append('title').text(d => d.graphNode.label || d.id);

    node.call(
      d3.drag<SVGCircleElement, Node>()
        .on('start', (_ev, d) => {
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (ev, d) => {
          d.fx = ev.x;
          d.fy = ev.y;
        })
        .on('end', () => {
          // keep node pinned where dropped — no sim restart
        }),
    );

    const labels = g.append('g')
      .selectAll<SVGTextElement, Node>('text')
      .data(nodes)
      .join('text')
      .attr('font-size', 10)
      .attr('font-family', '-apple-system, BlinkMacSystemFont, "SF Pro Rounded", sans-serif')
      .attr('font-weight', '500')
      .attr('fill', d => evidenceSet.has(d.id) ? 'var(--shail-evidence, #8a8ad4)' : '#FFFFFF')
      .attr('fill-opacity', 0.85)
      .attr('text-anchor', 'middle')
      .attr('dy', d => -(8 + (d.graphNode.importance ?? 0.5) * 8) - 5)
      .style('pointer-events', 'none')
      .style('text-shadow', '0 1px 4px rgba(0,0,0,0.9), 0 0 8px rgba(0,0,0,0.6)')
      .text(d => d.graphNode.label.slice(0, 22));

    sim.on('tick', () => {
      edgeLines
        .attr('x1', d => (d.source as Node).x!)
        .attr('y1', d => (d.source as Node).y!)
        .attr('x2', d => (d.target as Node).x!)
        .attr('y2', d => (d.target as Node).y!);
      node.attr('cx', d => d.x!).attr('cy', d => d.y!);
      labels.attr('x', d => d.x!).attr('y', d => d.y!);
    });

    return () => { sim.stop(); };
  }, [filteredGraph, showEvidence, citedIds]);

  const hasEvidence = flag('ui_v2') && citedIds.length > 0;
  const selectedRecord = selectedMemory.data as MemoryRecord | undefined;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '32px 48px 20px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexShrink: 0, gap: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600, color: 'var(--shail-text-primary)', letterSpacing: '-0.5px' }}>
            Knowledge Graph
          </h1>
          <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--shail-text-muted)', lineHeight: 1.5 }}>
            {graphNodes.length} memories · {graphEdges.length} backend connections
            {filter !== 'all' && ` · filtered to ${SOURCE_LABEL[filter] ?? filter}`}
          </p>
        </div>
        {/* Filter pills */}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {hasEvidence && (
            <button
              onClick={() => setShowEvidence(s => !s)}
              style={{
                padding: '5px 11px', borderRadius: 20, fontSize: 11, fontWeight: 500, cursor: 'pointer',
                border: `1px solid ${showEvidence ? 'var(--shail-evidence)50' : 'var(--shail-border-subtle)'}`,
                background: showEvidence ? 'var(--shail-evidence-soft)' : 'transparent',
                color: showEvidence ? 'var(--shail-evidence)' : 'var(--shail-text-muted)',
                transition: 'all 0.12s',
              }}
            >
              ◈ Evidence
            </button>
          )}
          {(['all', ...SOURCES] as const).map(s => {
            const isActive = filter === s;
            const color = s === 'all' ? 'var(--shail-text-muted)' : (SOURCE_COLOR[s] ?? 'var(--shail-text-muted)');
            const activeBg = s === 'all' ? 'var(--shail-bg-raised)' : (SOURCE_COLOR[s] ?? '#888') + '18';
            const activeBorder = s === 'all' ? 'var(--shail-border-strong)' : (SOURCE_COLOR[s] ?? '#888') + '50';
            return (
              <button key={s} onClick={() => setFilter(s)} style={{
                padding: '5px 11px', borderRadius: 20, fontSize: 11, fontWeight: 500, cursor: 'pointer',
                border: `1px solid ${isActive ? activeBorder : 'var(--shail-border-subtle)'}`,
                background: isActive ? activeBg : 'transparent',
                color: isActive ? color : 'var(--shail-text-muted)',
                transition: 'all 0.12s',
              }}>
                {s === 'all' ? 'All' : SOURCE_LABEL[s]}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, position: 'relative', background: '#0D0D14' }}>
          <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />
          {isLoading && (
            <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--shail-text-muted)', fontSize: 13 }}>
              Loading graph…
            </div>
          )}
          {!isLoading && !!error && (
            <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--shail-warning)', fontSize: 13, padding: 24, textAlign: 'center' }}>
              Failed to load the knowledge graph.
            </div>
          )}
          {!isLoading && !error && filteredGraph.nodes.length === 0 && (
            <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--shail-text-muted)', fontSize: 13 }}>
              No graph nodes match this filter.
            </div>
          )}
        </div>
        {selectedId && (
          <div style={{
            width: 320,
            background: 'var(--shail-bg-surface)',
            borderLeft: '1px solid var(--shail-border-subtle)',
            padding: 20,
            overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--shail-text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Memory
              </span>
              <button
                onClick={() => setSelectedId(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--shail-text-muted)', fontSize: 16, lineHeight: 1, opacity: 0.5 }}
                onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                onMouseLeave={e => (e.currentTarget.style.opacity = '0.5')}
              >
                ×
              </button>
            </div>
            {selectedMemory.isLoading && (
              <div style={{ fontSize: 13, color: 'var(--shail-text-muted)' }}>Loading memory…</div>
            )}
            {!selectedMemory.isLoading && selectedRecord && (
              <MemoryCard record={selectedRecord} onDeleted={() => setSelectedId(null)} />
            )}
            {!selectedMemory.isLoading && !selectedRecord && (
              <div style={{ fontSize: 13, color: 'var(--shail-text-muted)' }}>Memory details unavailable.</div>
            )}
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{
        padding: '8px 48px',
        display: 'flex',
        gap: 18,
        fontSize: 10,
        color: 'var(--shail-text-muted)',
        borderTop: '1px solid var(--shail-border-subtle)',
        flexShrink: 0,
        opacity: 0.8,
      }}>
        <span>◯ node size tracks importance</span>
        <span>─ backend graph edge</span>
        {showEvidence && <span style={{ color: 'var(--shail-evidence)' }}>● evidence cited in last answer</span>}
        <span style={{ marginLeft: 'auto' }}>Scroll to zoom · drag to pan · click node to inspect</span>
      </div>
    </div>
  );
}
