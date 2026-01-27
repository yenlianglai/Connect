import React, { useState } from 'react';
import { RefreshCw, Zap, GitMerge, MessageSquare, Network, PanelRight, PanelRightClose, FileEdit } from 'lucide-react';
import { extractContext, refreshMemory, triggerEvolution } from '../api';
import toast from 'react-hot-toast';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface ControlsProps {
  sessionId: string;
  activeTab: 'chat' | 'sessions' | 'editor';
  setActiveTab: (tab: 'chat' | 'sessions' | 'editor') => void;
  showWorkspace: boolean;
  onToggleWorkspace: () => void;
}

const Controls: React.FC<ControlsProps> = ({ 
  sessionId, 
  activeTab, 
  setActiveTab,
  showWorkspace,
  onToggleWorkspace
}) => {
  const [isExtracting, setIsExtracting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isEvolving, setIsEvolving] = useState(false);

  const handleExtract = async () => {
    if (!sessionId) {
      toast.error("No active session to extract from!");
      return;
    }
    setIsExtracting(true);
    try {
      await extractContext(sessionId);
      toast.success("Extraction scheduled!");
    } catch (error) {
      toast.error("Failed to trigger extraction");
    } finally {
      setIsExtracting(false);
    }
  };

  const handleRefresh = async () => {
    if (!sessionId) {
      toast.error("No active session to refresh!");
      return;
    }
    setIsRefreshing(true);
    try {
      await refreshMemory(sessionId);
      toast.success("Memory refresh scheduled!");
    } catch (error) {
      toast.error("Failed to trigger refresh");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleEvolve = async () => {
    setIsEvolving(true);
    try {
      await triggerEvolution();
      toast.success("Evolution triggered!");
    } catch (error) {
      toast.error("Failed to trigger evolution");
    } finally {
      setIsEvolving(false);
    }
  };

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-[#1a1a1a] border-b border-[#2d2d2d] sticky top-0 z-20 h-14">
      <div className="flex items-center gap-3">
        <button
          onClick={handleExtract}
          disabled={isExtracting || !sessionId}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-md text-[11px] font-medium transition-all",
            "bg-[#262626] hover:bg-[#333333] text-[#d4d4d4] border border-[#333333] disabled:opacity-30 disabled:cursor-not-allowed"
          )}
        >
          <Zap size={14} className={isExtracting ? "animate-pulse" : ""} />
          <span>Extract</span>
        </button>

        <button
          onClick={handleRefresh}
          disabled={isRefreshing || !sessionId}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-md text-[11px] font-medium transition-all",
            "bg-[#262626] hover:bg-[#333333] text-[#d4d4d4] border border-[#333333] disabled:opacity-30 disabled:cursor-not-allowed"
          )}
        >
          <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} />
          <span>Refresh</span>
        </button>

        <button
          onClick={handleEvolve}
          disabled={isEvolving}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-md text-[11px] font-medium transition-all",
            "bg-[#262626] hover:bg-[#333333] text-[#d4d4d4] border border-[#333333] disabled:opacity-30 disabled:cursor-not-allowed"
          )}
        >
          <GitMerge size={14} className={isEvolving ? "animate-bounce" : ""} />
          <span>Evolve</span>
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1 p-1 bg-[#141414] rounded-lg border border-[#2d2d2d]">
          <button 
            onClick={() => { setActiveTab('chat'); if (!showWorkspace) onToggleWorkspace(); }}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-md transition-all text-[11px] font-bold uppercase tracking-wider",
              activeTab === 'chat' && showWorkspace ? "bg-[#2d2d2d] text-purple-400" : "text-[#595959] hover:text-[#8c8c8c]"
            )}
            title="Conversation"
          >
            <MessageSquare size={14} />
            <span>Chat</span>
          </button>
          <button 
            onClick={() => { setActiveTab('editor'); if (!showWorkspace) onToggleWorkspace(); }}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-md transition-all text-[11px] font-bold uppercase tracking-wider",
              activeTab === 'editor' && showWorkspace ? "bg-[#2d2d2d] text-purple-400" : "text-[#595959] hover:text-[#8c8c8c]"
            )}
            title="Editor"
          >
            <FileEdit size={14} />
            <span>Note</span>
          </button>
          <button 
            onClick={() => { setActiveTab('sessions'); if (!showWorkspace) onToggleWorkspace(); }}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-md transition-all text-[11px] font-bold uppercase tracking-wider",
              activeTab === 'sessions' && showWorkspace ? "bg-[#2d2d2d] text-purple-400" : "text-[#595959] hover:text-[#8c8c8c]"
            )}
            title="Library"
          >
            <Network size={14} />
            <span>Library</span>
          </button>
        </div>

        <div className="w-px h-6 bg-[#2d2d2d]" />

        <button 
          onClick={onToggleWorkspace}
          className={cn(
            "p-2 hover:bg-[#262626] rounded-md transition-all border border-[#2d2d2d]",
            showWorkspace ? "text-purple-400 border-purple-900/30" : "text-[#8c8c8c]"
          )}
          title={showWorkspace ? "Close Workspace" : "Open Workspace"}
        >
          {showWorkspace ? <PanelRightClose size={18} /> : <PanelRight size={18} />}
        </button>
      </div>
    </div>
  );
};

export default Controls;