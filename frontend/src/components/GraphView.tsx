import React, { useMemo, useRef, useCallback, useState } from 'react';
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import { Network, Maximize2, Trash2, Link as LinkIcon, X, Link2Off } from 'lucide-react';
import { type GraphData, type Node as MnemoNode, deleteNode, createLink, deleteLink } from '../api';
import { toast } from 'react-hot-toast';

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Helper to brighten/darken hex colors for gradients
function brightenColor(hex: string, percent: number) {
  const num = parseInt(hex.replace('#', ''), 16),
    amt = Math.round(2.55 * percent),
    R = (num >> 16) + amt,
    G = (num >> 8 & 0x00FF) + amt,
    B = (num & 0x0000FF) + amt;
  return "#" + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 + (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + (B < 255 ? B < 1 ? 0 : B : 255)).toString(16).slice(1);
}

function darkenColor(hex: string, percent: number) {
  const num = parseInt(hex.replace('#', ''), 16),
    amt = Math.round(2.55 * percent),
    R = (num >> 16) - amt,
    G = (num >> 8 & 0x00FF) - amt,
    B = (num & 0x0000FF) - amt;
  return "#" + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 + (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + (B < 255 ? B < 1 ? 0 : B : 255)).toString(16).slice(1);
}

interface GraphViewProps {
  data: GraphData | null;
  onNodeClick: (node: MnemoNode) => void;
  onZoomInto: (categoryId: string) => void;
  onNodeUpdated?: () => void;
  currentFocusId?: string;
  activeSessionId?: string; // The ID of the currently active chat session/category
  retrievedNodeIds?: string[]; // IDs of nodes found in the last retrieval
}

const CAT0_COLORS: Record<string, string> = {
  "cat_software_eng": "#6366f1", // Indigo 500
  "cat_business": "#10b981",     // Emerald 500
  "cat_science": "#06b6d4",      // Cyan 500
  "cat_humanities": "#ec4899",   // Pink 500
  "cat_lifestyle": "#f59e0b",    // Amber 500
  "cat_facts": "#f97316",        // Orange 500
  "cat_root": "#64748b",         // Slate 500
  "unknown": "#334155",          // Slate 700
};

const EDGE_COLORS: Record<string, string> = {
  "SUB_CATEGORY_OF": "#1e293b", // Deep Slate (almost invisible)
  "BELONGS_TO": "#334155",      // Slate 700
  "SOLVES": "#059669",          // Emerald 600
  "PREREQUISITE_FOR": "#dc2626", // Red 600
  "RELATED_TO": "#4f46e5",      // Indigo 600
  "SIMILAR_TO": "#7c3aed",      // Violet 600
  "PART_OF": "#475569",         // Slate 600
};

const GraphView: React.FC<GraphViewProps> = ({ 
  data, 
  onNodeClick, 
  onZoomInto, 
  onNodeUpdated, 
  currentFocusId, 
  activeSessionId,
  retrievedNodeIds = [] 
}) => {
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  const [linkingSource, setLinkingSource] = useState<any | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number, y: number } | null>(null);
  const [pendingLinkTarget, setPendingLinkTarget] = useState<any | null>(null);
  const [hoverNode, setHoverNode] = useState<any | null>(null);

  const retrievedSet = useMemo(() => new Set(retrievedNodeIds), [retrievedNodeIds]);

  const handleCenter = useCallback(() => {
    if (fgRef.current) {
      fgRef.current.zoomToFit(400, 50);
    }
  }, []);

  const handleDeleteNode = useCallback(async (node: any) => {
    if (!confirm(`Delete node "${node.name || node.description}" and all its links?`)) return;
    
    const tid = toast.loading('Deleting node...');
    try {
      await deleteNode(node.id);
      toast.success('Node deleted', { id: tid });
      if (onNodeUpdated) onNodeUpdated();
    } catch (err) {
      toast.error('Failed to delete node', { id: tid });
    }
  }, [onNodeUpdated]);

  const handleNodeRightClick = useCallback((node: any) => {
    if (node.id === 'cat_root') {
      toast.error("The Root node cannot be modified or deleted.");
      return;
    }
    
    toast((t) => (
      <div className="flex flex-col gap-1 min-w-[140px]">
        <div className="text-[10px] font-bold text-[#595959] uppercase tracking-widest mb-1 px-1 border-b border-[#2d2d2d] pb-1">
          Node Actions
        </div>
        {node.type === 'category' && (
          <button 
            onClick={() => {
              toast.dismiss(t.id);
              onZoomInto(node.id);
            }}
            className="flex items-center gap-2.5 px-2 py-2 hover:bg-blue-500/10 text-blue-400 rounded-lg transition-all text-xs text-left font-medium group"
          >
            <Maximize2 size={14} className="text-[#595959] group-hover:text-blue-400" />
            Zoom Into Subtree
          </button>
        )}
        <button 
          onClick={() => {
            toast.dismiss(t.id);
            setLinkingSource(node);
            node.fx = node.x;
            node.fy = node.y;
            toast.success(`Linking mode active. Click target node.`, { icon: '🔗' });
          }}
          className="flex items-center gap-2.5 px-2 py-2 hover:bg-purple-500/10 text-[#d4d4d4] rounded-lg transition-all text-xs text-left font-medium group"
        >
          <LinkIcon size={14} className="text-[#595959] group-hover:text-purple-400" />
          Start Linking
        </button>
        <button 
          onClick={() => {
            toast.dismiss(t.id);
            handleDeleteNode(node);
          }}
          className="flex items-center gap-2.5 px-2 py-2 hover:bg-rose-500/10 text-rose-400 rounded-lg transition-all text-xs text-left font-medium group"
        >
          <Trash2 size={14} className="text-[#595959] group-hover:text-rose-400" />
          Delete Node
        </button>
      </div>
    ), {
      duration: 4000,
      position: 'bottom-center',
      style: {
        background: '#1a1a1a',
        border: '1px solid #2d2d2d',
        color: '#d4d4d4',
        padding: '8px',
        borderRadius: '12px',
        boxShadow: '0 20px 40px -15px rgba(0, 0, 0, 0.7)'
      }
    });
  }, [handleDeleteNode]);

  const handleLinkRightClick = useCallback((link: any) => {
    toast((t) => (
      <div className="flex flex-col gap-1 min-w-[140px]">
        <div className="text-[10px] font-bold text-[#595959] uppercase tracking-widest mb-1 px-1 border-b border-[#2d2d2d] pb-1">
          Link Actions
        </div>
        <div className="px-2 py-1.5 text-[10px] text-[#8c8c8c] italic border-b border-[#2d2d2d]/50 mb-1">
          {link.edge_label}
        </div>
        <button 
          onClick={async () => {
            toast.dismiss(t.id);
            if (!confirm(`Delete relationship "${link.edge_label}"?`)) return;
            const tid = toast.loading('Removing link...');
            try {
              const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
              const targetId = typeof link.target === 'object' ? link.target.id : link.target;
              await deleteLink(sourceId, targetId, link.edge_label);
              toast.success('Link removed', { id: tid });
              if (onNodeUpdated) onNodeUpdated();
            } catch (err) {
              toast.error('Failed to remove link', { id: tid });
            }
          }}
          className="flex items-center gap-2.5 px-2 py-2 hover:bg-rose-500/10 text-rose-400 rounded-lg transition-all text-xs text-left font-medium group"
        >
          <Link2Off size={14} className="text-[#595959] group-hover:text-rose-400" />
          Delete Link
        </button>
      </div>
    ), {
      duration: 4000,
      position: 'bottom-center',
      style: {
        background: '#1a1a1a',
        border: '1px solid #2d2d2d',
        color: '#d4d4d4',
        padding: '8px',
        borderRadius: '12px',
        boxShadow: '0 20px 40px -15px rgba(0, 0, 0, 0.7)'
      }
    });
  }, [onNodeUpdated]);

  const finalizeLink = async (relType: string) => {
    if (!linkingSource || !pendingLinkTarget) return;
    
    const tid = toast.loading(`Creating ${relType} link...`);
    try {
      await createLink(linkingSource.id, pendingLinkTarget.id, relType);
      toast.success('Link created!', { id: tid });
      if (onNodeUpdated) onNodeUpdated();
    } catch (err) {
      toast.error('Failed to create link', { id: tid });
    } finally {
      if (linkingSource) {
        delete linkingSource.fx;
        delete linkingSource.fy;
      }
      setLinkingSource(null);
      setPendingLinkTarget(null);
      setMousePos(null);
    }
  };

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (linkingSource && fgRef.current) {
      const rect = e.currentTarget.getBoundingClientRect();
      const { x, y } = fgRef.current.screen2GraphCoords(e.clientX - rect.left, e.clientY - rect.top);
      setMousePos({ x, y });
    }
  }, [linkingSource]);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    
    return {
      nodes: data.nodes.map(n => {
        let color = CAT0_COLORS[n.cat0 || ""] || CAT0_COLORS["unknown"];
        if (currentFocusId !== 'cat_root') {
          if (n.id === currentFocusId) color = "#ffffff";
        }
        return { ...n, color };
      }),
      links: data.links.map(l => ({
        source: l.source,
        target: l.target,
        label: l.type,
        edge_label: l.edge_label,
        color: EDGE_COLORS[l.type] || EDGE_COLORS[l.edge_label] || "#2d2d2d"
      }))
    };
  }, [data, currentFocusId]);

  if (!data) return null;

  if (data.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-[#262626] gap-2 bg-[#0d0d0d]">
        <div className="p-6 rounded-2xl bg-[#0f0f0f] border border-[#1a1a1a]">
          <Network size={40} className="text-[#1a1a1a]" />
        </div>
        <p className="text-xs font-medium tracking-widest uppercase mt-4">Graph is Empty</p>
      </div>
    );
  }

  return (
    <div 
      className="h-full w-full bg-[#0d0d0d] relative overflow-hidden"
      onMouseMove={handleMouseMove}
    >
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        {...({ d3AlphaTarget: 0.05 } as any)} // Keep simulation warm for continuous animation
        cooldownTicks={100}
        nodeLabel={(node: any) => `
          <div class="bg-[#262626] border border-[#434343] p-2.5 rounded-md shadow-2xl text-[11px] min-w-[150px]">
            ${node.is_hot ? '<div class="text-[9px] font-bold text-orange-400 mb-1 tracking-tighter uppercase">🔥 Memory Cached</div>' : ''}
            ${retrievedSet.has(node.id) ? '<div class="text-[9px] font-bold text-blue-400 mb-1 tracking-tighter uppercase">🔍 Retrieved</div>' : ''}
            <div class="font-bold text-[#d4d4d4] mb-1">
              ${node.type === 'category' ? node.name : node.description}
            </div>
            ${node.type === 'knowledge' ? `<div class="text-[#8c8c8c] text-[9px] mt-1 line-clamp-2 italic">${node.content}</div>` : ''}
            ${node.type === 'knowledge' && node.tags && node.tags.length > 0 ? `
              <div class="flex flex-wrap gap-1 mt-2">
                ${node.tags.map((tag: string) => `<span class="px-1 py-0.5 rounded bg-purple-500/10 text-purple-400 text-[8px] border border-purple-500/20">#${tag}</span>`).join('')}
              </div>
            ` : ''}
            <div class="text-[#8c8c8c] flex items-center gap-1.5 mt-2 capitalize text-[9px]">
               <span class="w-1.5 h-1.5 rounded-full" style="background-color: ${node.color}"></span>
               ${node.type}
            </div>
          </div>
        `}
        nodeColor={(node: any) => node.color}
        nodeVal={(node: any) => {
          if (node.id === currentFocusId) return 12;
          if (node.type === 'category') return 8;
          return 4;
        }}
        nodeRelSize={1}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.15}
        linkDirectionalParticles={(link: any) => {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          const isActive = retrievedSet.has(sourceId) || retrievedSet.has(targetId) || sourceId === activeSessionId || targetId === activeSessionId;
          return isActive ? 2 : 0; // Fewer particles
        }}
        linkDirectionalParticleWidth={(link: any) => {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          return (sourceId === activeSessionId || targetId === activeSessionId) ? 3 : 1.5; // Smaller particles
        }}
        linkDirectionalParticleSpeed={(link: any) => {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          // MUCH slower speed (0.003-0.006 instead of 0.006-0.012)
          return (sourceId === activeSessionId || targetId === activeSessionId) ? 0.005 : 0.003; 
        }}
        linkDirectionalParticleColor={(link: any) => {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          // Use rgba for softer, ethereal particles
          return (sourceId === activeSessionId || targetId === activeSessionId) ? "rgba(167, 139, 250, 0.6)" : "rgba(34, 211, 238, 0.4)";
        }}
        linkWidth={(link: any) => {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          const isRetrieved = retrievedSet.has(sourceId) || retrievedSet.has(targetId);
          const isHovered = hoverNode && (sourceId === hoverNode.id || targetId === hoverNode.id);
          return (link.edge_label === 'RELATED' ? 1.5 : 2.5) * (isRetrieved || isHovered ? 1.5 : 1);
        }}
        linkColor={(link: any) => {
          if (hoverNode) {
            const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
            const targetId = typeof link.target === 'object' ? link.target.id : link.target;
            if (sourceId === hoverNode.id || targetId === hoverNode.id) return '#ffffff';
            return 'rgba(255,255,255,0.05)';
          }
          return link.color;
        }}
        onNodeClick={(node: any) => {
          if (linkingSource) {
            if (node.id === linkingSource.id) {
              delete linkingSource.fx;
              delete linkingSource.fy;
              setLinkingSource(null);
              setMousePos(null);
              return;
            }
            setPendingLinkTarget(node);
            return;
          }
          onNodeClick(node as MnemoNode);
        }}
        onNodeDragEnd={(node: any) => {
          node.fx = node.x;
          node.fy = node.y;
        }}
        onNodeDoubleClick={(node: any) => {
          if (node.type === 'category' && node.id !== currentFocusId) {
            onZoomInto(node.id);
          }
        }}
        onNodeRightClick={handleNodeRightClick}
        onLinkRightClick={handleLinkRightClick}
        onNodeHover={(node) => setHoverNode(node)}
        onBackgroundClick={() => {
          if (linkingSource) {
            delete linkingSource.fx;
            delete linkingSource.fy;
          }
          setLinkingSource(null);
          setPendingLinkTarget(null);
          setMousePos(null);
        }}
        backgroundColor="#0d0d0d"
        nodeCanvasObjectMode={() => 'always'}
        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
          const isCurrent = node.id === currentFocusId;
          const isActiveSession = node.id === activeSessionId;
          const isRetrieved = retrievedSet.has(node.id);
          const isHot = node.is_hot;
          const isHovered = hoverNode?.id === node.id;
          
          let radius = (isCurrent ? 9 : node.type === 'category' ? 6 : 3.5);
          if (isActiveSession) radius = 8;
          
          const t = Date.now() / 1000;
          const pulse = Math.sin(t * 3) * 0.8; // Slower, gentler pulse
          if (isRetrieved || isHot || isActiveSession) {
            radius += pulse * 0.5;
          }

          if (linkingSource && linkingSource.id === node.id && mousePos) {
            ctx.beginPath();
            ctx.moveTo(node.x, node.y);
            ctx.lineTo(mousePos.x, mousePos.y);
            ctx.strokeStyle = 'rgba(167, 139, 250, 0.4)';
            ctx.lineWidth = 1.5 / globalScale;
            ctx.setLineDash([6, 6]);
            ctx.stroke();
            ctx.setLineDash([]);
          }

          // 1. Draw Atmospheric Glow (Layered)
          if (isCurrent || isHot || isRetrieved || isActiveSession || isHovered) {
            ctx.save();
            const glowRadius = radius + (isCurrent || isActiveSession ? 8 : 5) + pulse;
            const gradient = ctx.createRadialGradient(node.x, node.y, radius, node.x, node.y, glowRadius);
            
            let color = '129, 140, 248'; // Indigo
            if (isActiveSession) color = '167, 139, 250'; // Violet
            if (isRetrieved) color = '34, 211, 238'; // Cyan
            if (isHot) color = '251, 146, 60'; // Orange
            if (isHovered && !isCurrent && !isActiveSession) color = '255, 255, 255';

            gradient.addColorStop(0, `rgba(${color}, 0.25)`);
            gradient.addColorStop(0.5, `rgba(${color}, 0.1)`);
            gradient.addColorStop(1, `rgba(${color}, 0)`);
            
            ctx.fillStyle = gradient;
            ctx.beginPath();
            ctx.arc(node.x, node.y, glowRadius, 0, 2 * Math.PI);
            ctx.fill();
            ctx.restore();
          }

          // 2. Draw Node Texture (Gradient Fill)
          const isNeighbor = graphData.links.some(l => {
            const sId = typeof l.source === 'object' ? (l.source as any).id : l.source;
            const tId = typeof l.target === 'object' ? (l.target as any).id : l.target;
            return (sId === hoverNode?.id && tId === node.id) || (tId === hoverNode?.id && sId === node.id);
          });

          ctx.globalAlpha = hoverNode ? (node.id === hoverNode.id || isActiveSession || isNeighbor ? 1 : 0.15) : 1;

          // Node Body Gradient
          const nodeGradient = ctx.createRadialGradient(
            node.x - radius * 0.3, 
            node.y - radius * 0.3, 
            radius * 0.1, 
            node.x, 
            node.y, 
            radius
          );
          
          // Lighten the top-left for a 3D sphere/glass effect
          nodeGradient.addColorStop(0, brightenColor(node.color, 40));
          nodeGradient.addColorStop(0.7, node.color);
          nodeGradient.addColorStop(1, darkenColor(node.color, 20));

          ctx.beginPath();
          ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
          ctx.fillStyle = nodeGradient;
          ctx.fill();
          
          // 3. Node Border / Ring
          ctx.beginPath();
          ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
          ctx.strokeStyle = isCurrent || isActiveSession ? '#ffffff' : isRetrieved ? '#22d3ee' : 'rgba(255,255,255,0.15)';
          ctx.lineWidth = (isCurrent || isActiveSession || isRetrieved ? 1.5 : 0.8) / globalScale;
          ctx.stroke();

          // 4. Inner Ring for Categories (Decorative)
          if (node.type === 'category' && globalScale > 1.2) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius * 0.7, 0, 2 * Math.PI, false);
            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.lineWidth = 0.5 / globalScale;
            ctx.stroke();
          }

          ctx.globalAlpha = 1;

          // 5. Refined Label Rendering
          const label = node.type === 'category' ? node.name : node.description;
          if (label && globalScale > 1.8) {
            const fontSize = (node.type === 'category' ? 10 : 7.5) / globalScale;
            ctx.font = `${node.type === 'category' ? '600' : '400'} ${fontSize}px Inter, -apple-system, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            
            const labelAlpha = hoverNode ? (node.id === hoverNode.id || isActiveSession || isNeighbor ? 1 : 0.1) : 0.8;

            ctx.globalAlpha = labelAlpha;
            // Subtle Shadow for legibility
            ctx.fillStyle = 'rgba(0,0,0,0.8)';
            ctx.fillText(label, node.x, node.y + radius + 3/globalScale);
            
            ctx.fillStyle = isCurrent || isActiveSession ? '#ffffff' : isRetrieved ? '#22d3ee' : 'rgba(229, 231, 235, 0.9)';
            ctx.fillText(label, node.x, node.y + radius + 3/globalScale);
            ctx.globalAlpha = 1;
          }
        }}
      />
      
      {pendingLinkTarget && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-2xl p-6 shadow-2xl max-w-sm w-full space-y-4 text-center">
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-sm font-bold text-[#d4d4d4] flex items-center gap-2 uppercase tracking-widest">
                <LinkIcon size={16} className="text-purple-400" />
                Select Relationship
              </h3>
              <button onClick={() => { 
                if (linkingSource) { delete linkingSource.fx; delete linkingSource.fy; }
                setLinkingSource(null); 
                setPendingLinkTarget(null); 
              }} className="p-1 text-[#595959] hover:text-[#d4d4d4]">
                <X size={18} />
              </button>
            </div>
            
            <p className="text-[11px] text-[#8c8c8c] leading-relaxed">
              Define the relationship from <br/>
              <span className="text-purple-400 font-bold underline decoration-purple-500/30 underline-offset-4">"{linkingSource?.name || linkingSource?.description}"</span> <br/>
              to <br/>
              <span className="text-blue-400 font-bold underline decoration-blue-500/30 underline-offset-4">"{pendingLinkTarget.name || pendingLinkTarget.description}"</span>
            </p>

            <div className="grid grid-cols-1 gap-2 pt-2">
              {[
                { type: 'RELATED_TO', label: 'Semantic: Related To', color: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20', allowed: true },
                { type: 'PREREQUISITE_FOR', label: 'Flow: Prerequisite For', color: 'bg-rose-500/10 text-rose-400 border-rose-500/20', allowed: true },
                { type: 'SOLVES', label: 'Problem: Solves', color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', allowed: true },
                { type: 'PART_OF', label: 'Composition: Part Of', color: 'bg-slate-500/10 text-slate-400 border-slate-500/20', allowed: true },
                { 
                  type: 'SUB_CATEGORY_OF', 
                  label: 'Vertical: Sub-Category Of', 
                  color: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
                  allowed: linkingSource.type === 'category' && pendingLinkTarget.type === 'category'
                },
                { 
                  type: 'BELONGS_TO', 
                  label: 'Vertical: Belongs To Category', 
                  color: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
                  allowed: linkingSource.type !== 'category' && pendingLinkTarget.type === 'category'
                },
              ].map((rel) => (
                rel.allowed && (
                  <button
                    key={rel.type}
                    onClick={() => finalizeLink(rel.type)}
                    className={cn(
                      "w-full text-left px-4 py-2.5 rounded-xl text-[11px] font-bold uppercase tracking-wide border transition-all hover:scale-[1.02] active:scale-[0.98]",
                      rel.color
                    )}
                  >
                    {rel.label}
                  </button>
                )
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="absolute top-4 right-4 flex flex-col gap-2">
        <button 
          onClick={handleCenter}
          className="p-2.5 bg-[#1f1f1f] hover:bg-[#262626] border border-[#333333] rounded-lg text-[#8c8c8c] hover:text-[#d4d4d4] transition-all shadow-lg"
          title="Center Graph"
        >
          <Maximize2 size={16} />
        </button>
      </div>

      <div className="absolute bottom-6 left-6 flex flex-col gap-1.5 text-[9px] tracking-tight">
        <div className="flex items-center gap-2 group cursor-default">
          <div className="w-1.5 h-1.5 rounded-full bg-[#6366f1]" />
          <span className="text-[#595959] group-hover:text-[#d4d4d4] transition-colors">Engineering</span>
        </div>
        <div className="flex items-center gap-2 group cursor-default">
          <div className="w-1.5 h-1.5 rounded-full bg-[#10b981]" />
          <span className="text-[#595959] group-hover:text-[#d4d4d4] transition-colors">Business</span>
        </div>
        <div className="flex items-center gap-2 group cursor-default">
          <div className="w-1.5 h-1.5 rounded-full bg-[#f59e0b]" />
          <span className="text-[#595959] group-hover:text-[#d4d4d4] transition-colors">Lifestyle</span>
        </div>
        <div className="flex items-center gap-2 group cursor-default">
          <div className="w-1.5 h-1.5 rounded-full bg-[#f97316]" />
          <span className="text-[#595959] group-hover:text-[#d4d4d4] transition-colors">Personal Facts</span>
        </div>
      </div>
    </div>
  );
};

export default GraphView;