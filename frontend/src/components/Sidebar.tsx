import React, { useMemo } from 'react';
import { X, Calendar, Info, Brain, Zap, RefreshCw, ChevronDown, Link as LinkIcon, MessageSquarePlus } from 'lucide-react';
import { type Node, type GraphData } from '../api';

interface SidebarProps {
  selectedNode: Node | null;
  graphData: GraphData | null;
  onClose: () => void;
  onSelectNode: (node: Node) => void;
  onEvolveSubtree?: (categoryId: string) => void;
  isEvolving?: boolean;
  onStartSessionHere?: (node: Node) => void;
  onNodeUpdated?: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  selectedNode,
  graphData,
  onClose,
  onSelectNode,
  onEvolveSubtree,
  isEvolving,
  onStartSessionHere
}) => {
  // Organize connections into hierarchical (Children) and semantic (Horizontal)
  const connections = useMemo(() => {
    if (!graphData || !selectedNode) return { children: [], parents: [], semantic: [] };

    const children: { node: Node; type: string }[] = [];
    const parents: { node: Node; type: string }[] = [];
    const semantic: { node: Node; type: string }[] = [];

    graphData.links.forEach(l => {
      // 1. Vertical Logic (Hierarchy)
      if (l.target === selectedNode.id && (l.edge_label === 'BELONGS_TO' || l.edge_label === 'SUB_CATEGORY_OF')) {
        const sourceNode = graphData.nodes.find(n => n.id === l.source);
        if (sourceNode) children.push({ node: sourceNode, type: l.edge_label });
      } else if (l.source === selectedNode.id && (l.edge_label === 'BELONGS_TO' || l.edge_label === 'SUB_CATEGORY_OF')) {
        const targetNode = graphData.nodes.find(n => n.id === l.target);
        if (targetNode) parents.push({ node: targetNode, type: l.edge_label });
      }

      // 2. Semantic Logic (Horizontal)
      const isStructural = ['BELONGS_TO', 'SUB_CATEGORY_OF'].includes(l.edge_label);
      if (!isStructural) {
        if (l.source === selectedNode.id) {
          const targetNode = graphData.nodes.find(n => n.id === l.target);
          if (targetNode) semantic.push({ node: targetNode, type: l.type || l.edge_label });
        } else if (l.target === selectedNode.id) {
          const sourceNode = graphData.nodes.find(n => n.id === l.source);
          if (sourceNode) semantic.push({ node: sourceNode, type: `REVERSE_${l.type || l.edge_label}` });
        }
      }
    });

    return { children, parents, semantic };
  }, [selectedNode, graphData]);

  if (!selectedNode) return null;

  return (
    <div className="h-full bg-[#111111] overflow-y-auto z-30 flex flex-col border-l border-[#2d2d2d]">
      <div className="px-6 py-4 border-b border-[#2d2d2d] flex justify-between items-center bg-[#111111] sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <Info size={14} className="text-[#8c8c8c]" />
          <h3 className="text-[11px] font-bold text-[#8c8c8c] uppercase tracking-widest">Inspector</h3>
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-[#262626] text-[#595959] hover:text-[#d4d4d4] transition-all">
          <X size={16} />
        </button>
      </div>

      <div className="p-6 space-y-8 flex-1 custom-scrollbar">
        {/* Header & Quick Actions */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
              selectedNode.type === 'category'
                ? 'bg-blue-500/5 text-blue-400/80 border-blue-500/10'
                : 'bg-emerald-500/5 text-emerald-400/80 border-emerald-500/10'
            }`}>
              {selectedNode.type === 'category' ? `Category (L${selectedNode.level})` : 'Knowledge'}
            </span>

            {selectedNode.type === 'category' && onEvolveSubtree && (
              <div className="flex gap-2">
                {onStartSessionHere && (
                  <button
                    onClick={() => onStartSessionHere(selectedNode)}
                    className="flex items-center gap-1.5 px-2 py-1 bg-[#262626] hover:bg-[#333333] border border-[#333333] rounded text-[#d4d4d4] text-[10px] transition-all"
                  >
                    <MessageSquarePlus size={12} />
                    <span>Topic</span>
                  </button>
                )}
                <button
                  onClick={() => onEvolveSubtree(selectedNode.id)}
                  disabled={isEvolving}
                  className="flex items-center gap-1.5 px-2 py-1 bg-[#262626] hover:bg-[#333333] border border-[#333333] rounded text-[#d4d4d4] text-[10px] transition-all disabled:opacity-30"
                >
                  {isEvolving ? <RefreshCw size={12} className="animate-spin" /> : <Zap size={12} />}
                  <span>Evolve</span>
                </button>
              </div>
            )}
          </div>

          <h1 className="text-base font-bold text-[#d4d4d4] leading-tight">
            {selectedNode.type === 'category' ? selectedNode.name : selectedNode.description}
          </h1>

          {selectedNode.type === 'knowledge' && (selectedNode.tags || []).length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {(selectedNode.tags || []).map(tag => (
                <span key={tag} className="px-1.5 py-0.5 rounded bg-purple-500/5 text-purple-400/70 border border-purple-500/10 text-[9px] font-medium">
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Connections Section */}
        <div className="space-y-6 pt-4 border-t border-[#262626]">
          {connections.parents.length > 0 && (
            <div className="space-y-3">
              <label className="text-[10px] font-medium text-[#595959] uppercase tracking-wider flex items-center gap-1.5">
                <ChevronDown size={10} className="rotate-180" /> Parent
              </label>
              <div className="space-y-1.5">
                {connections.parents.map(({ node }) => (
                  <button
                    key={node.id}
                    onClick={() => onSelectNode(node)}
                    className="w-full text-left px-3 py-2 rounded-md bg-[#161616] border border-[#262626] hover:border-[#404040] hover:bg-[#1a1a1a] transition-all group flex items-center justify-between"
                  >
                    <span className="text-[11px] text-[#d4d4d4] group-hover:text-white line-clamp-1">{node.name || node.description}</span>
                    <span className="text-[8px] font-bold text-[#595959] uppercase">UP</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {connections.children.length > 0 && (
            <div className="space-y-3">
              <label className="text-[10px] font-medium text-[#595959] uppercase tracking-wider flex items-center gap-1.5">
                <ChevronDown size={10} /> {selectedNode.type === 'category' ? 'Contents' : 'Sub-items'}
              </label>
              <div className="space-y-1.5">
                {connections.children.map(({ node }) => (
                  <button
                    key={node.id}
                    onClick={() => onSelectNode(node)}
                    className="w-full text-left px-3 py-2 rounded-md bg-[#161616] border border-[#262626] hover:border-[#404040] hover:bg-[#1a1a1a] transition-all group flex items-center justify-between"
                  >
                    <span className="text-[11px] text-[#d4d4d4] group-hover:text-white line-clamp-1">{node.type === 'category' ? node.name : node.description}</span>
                    <span className="text-[8px] font-bold text-[#595959] uppercase">{node.type === 'category' ? 'DIR' : 'NODE'}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {connections.semantic.length > 0 && (
            <div className="space-y-3">
              <label className="text-[10px] font-medium text-[#595959] uppercase tracking-wider flex items-center gap-1.5">
                <LinkIcon size={10} /> Semantic Links
              </label>
              <div className="space-y-1.5">
                {connections.semantic.map(({ node, type }) => (
                  <button
                    key={`${node.id}-${type}`}
                    onClick={() => onSelectNode(node)}
                    className="w-full text-left px-3 py-2 rounded-md bg-[#161616] border border-[#262626] hover:border-[#404040] hover:bg-[#1a1a1a] transition-all group flex items-center justify-between"
                  >
                    <span className="text-[11px] text-[#d4d4d4] group-hover:text-white line-clamp-1">{node.type === 'category' ? node.name : node.description}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold border ${
                      type.includes('SOLVES') ? 'text-emerald-500/80 bg-emerald-500/5 border-emerald-500/10' :
                      type.includes('PREREQUISITE') ? 'text-rose-500/80 bg-rose-500/5 border-rose-500/10' :
                      'text-[#595959] bg-[#262626]'
                    }`}>
                      {type.replace('REVERSE_', '← ').replace('_', ' ')}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Metadata Footer */}
        <div className="pt-8 border-t border-[#262626] space-y-4">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-[#595959] flex items-center gap-1.5"><Calendar size={12} /> Discovered</span>
            <span className="text-[#8c8c8c]">{new Date(selectedNode.created_at).toLocaleDateString()}</span>
          </div>

          {selectedNode.type === 'category' && (
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-[#595959] flex items-center gap-1.5"><RefreshCw size={12} /> Pending Changes</span>
              <span className="text-purple-400 font-medium">{selectedNode.insert_counter || 0} nodes</span>
            </div>
          )}

          {selectedNode.type === 'knowledge' && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-[#595959] flex items-center gap-1.5"><Brain size={12} /> Utility</span>
                <span className="text-emerald-400 font-medium">{((selectedNode.worth_of_learning || 0) * 10).toFixed(1)}/10</span>
              </div>
              <div className="w-full h-1 bg-[#141414] rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500/40"
                  style={{ width: `${(selectedNode.worth_of_learning || 0) * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
