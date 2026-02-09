import React from 'react';
import { MessageSquare, Plus, Clock, History as HistoryIcon, Trash2 } from 'lucide-react';
import { type Session } from '../api';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SessionSidebarProps {
  sessions: Session[];
  currentSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession?: (id: string) => void;
  isOpen?: boolean; // New prop for RWD control
}

const SessionSidebar: React.FC<SessionSidebarProps> = ({
  sessions,
  currentSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  isOpen = true
}) => {
  return (
    <div className={cn(
      "h-full flex flex-col transition-all duration-300 overflow-hidden",
      isOpen ? "opacity-100" : "opacity-0"
    )}>
      <div className="p-4 border-b border-[#2d2d2d]">
        <button
          onClick={onNewSession}
          className="w-full flex items-center justify-between gap-2 bg-[#1a1a1a] hover:bg-[#262626] text-[#d4d4d4] px-4 py-2.5 rounded-md transition-all text-xs font-medium border border-[#333333] group shadow-sm active:scale-[0.98]"
        >
          <div className="flex items-center gap-2">
            <Plus size={14} className="text-[#8c8c8c]" />
            <span>New Session</span>
          </div>
          <kbd className="hidden lg:inline-flex px-1.5 py-0.5 rounded bg-[#141414] border border-[#2d2d2d] text-[10px] text-[#595959] font-mono group-hover:border-[#434343]">N</kbd>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
        <div className="px-5 py-2 text-[10px] font-bold text-[#595959] uppercase tracking-[0.15em] mb-1">
          Recent Sessions
        </div>
        {sessions.map((s) => {
          const sid = s.session_id || (s as any)._id;
          const isActive = currentSessionId === sid;
          return (
            <div
              key={sid}
              className={cn(
                "group relative w-full flex items-center gap-3 px-5 py-2.5 text-[11px] transition-all text-left",
                isActive
                  ? "bg-[#262626] text-[#d4d4d4]"
                  : "text-[#8c8c8c] hover:bg-[#1a1a1a] hover:text-[#d4d4d4]"
              )}
            >
              {isActive && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-purple-500 rounded-r" />}

              <button
                onClick={() => onSelectSession(sid)}
                className="flex-1 flex items-center gap-3 min-w-0"
              >
                <MessageSquare size={14} className={isActive ? "text-purple-400" : "text-[#595959]"} />
                <div className="truncate flex-1 flex flex-col gap-0.5">
                  <div className="truncate font-medium">{sid}</div>
                  <div className="text-[9px] text-[#595959] flex items-center gap-1 opacity-70">
                    <Clock size={10} />
                    {new Date(s.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  </div>
                </div>
              </button>

              {onDeleteSession && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(sid);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded hover:bg-red-500/10 text-[#595959] hover:text-red-400 transition-all ml-1"
                  title="Delete Session"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          );
        })}
        {sessions.length === 0 && (
          <div className="p-8 text-center text-[#434343]">
            <HistoryIcon size={20} className="mx-auto mb-2 opacity-30" />
            <p className="text-[10px] font-medium tracking-tight">Empty Workspace</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SessionSidebar;
