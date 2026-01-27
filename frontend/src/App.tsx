import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Toaster, toast } from 'react-hot-toast';
import { ChevronRight, Home, ChevronLeft, Menu, Network, Plus } from 'lucide-react';
import { getGraphData, getAllSessions, triggerEvolution, deleteSession, type Node as MnemoNode } from './api';
import Chat from './components/Chat';
import GraphView from './components/GraphView';
import ChatSidebar from './components/ChatSidebar';
import Sidebar from './components/Sidebar';
import NodeEditor from './components/NodeEditor';

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function App() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string>('');
  const [selectedNode, setSelectedNode] = useState<MnemoNode | null>(null);
  const [activeTab, setActiveTab] = useState<'chat' | 'graph' | 'editor'>('chat');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isEvolvingSubtree, setIsEvolvingSubtree] = useState(false);
  const [focusStack, setFocusStack] = useState<string[]>(['cat_root']);
  const [retrievedNodeIds, setRetrievedNodeIds] = useState<string[]>([]);
  
  // State for new recursive topic flow
  const [newTopicConfig, setNewTopicConfig] = useState<{ name: string; parentId: string } | null>(null);

  const currentFocusId = focusStack[focusStack.length - 1];

  const { data: graphData, isLoading: isGraphLoading } = useQuery({
    queryKey: ['graphData', sessionId],
    queryFn: () => getGraphData(sessionId),
    refetchInterval: 30000, 
    staleTime: 5000,
  });

  const { data: sessionsData } = useQuery({
    queryKey: ['sessions'],
    queryFn: getAllSessions,
    refetchInterval: 60000,
  });

  const refreshAllData = () => {
    queryClient.invalidateQueries({ queryKey: ['graphData'] });
    queryClient.invalidateQueries({ queryKey: ['sessions'] });
  };

  const focusedGraphData = useMemo(() => {
    if (!graphData) return null;
    if (currentFocusId === 'cat_root') return graphData;

    // Filter nodes that are descendants of currentFocusId or the focus node itself
    const descendants = new Set<string>([currentFocusId]);
    const queue = [currentFocusId];
    
    // Simple iterative find descendants (since graph is a tree vertically)
    while (queue.length > 0) {
      const parentId = queue.shift()!;
      graphData.links.forEach(link => {
        const sId = typeof link.source === 'object' ? (link.source as any).id : link.source;
        const tId = typeof link.target === 'object' ? (link.target as any).id : link.target;
        if (tId === parentId && (link.edge_label === 'SUB_CATEGORY_OF' || link.edge_label === 'BELONGS_TO')) {
          if (!descendants.has(sId)) {
            descendants.add(sId);
            queue.push(sId);
          }
        }
      });
    }

    return {
      nodes: graphData.nodes.filter(n => descendants.has(n.id)),
      links: graphData.links.filter(l => {
        const sId = typeof l.source === 'object' ? (l.source as any).id : l.source;
        const tId = typeof l.target === 'object' ? (l.target as any).id : l.target;
        return descendants.has(sId) && descendants.has(tId);
      })
    };
  }, [graphData, currentFocusId]);

  const handleNodeClick = (node: MnemoNode) => {
    setSelectedNode(node);
    // Switch to editor tab when a node is clicked
    setActiveTab('editor');
  };

  const handleCreateNode = () => {
    // Clear selection and open editor in create mode
    setSelectedNode(null);
    setActiveTab('editor');
  };

  const handleZoomInto = (categoryId: string) => {
    if (categoryId === currentFocusId) return;
    setFocusStack(prev => [...prev, categoryId]);
    setSelectedNode(null);
  };

  const handleGoBack = () => {
    if (focusStack.length > 1) {
      setFocusStack(prev => prev.slice(0, -1));
      setSelectedNode(null);
    }
  };

  const handleGoHome = () => {
    setFocusStack(['cat_root']);
    setSelectedNode(null);
  };

  const handleNewMessage = () => {
    refreshAllData();
  };

  const handleNewSession = () => {
    setSessionId('');
    setSelectedNode(null);
    setNewTopicConfig(null);
    setFocusStack(['cat_root']); 
    setActiveTab('chat');
    setSidebarOpen(false); // Close sidebar on mobile after selecting
  };

  const handleSessionCreated = (id: string) => {
    handleZoomInto(id);
    refreshAllData();
    toast.success('Topic anchor created. Starting learning...');
  };

  const handleDeleteSession = async (id: string) => {
    const tid = toast.loading(`Deleting session...`);
    try {
      await deleteSession(id);
      toast.success('Session deleted', { id: tid });
      if (sessionId === id) setSessionId('');
      refreshAllData();
    } catch (err) {
      toast.error('Failed to delete session', { id: tid });
    }
  };

  const handleStartSessionHere = (node: MnemoNode) => {
    setSessionId('');
    setSelectedNode(null);
    setNewTopicConfig({
      name: `Learning: ${node.name || 'New Topic'}`,
      parentId: node.id
    });
    setActiveTab('chat');
    toast.success(`New topic session targeted under: ${node.name || node.id}`);
  };

  const handleEvolveSubtree = async (categoryId: string) => {
    setIsEvolvingSubtree(true);
    const tid = toast.loading(`Evolving subtree ${categoryId}...`);
    try {
      await triggerEvolution(categoryId);
      toast.success('Subtree evolution complete!', { id: tid });
      refreshAllData();
    } catch (err) {
      toast.error('Evolution failed.', { id: tid });
    } finally {
      setIsEvolvingSubtree(false);
    }
  };

  return (
    <div className="flex h-screen w-screen bg-[#171717] text-[#d4d4d4] font-sans overflow-hidden">
      <Toaster position="bottom-right" />

      {/* ChatGPT-style Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar: Chat History */}
        <ChatSidebar
          sessions={sessionsData?.sessions || []}
          currentSessionId={sessionId}
          onSelectSession={(id) => {
            setSessionId(id);
            setActiveTab('chat');
            setSidebarOpen(false); // Close on mobile
          }}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen(!sidebarOpen)}
        />

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Top Bar - Simplified */}
          <div className="h-14 px-4 lg:px-6 flex items-center justify-between border-b border-[#2d2d2d] bg-[#171717] shrink-0">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 hover:bg-[#262626] rounded-lg transition-colors text-[#8c8c8c] hover:text-[#d4d4d4]"
              >
                <Menu size={20} />
              </button>
              <h1 className="text-lg lg:text-xl font-semibold text-[#d4d4d4]">Mnemo</h1>
            </div>

            {/* Tab Switcher */}
            <div className="flex items-center gap-1 p-1 bg-[#1a1a1a] rounded-lg border border-[#2d2d2d]">
              <button
                onClick={() => setActiveTab('chat')}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-md transition-all text-sm font-medium",
                  activeTab === 'chat'
                    ? "bg-[#262626] text-purple-400"
                    : "text-[#8c8c8c] hover:text-[#d4d4d4]"
                )}
              >
                <span>Chat</span>
              </button>
              <button
                onClick={() => setActiveTab('graph')}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-md transition-all text-sm font-medium",
                  activeTab === 'graph'
                    ? "bg-[#262626] text-purple-400"
                    : "text-[#8c8c8c] hover:text-[#d4d4d4]"
                )}
              >
                <Network size={18} />
                <span className="hidden sm:inline">Graph</span>
              </button>
            </div>
          </div>

          {/* Content Area */}
          <main className="flex-1 overflow-hidden relative">
            {activeTab === 'graph' ? (
              /* Graph View */
              <div className="h-full relative bg-[#1a1a1a] overflow-hidden">
                {/* Create Node Button - Floating */}
                <div className="absolute top-4 right-4 z-30">
                  <button
                    onClick={handleCreateNode}
                    className="flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-semibold transition-all shadow-lg shadow-purple-900/30 active:scale-95"
                    title="Create New Node"
                  >
                    <Plus size={18} />
                    <span className="hidden sm:inline">Create Node</span>
                  </button>
                </div>

                {/* Breadcrumbs */}
                {focusStack.length > 1 && (
                  <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-4 py-2 bg-[#1a1a1a]/90 backdrop-blur-md border border-[#2d2d2d] rounded-full shadow-2xl">
                    <button
                      onClick={handleGoHome}
                      className="p-1.5 hover:bg-[#262626] rounded-full text-[#8c8c8c] hover:text-[#d4d4d4] transition-colors"
                      title="Back to Root"
                    >
                      <Home size={16} />
                    </button>
                    <ChevronRight size={14} className="text-[#434343]" />
                    <button
                      onClick={handleGoBack}
                      className="flex items-center gap-1.5 px-3 py-1 hover:bg-[#262626] rounded-full text-sm font-medium text-[#d4d4d4] transition-colors"
                    >
                      <ChevronLeft size={14} />
                      <span>Back</span>
                    </button>
                    <div className="w-px h-4 bg-[#2d2d2d] mx-1" />
                    <span className="text-sm font-bold text-purple-400 tracking-tight px-2">
                      {graphData?.nodes.find(n => n.id === currentFocusId)?.name || 'Subtree'}
                    </span>
                  </div>
                )}

                {isGraphLoading && !graphData && (
                  <div className="absolute inset-0 flex items-center justify-center z-20 bg-[#1a1a1a]/60 backdrop-blur-md">
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-12 h-12 border-2 border-purple-500/30 border-t-purple-500 rounded-full animate-spin"></div>
                      <span className="text-sm font-medium text-[#888888] tracking-widest uppercase">Initializing Graph</span>
                    </div>
                  </div>
                )}

                <GraphView
                  data={focusedGraphData}
                  onNodeClick={handleNodeClick}
                  onZoomInto={handleZoomInto}
                  onNodeUpdated={() => refreshAllData()}
                  currentFocusId={currentFocusId}
                  activeSessionId={sessionId}
                  retrievedNodeIds={retrievedNodeIds}
                />
              </div>
            ) : activeTab === 'editor' ? (
              /* Editor View */
              <div className="h-full overflow-hidden">
                <NodeEditor
                  selectedNode={selectedNode}
                  onNodeUpdated={() => refreshAllData()}
                  currentFocusId={currentFocusId}
                  onSelectNode={(id) => {
                    if (!id) {
                      setSelectedNode(null);
                    } else {
                      // Refresh graph data to get the newly created node
                      refreshAllData();
                      // Find and select the node once graph data is available
                      const findAndSelectNode = () => {
                        const node = graphData?.nodes.find(n => n.id === id);
                        if (node) {
                          setSelectedNode(node);
                        }
                      };
                      // Try immediately, then after a short delay for async refresh
                      findAndSelectNode();
                      setTimeout(findAndSelectNode, 300);
                    }
                  }}
                  onNodeDeleted={() => {
                    setSelectedNode(null);
                    setActiveTab('graph');
                    refreshAllData();
                  }}
                />
              </div>
            ) : (
              /* Chat View - ChatGPT Style */
              <div className="h-full flex flex-col bg-[#171717]">
                {/* Node Inspector (if selected) - Collapsible */}
                {selectedNode && (
                  <div className="border-b border-[#2d2d2d] bg-[#1a1a1a] max-h-[40vh] overflow-y-auto">
                    <Sidebar
                      selectedNode={selectedNode}
                      graphData={graphData || null}
                      onClose={() => setSelectedNode(null)}
                      onSelectNode={setSelectedNode}
                      onEvolveSubtree={handleEvolveSubtree}
                      isEvolving={isEvolvingSubtree}
                      onStartSessionHere={handleStartSessionHere}
                      onNodeUpdated={() => refreshAllData()}
                    />
                  </div>
                )}

                {/* Chat Interface */}
                <div className="flex-1 overflow-hidden">
                  <Chat
                    sessionId={sessionId}
                    setSessionId={setSessionId}
                    onNewMessage={handleNewMessage}
                    onRetrievedNodes={setRetrievedNodeIds}
                    onSessionCreated={handleSessionCreated}
                    initialTopicName={newTopicConfig?.name}
                    initialParentId={newTopicConfig?.parentId}
                    availableCategories={graphData?.nodes.filter(n => n.type === 'category') || []}
                  />
                </div>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}

export default App;