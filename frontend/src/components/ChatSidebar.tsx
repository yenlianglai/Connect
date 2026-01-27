import React from 'react';
import { MessageSquare, Plus, Trash2, X } from 'lucide-react';
import { type Session } from '../api';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface ChatSidebarProps {
  sessions: Session[];
  currentSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession?: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

const ChatSidebar: React.FC<ChatSidebarProps> = ({ 
  sessions, 
  currentSessionId, 
  onSelectSession, 
  onNewSession,
  onDeleteSession,
  isOpen,
  onToggle
}) => {
  const getSessionTitle = (session: Session): string => {
    const sid = session.session_id || (session as any)._id;
    const metadata = (session as any).metadata || {};
    return metadata.topic_name || sid.substring(0, 20) || 'New Chat';
  };

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar */}
      <div className={cn(
        "fixed lg:static inset-y-0 left-0 z-50 lg:z-auto",
        "w-[280px] xl:w-[320px] 2xl:w-[360px]",
        "bg-[#171717] border-r border-[#2d2d2d]",
        "flex flex-col transition-transform duration-300 ease-in-out",
        isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      )}>
        {/* Header */}
        <div className="h-16 px-4 flex items-center justify-between border-b border-[#2d2d2d] shrink-0">
          <button
            onClick={onNewSession}
            className="flex-1 flex items-center gap-3 px-4 py-2.5 bg-[#1a1a1a] hover:bg-[#262626] text-[#d4d4d4] rounded-lg transition-all text-sm font-medium border border-[#2d2d2d] group shadow-sm active:scale-[0.98]"
          >
            <Plus size={18} className="text-[#8c8c8c] group-hover:text-purple-400 transition-colors" />
            <span className="font-semibold">New Chat</span>
          </button>
          <button
            onClick={onToggle}
            className="lg:hidden ml-2 p-2 hover:bg-[#262626] rounded-lg transition-colors text-[#8c8c8c] hover:text-[#d4d4d4]"
          >
            <X size={20} />
          </button>
        </div>

        {/* Session List */}
        <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
          {sessions.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <MessageSquare size={32} className="mx-auto mb-3 text-[#434343]" />
              <p className="text-sm text-[#595959] font-medium">No chat history</p>
              <p className="text-xs text-[#434343] mt-1">Start a new conversation</p>
            </div>
          ) : (
            <div className="px-2">
              {sessions.map((session) => {
                const sid = session.session_id || (session as any)._id;
                const isActive = currentSessionId === sid;
                const title = getSessionTitle(session);
                
                return (
                  <div
                    key={sid}
                    className={cn(
                      "group relative flex items-center gap-2 px-3 py-2.5 mx-1 mb-1 rounded-lg transition-all cursor-pointer",
                      isActive
                        ? "bg-[#262626] text-[#d4d4d4]"
                        : "text-[#8c8c8c] hover:bg-[#1f1f1f] hover:text-[#d4d4d4]"
                    )}
                    onClick={() => onSelectSession(sid)}
                  >
                    {isActive && (
                      <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-purple-500 rounded-r" />
                    )}
                    
                    <MessageSquare 
                      size={18} 
                      className={cn(
                        "shrink-0",
                        isActive ? "text-purple-400" : "text-[#595959] group-hover:text-[#8c8c8c]"
                      )} 
                    />
                    
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{title}</div>
                      {session.updated_at && (
                        <div className="text-xs text-[#595959] mt-0.5">
                          {new Date(session.updated_at).toLocaleDateString(undefined, { 
                            month: 'short', 
                            day: 'numeric',
                            hour: 'numeric',
                            minute: '2-digit'
                          })}
                        </div>
                      )}
                    </div>

                    {onDeleteSession && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(sid);
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1.5 rounded hover:bg-red-500/10 text-[#595959] hover:text-red-400 transition-all shrink-0"
                        title="Delete"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default ChatSidebar;
