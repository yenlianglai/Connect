import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { Send, Bot, X, Hash, Sparkles } from 'lucide-react';
import { chatStream, createTopic, getSessionHistory, type Node as MnemoNode } from '../api';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Static empty state component - hoisted outside to prevent re-creation
const EmptyState: React.FC<{ selectedCategoryCount: number }> = ({ selectedCategoryCount }) => (
  <div className="h-full flex flex-col items-center justify-center text-[#434343] gap-6">
    <div className="p-6 rounded-3xl bg-[#1a1a1a] border border-[#2d2d2d]">
      <Sparkles size={48} strokeWidth={1.5} className="text-[#262626]" />
    </div>
    <div className="text-center space-y-2">
      <p className="text-xl lg:text-2xl font-semibold text-[#d4d4d4]">How can I help you today?</p>
      {selectedCategoryCount > 0 && (
        <p className="text-base text-[#8c8c8c]">
          Searching in {selectedCategoryCount} categor{selectedCategoryCount === 1 ? 'y' : 'ies'}
        </p>
      )}
    </div>
  </div>
);

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatProps {
  sessionId: string;
  setSessionId: (id: string) => void;
  onNewMessage: () => void;
  onRetrievedNodes?: (ids: string[]) => void;
  onSessionCreated?: (id: string) => void;
  initialTopicName?: string;
  initialParentId?: string;
  availableCategories?: MnemoNode[];
}

const Chat: React.FC<ChatProps> = ({ 
  sessionId, 
  setSessionId, 
  onNewMessage, 
  onRetrievedNodes,
  onSessionCreated,
  initialTopicName, 
  initialParentId,
  availableCategories = []
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<string[]>([]);
  const [showCategorySelector, setShowCategorySelector] = useState(false);
  const [categorySearchQuery, setCategorySearchQuery] = useState('');
  
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Sync props if they change
  useEffect(() => {
    if (initialTopicName) {
      // New session flow - will be handled by first message
    }
  }, [initialTopicName, initialParentId]);

  useEffect(() => {
    const loadHistory = async () => {
      if (sessionId) {
        setIsLoading(true);
        try {
          const data = await getSessionHistory(sessionId, 20);
          if (data && data.messages) {
            setMessages(data.messages);
          }
        } catch (error) {
          console.error('Failed to load history:', error);
        } finally {
          setIsLoading(false);
        }
      } else {
        setMessages([]);
      }
    };
    loadHistory();
  }, [sessionId]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const filteredCategories = useMemo(() => {
    if (!categorySearchQuery) return availableCategories;
    const query = categorySearchQuery.toLowerCase();
    return availableCategories.filter(cat => 
      cat.name?.toLowerCase().includes(query) ||
      cat.id.toLowerCase().includes(query)
    );
  }, [availableCategories, categorySearchQuery]);

  const toggleCategory = useCallback((categoryId: string) => {
    setSelectedCategoryIds(prev => 
      prev.includes(categoryId)
        ? prev.filter(id => id !== categoryId)
        : [...prev, categoryId]
    );
  }, []);

  const handleSend = useCallback(async () => {
    if (!input.trim() || isLoading) return;

    const userMsg = input;
    setInput('');
    
    const isNewSession = !sessionId;
    let activeSessionId = sessionId;
    
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
    setIsLoading(true);

    // Add placeholder assistant message for streaming
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

    try {
      if (isNewSession && initialTopicName) {
        const topicResponse = await createTopic({
          topic_name: initialTopicName,
          parent_category_id: initialParentId || 'cat_root',
          initial_sub_categories: undefined
        });
        activeSessionId = topicResponse.session_id;
        setSessionId(activeSessionId);
        onSessionCreated?.(activeSessionId);
      } else if (isNewSession) {
        activeSessionId = `session_${Math.random().toString(36).substr(2, 12)}`;
      }
      
      await chatStream(
        userMsg,
        activeSessionId,
        selectedCategoryIds.length > 0 ? selectedCategoryIds : undefined,
        // onChunk: append each chunk to the last assistant message
        (chunk: string) => {
          setMessages((prev) => {
            const newMessages = [...prev];
            const lastIndex = newMessages.length - 1;
            if (lastIndex >= 0 && newMessages[lastIndex].role === 'assistant') {
              newMessages[lastIndex] = {
                ...newMessages[lastIndex],
                content: newMessages[lastIndex].content + chunk,
              };
            }
            return newMessages;
          });
        },
        // onMetadata: handle session ID and retrieved nodes
        (metadata) => {
          if (isNewSession && !initialTopicName) {
            setSessionId(metadata.session_id);
          }
          if (metadata.retrieved_node_ids) {
            onRetrievedNodes?.(metadata.retrieved_node_ids);
          }
        },
        // onError: handle errors
        (errorMsg: string) => {
          setMessages((prev) => {
            const newMessages = [...prev];
            const lastIndex = newMessages.length - 1;
            if (lastIndex >= 0 && newMessages[lastIndex].role === 'assistant') {
              newMessages[lastIndex] = {
                ...newMessages[lastIndex],
                content: `Error: ${errorMsg}`,
              };
            }
            return newMessages;
          });
        }
      );
      
      onNewMessage();
    } catch (error: unknown) {
      const errorMsg = error instanceof Error 
        ? error.message 
        : (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Unknown error';
      setMessages((prev) => {
        const newMessages = [...prev];
        const lastIndex = newMessages.length - 1;
        if (lastIndex >= 0 && newMessages[lastIndex].role === 'assistant') {
          newMessages[lastIndex] = {
            ...newMessages[lastIndex],
            content: `Error: ${errorMsg}`,
          };
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [input, isLoading, sessionId, initialTopicName, initialParentId, selectedCategoryIds, onSessionCreated, onRetrievedNodes, onNewMessage, setSessionId]);

  const selectedCategories = useMemo(() => {
    return availableCategories.filter(cat => selectedCategoryIds.includes(cat.id));
  }, [availableCategories, selectedCategoryIds]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  }, []);

  const handleInputKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Don't submit if user is composing text with IME (e.g., 注音, Japanese, Korean)
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  return (
    <div className="flex flex-col h-full bg-[#171717]">
      {/* Category Selector Bar - Show always if categories are available */}
      {availableCategories.length > 0 && (
        <div className="px-4 lg:px-6 py-3 border-b border-[#2d2d2d] bg-[#1a1a1a] flex items-center gap-3 overflow-x-auto custom-scrollbar">
          <button
            onClick={() => setShowCategorySelector(!showCategorySelector)}
            className={cn(
              "shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg text-base font-semibold transition-all",
              showCategorySelector
                ? "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                : "bg-[#262626] text-[#8c8c8c] hover:text-[#d4d4d4] border border-[#2d2d2d]"
            )}
          >
            <Hash size={20} />
            <span>Sources</span>
            {selectedCategoryIds.length > 0 && (
              <span className="px-2 py-1 bg-purple-500/30 rounded text-sm font-medium">
                {selectedCategoryIds.length}
              </span>
            )}
          </button>
          
          {/* Selected Categories as Chips */}
          {selectedCategories.map(cat => (
            <div
              key={cat.id}
              className="shrink-0 flex items-center gap-2 px-3 py-2 bg-purple-500/10 border border-purple-500/20 rounded-lg text-sm text-purple-300"
            >
              <span className="font-medium">{cat.name || cat.id}</span>
              <button
                onClick={() => toggleCategory(cat.id)}
                className="hover:text-purple-100 transition-colors"
              >
                <X size={16} />
              </button>
            </div>
          ))}
          
          {selectedCategoryIds.length === 0 && (
            <span className="text-sm text-[#595959] italic ml-2">
              Searching entire graph
            </span>
          )}
        </div>
      )}

      {/* Category Dropdown */}
      {showCategorySelector && availableCategories.length > 0 && (
        <div className="px-4 lg:px-6 py-4 border-b border-[#2d2d2d] bg-[#1a1a1a] animate-in slide-in-from-top-2 duration-200">
          <div className="relative mb-3">
            <input
              type="text"
              value={categorySearchQuery}
              onChange={(e) => setCategorySearchQuery(e.target.value)}
              placeholder="Search categories..."
              className="w-full bg-[#262626] border border-[#2d2d2d] rounded-lg px-4 py-2.5 text-base text-[#d4d4d4] placeholder-[#595959] focus:border-purple-500/50 outline-none transition-colors"
              autoFocus
            />
          </div>
          <div className="max-h-48 overflow-y-auto custom-scrollbar space-y-1.5">
            {filteredCategories.map(cat => (
              <button
                key={cat.id}
                onClick={() => toggleCategory(cat.id)}
                className={cn(
                  "w-full text-left px-4 py-2.5 rounded-lg text-base transition-all flex items-center justify-between",
                  selectedCategoryIds.includes(cat.id)
                    ? "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                    : "hover:bg-[#262626] text-[#8c8c8c]"
                )}
              >
                <span className="font-medium">{cat.name || cat.id}</span>
                {cat.level !== undefined && (
                  <span className="text-sm font-mono opacity-40">L{cat.level}</span>
                )}
              </button>
            ))}
            {filteredCategories.length === 0 && (
              <div className="p-4 text-sm text-[#595959] text-center italic">
                No categories found
              </div>
            )}
          </div>
        </div>
      )}

      {/* Messages Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 lg:px-8 xl:px-12 py-8 lg:py-12 space-y-8 custom-scrollbar">
        {messages.length === 0 && !isLoading && (
          <EmptyState selectedCategoryCount={selectedCategoryIds.length} />
        )}
        
        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "flex gap-4 lg:gap-6 max-w-4xl",
              msg.role === 'user' ? "ml-auto flex-row-reverse" : "mr-auto"
            )}
          >
            {/* Avatar */}
            <div className={cn(
              "shrink-0 w-10 h-10 lg:w-12 lg:h-12 rounded-full flex items-center justify-center",
              msg.role === 'user' 
                ? "bg-[#262626] border border-[#2d2d2d]" 
                : "bg-purple-500/10 border border-purple-500/20"
            )}>
              {msg.role === 'user' ? (
                <span className="text-base lg:text-lg font-bold text-[#d4d4d4]">U</span>
              ) : (
                <Bot size={22} className="lg:w-6 lg:h-6 text-purple-400" />
              )}
            </div>
            
            {/* Message Content */}
            <div className={cn(
              "flex-1 rounded-2xl px-6 py-4 lg:px-8 lg:py-5",
              msg.role === 'user'
                ? "bg-[#262626] text-[#d4d4d4] border border-[#2d2d2d]"
                : "bg-[#1a1a1a] text-[#d4d4d4]"
            )}>
              {msg.role === 'assistant' && !msg.content && isLoading ? (
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                  <div className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                  <div className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce"></div>
                </div>
              ) : (
                <div className="prose prose-invert prose-lg max-w-none">
                  <p className="text-base lg:text-lg leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                </div>
              )}
            </div>
          </div>
        ))}
        
        {/* Only show loading indicator if last message is not an assistant message (streaming) */}
        {isLoading && (!messages.length || messages[messages.length - 1]?.role !== 'assistant') && (
          <div className="flex gap-4 lg:gap-6 max-w-4xl mr-auto">
            <div className="shrink-0 w-10 h-10 lg:w-12 lg:h-12 rounded-full bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
              <Bot size={22} className="lg:w-6 lg:h-6 text-purple-400" />
            </div>
            <div className="flex-1 rounded-2xl px-6 py-4 lg:px-8 lg:py-5 bg-[#1a1a1a]">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce"></div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="px-4 lg:px-8 xl:px-12 py-4 lg:py-6 border-t border-[#2d2d2d] bg-[#171717]">
        <div className="max-w-4xl mx-auto">
          <div className="relative flex items-end bg-[#262626] border border-[#2d2d2d] rounded-2xl focus-within:border-purple-500/50 transition-all shadow-lg">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleInputKeyDown}
              placeholder="Message Mnemo..."
              rows={1}
              className="flex-1 bg-transparent px-6 py-4 lg:px-8 lg:py-5 text-base lg:text-lg text-[#d4d4d4] placeholder-[#595959] outline-none resize-none max-h-40 overflow-y-auto custom-scrollbar"
              style={{ minHeight: '32px' }}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className={cn(
                "m-2 lg:m-3 p-2.5 lg:p-3 rounded-lg transition-all",
                isLoading || !input.trim()
                  ? "text-[#434343] cursor-not-allowed"
                  : "text-[#8c8c8c] hover:text-[#d4d4d4] hover:bg-[#333333]"
              )}
            >
              <Send size={22} className="lg:w-6 lg:h-6" />
            </button>
          </div>
          <p className="mt-3 text-sm text-[#595959] text-center">
            {selectedCategoryIds.length > 0 
              ? `Searching ${selectedCategoryIds.length} categor${selectedCategoryIds.length === 1 ? 'y' : 'ies'}. Press Enter to send, Shift+Enter for new line.`
              : "Searching entire graph. Press Enter to send, Shift+Enter for new line."
            }
          </p>
        </div>
      </div>
    </div>
  );
};

export default Chat;
