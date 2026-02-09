import { useState, useMemo, useCallback, useEffect, useRef, lazy, Suspense } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Toaster, toast } from 'react-hot-toast';
import { ChevronRight, Home, ChevronLeft, Menu, Network, Plus } from 'lucide-react';
import { getGraphData, getAllSessions, triggerEvolution, deleteSession, extractContext, refreshMemory, type Node, type GraphData } from './api';
import Chat from './components/Chat';
import ChatSidebar from './components/ChatSidebar';
import Sidebar from './components/Sidebar';
import { Zap, RefreshCw, GitMerge } from 'lucide-react';

// Dynamic imports for heavy components - reduces initial bundle size
const GraphView = lazy(() => import('./components/GraphView'));
const NodeEditor = lazy(() => import('./components/NodeEditor'));

// Loading component for lazy-loaded components
const ComponentLoader: React.FC = () => (
  <div className="absolute inset-0 flex items-center justify-center z-20 bg-[#1a1a1a]/60 backdrop-blur-md">
    <div className="flex flex-col items-center gap-3">
      <div className="w-12 h-12 border-2 border-purple-500/30 border-t-purple-500 rounded-full animate-spin"></div>
      <span className="text-sm font-medium text-[#888888] tracking-widest uppercase">Loading...</span>
    </div>
  </div>
);

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Helper function to extract node ID from link source/target
const getNodeId = (nodeOrId: string | { id: string }): string => {
  return typeof nodeOrId === 'object' ? nodeOrId.id : nodeOrId;
};

// Helper function to filter graph data by focus
const filterGraphByFocus = (graphData: GraphData, currentFocusId: string): GraphData | null => {
  if (currentFocusId === 'cat_root') return graphData;

  const descendants = new Set<string>([currentFocusId]);
  const queue = [currentFocusId];

  while (queue.length > 0) {
    const parentId = queue.shift()!;
    graphData.links.forEach(link => {
      const sourceId = getNodeId(link.source);
      const targetId = getNodeId(link.target);
      if (targetId === parentId && (link.edge_label === 'SUB_CATEGORY_OF' || link.edge_label === 'BELONGS_TO')) {
        if (!descendants.has(sourceId)) {
          descendants.add(sourceId);
          queue.push(sourceId);
        }
      }
    });
  }

  return {
    nodes: graphData.nodes.filter(n => descendants.has(n.id)),
    links: graphData.links.filter(l => {
      const sourceId = getNodeId(l.source);
      const targetId = getNodeId(l.target);
      return descendants.has(sourceId) && descendants.has(targetId);
    })
  };
};

function App() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string>('');
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
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
    refetchInterval: activeTab === 'graph' ? 8000 : 30000,
    staleTime: 3000,
  });

  const { data: sessionsData } = useQuery({
    queryKey: ['sessions'],
    queryFn: getAllSessions,
    refetchInterval: 60000,
  });

  const refreshAllData = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['graphData'] });
    queryClient.invalidateQueries({ queryKey: ['sessions'] });
  }, [queryClient]);

  // Refetch graph when switching to Graph tab so changes are visible
  useEffect(() => {
    if (activeTab === 'graph') {
      queryClient.invalidateQueries({ queryKey: ['graphData'] });
    }
  }, [activeTab, queryClient]);

  // Poll graph after extraction so new nodes appear without manual refresh
  const extractionPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startExtractionPolling = useCallback(() => {
    if (extractionPollingRef.current) clearInterval(extractionPollingRef.current);
    let count = 0;
    const maxPolls = 10;
    extractionPollingRef.current = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['graphData'] });
      count += 1;
      if (count >= maxPolls && extractionPollingRef.current) {
        clearInterval(extractionPollingRef.current);
        extractionPollingRef.current = null;
      }
    }, 3000);
  }, [queryClient]);
  useEffect(() => () => {
    if (extractionPollingRef.current) {
      clearInterval(extractionPollingRef.current);
      extractionPollingRef.current = null;
    }
  }, []);

  const focusedGraphData = useMemo(() => {
    if (!graphData) return null;
    return filterGraphByFocus(graphData, currentFocusId);
  }, [graphData, currentFocusId]);

  const handleNodeClick = useCallback((node: Node) => {
    setSelectedNode(node);
    setActiveTab('editor');
  }, []);

  const handleCreateNode = useCallback(() => {
    setSelectedNode(null);
    setActiveTab('editor');
  }, []);

  const handleZoomInto = useCallback((categoryId: string) => {
    if (categoryId === currentFocusId) return;
    setFocusStack(prev => [...prev, categoryId]);
    setSelectedNode(null);
  }, [currentFocusId]);

  const handleGoBack = useCallback(() => {
    setFocusStack(prev => {
      if (prev.length > 1) {
        setSelectedNode(null);
        return prev.slice(0, -1);
      }
      return prev;
    });
  }, []);

  const handleGoHome = useCallback(() => {
    setFocusStack(['cat_root']);
    setSelectedNode(null);
  }, []);

  const handleNewMessage = useCallback(() => {
    refreshAllData();
  }, [refreshAllData]);

  const handleNewSession = useCallback(() => {
    setSessionId('');
    setSelectedNode(null);
    setNewTopicConfig(null);
    setFocusStack(['cat_root']);
    setActiveTab('chat');
    setSidebarOpen(false);
  }, []);

  const handleSessionCreated = useCallback((id: string) => {
    handleZoomInto(id);
    refreshAllData();
    toast.success('Topic anchor created. Starting learning...');
  }, [handleZoomInto, refreshAllData]);

  const handleDeleteSession = useCallback(async (id: string) => {
    const tid = toast.loading(`Deleting session...`);
    try {
      await deleteSession(id);
      toast.success('Session deleted', { id: tid });
      setSessionId(prev => prev === id ? '' : prev);
      refreshAllData();
    } catch (err) {
      toast.error('Failed to delete session', { id: tid });
    }
  }, [refreshAllData]);

  const handleStartSessionHere = useCallback((node: Node) => {
    setSessionId('');
    setSelectedNode(null);
    setNewTopicConfig({
      name: `Learning: ${node.name || 'New Topic'}`,
      parentId: node.id
    });
    setActiveTab('chat');
    toast.success(`New topic session targeted under: ${node.name || node.id}`);
  }, []);

  const handleEvolveSubtree = useCallback(async (categoryId: string) => {
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
  }, [refreshAllData]);

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen(prev => !prev);
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    setSessionId(id);
    setActiveTab('chat');
    setSidebarOpen(false);
  }, []);

  const handleSetActiveTabChat = useCallback(() => {
    setActiveTab('chat');
  }, []);

  const handleSetActiveTabGraph = useCallback(() => {
    setActiveTab('graph');
  }, []);

  const handleCloseSidebar = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const handleSelectNode = useCallback((id: string) => {
    if (!id) {
      setSelectedNode(null);
    } else {
      refreshAllData();
      const findAndSelectNode = () => {
        const node = graphData?.nodes.find(n => n.id === id);
        if (node) {
          setSelectedNode(node);
        }
      };
      findAndSelectNode();
      setTimeout(findAndSelectNode, 300);
    }
  }, [graphData, refreshAllData]);

  const handleNodeDeleted = useCallback(() => {
    setSelectedNode(null);
    setActiveTab('graph');
    refreshAllData();
  }, [refreshAllData]);

  const availableCategories = useMemo(() =>
    graphData?.nodes.filter(n => n.type === 'category') || [],
    [graphData]
  );

  return (
    <div className="flex h-screen w-screen bg-[#171717] text-[#d4d4d4] font-sans overflow-hidden">
      <Toaster position="bottom-right" />

      {/* ChatGPT-style Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar: Chat History */}
        <ChatSidebar
          sessions={sessionsData?.sessions || []}
          currentSessionId={sessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
          isOpen={sidebarOpen}
          onToggle={handleToggleSidebar}
        />

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Top Bar - Simplified */}
          <div className="h-14 px-4 lg:px-6 flex items-center justify-between border-b border-[#2d2d2d] bg-[#171717] shrink-0">
            <div className="flex items-center gap-3">
              <button
                onClick={handleToggleSidebar}
                className="lg:hidden p-2 hover:bg-[#262626] rounded-lg transition-colors text-[#8c8c8c] hover:text-[#d4d4d4]"
              >
                <Menu size={20} />
              </button>
              <h1 className="text-lg lg:text-xl font-semibold text-[#d4d4d4]">Connect</h1>
            </div>

            {/* Tab Switcher */}
            <div className="flex items-center gap-1 p-1 bg-[#1a1a1a] rounded-lg border border-[#2d2d2d]">
              <button
                onClick={handleSetActiveTabChat}
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
                onClick={handleSetActiveTabGraph}
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

          {/* Controls Bar - Extract, Refresh, Evolve buttons */}
          {activeTab === 'chat' && (
            <div className="px-4 lg:px-6 py-2 flex items-center gap-2 border-b border-[#2d2d2d] bg-[#171717] shrink-0">
              <button
                onClick={async () => {
                  if (!sessionId) {
                    toast.error("Select a chat from the sidebar or send a message first to extract from.");
                    return;
                  }
                  const tid = toast.loading("Extracting...");
                  try {
                    await extractContext(sessionId);
                    toast.success("Extraction started. New nodes may appear in the Graph in a few moments.", { id: tid, duration: 5000 });
                    refreshAllData();
                    startExtractionPolling();
                  } catch (error: unknown) {
                    const msg = error instanceof Error ? error.message : (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to trigger extraction";
                    toast.error(msg, { id: tid });
                  }
                }}
                title={!sessionId ? "Select a chat session first (sidebar) or send a message" : "Extract knowledge from this chat into the graph"}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                  "bg-[#262626] hover:bg-[#333333] text-[#d4d4d4] border border-[#333333]",
                  !sessionId && "opacity-50 cursor-not-allowed"
                )}
              >
                <Zap size={14} />
                <span>Extract</span>
              </button>

              <button
                onClick={async () => {
                  if (!sessionId) {
                    toast.error("No active session to refresh!");
                    return;
                  }
                  const tid = toast.loading("Refreshing...");
                  try {
                    await refreshMemory(sessionId);
                    toast.success("Memory refresh scheduled!", { id: tid });
                    refreshAllData();
                  } catch (error) {
                    toast.error("Failed to trigger refresh", { id: tid });
                  }
                }}
                disabled={!sessionId}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                  "bg-[#262626] hover:bg-[#333333] text-[#d4d4d4] border border-[#333333]",
                  !sessionId && "opacity-30 cursor-not-allowed"
                )}
              >
                <RefreshCw size={14} />
                <span>Refresh</span>
              </button>

              <button
                onClick={async () => {
                  const tid = toast.loading("Evolving...");
                  try {
                    await triggerEvolution();
                    toast.success("Evolution triggered!", { id: tid });
                    refreshAllData();
                  } catch (error) {
                    toast.error("Failed to trigger evolution", { id: tid });
                  }
                }}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                  "bg-[#262626] hover:bg-[#333333] text-[#d4d4d4] border border-[#333333]"
                )}
              >
                <GitMerge size={14} />
                <span>Evolve</span>
              </button>
            </div>
          )}

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

                {isGraphLoading && !graphData ? (
                  <ComponentLoader />
                ) : (
                  <Suspense fallback={<ComponentLoader />}>
                    <GraphView
                      data={focusedGraphData}
                      onNodeClick={handleNodeClick}
                      onZoomInto={handleZoomInto}
                      onNodeUpdated={refreshAllData}
                      currentFocusId={currentFocusId}
                      activeSessionId={sessionId}
                      retrievedNodeIds={retrievedNodeIds}
                    />
                  </Suspense>
                )}
              </div>
            ) : activeTab === 'editor' ? (
              /* Editor View */
              <div className="h-full overflow-hidden">
                <Suspense fallback={<ComponentLoader />}>
                  <NodeEditor
                    selectedNode={selectedNode}
                    onNodeUpdated={refreshAllData}
                    currentFocusId={currentFocusId}
                    onSelectNode={handleSelectNode}
                    onNodeDeleted={handleNodeDeleted}
                  />
                </Suspense>
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
                      onClose={handleCloseSidebar}
                      onSelectNode={setSelectedNode}
                      onEvolveSubtree={handleEvolveSubtree}
                      isEvolving={isEvolvingSubtree}
                      onStartSessionHere={handleStartSessionHere}
                      onNodeUpdated={refreshAllData}
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
                    availableCategories={availableCategories}
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
