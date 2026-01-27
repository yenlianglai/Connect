import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import TextAlign from '@tiptap/extension-text-align';
import Color from '@tiptap/extension-color';
import { TextStyle } from '@tiptap/extension-text-style';
import Highlight from '@tiptap/extension-highlight';
import Underline from '@tiptap/extension-underline';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import FloatingMenu from '@tiptap/extension-floating-menu';
import BubbleMenu from '@tiptap/extension-bubble-menu';
import DragHandle from '@tiptap/extension-drag-handle';
import Dropcursor from '@tiptap/extension-dropcursor';
import Gapcursor from '@tiptap/extension-gapcursor';
import { createLowlight, all } from 'lowlight';
import { 
  Save, FileText, Sparkles, Hash, Plus, X, Info, Trash2, 
  Bold, Italic, Underline as UnderlineIcon, Strikethrough, Code,
  List, ListOrdered, Quote, Heading1, Heading2, Heading3,
  Image as ImageIcon, Table as TableIcon,
  AlignLeft, AlignCenter, Undo, Redo
} from 'lucide-react';
import { type Node as MnemoNode, updateKnowledgeNode, updateCategoryNode, createKnowledgeNode, deleteNode } from '../api';
import { toast } from 'react-hot-toast';
import { useAIGeneration } from '../hooks/useAIGeneration';
import { marked } from 'marked';
import './TiptapStyles.css';

// Create lowlight instance with all languages
const lowlight = createLowlight(all);

interface TiptapEditorProps {
  selectedNode: MnemoNode | null;
  onNodeUpdated?: () => void;
  currentFocusId?: string;
  onSelectNode?: (nodeId: string) => void;
  onNodeDeleted?: () => void;
}

const TiptapEditor: React.FC<TiptapEditorProps> = ({ 
  selectedNode, 
  onNodeUpdated, 
  currentFocusId, 
  onSelectNode, 
  onNodeDeleted 
}) => {
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [slashMenuPos, setSlashMenuPos] = useState({ top: 0, left: 0 });
  const [selectedSlashIndex, setSelectedSlashIndex] = useState(0);
  const slashMenuRef = useRef<HTMLDivElement>(null);
  const selectedSlashIndexRef = useRef(0);
  const showSlashMenuRef = useRef(false);

  // Define slash commands before editor (needed for keyboard handlers)
  const slashCommands = [
    { type: 'heading1', label: 'Heading 1', icon: Heading1 },
    { type: 'heading2', label: 'Heading 2', icon: Heading2 },
    { type: 'heading3', label: 'Heading 3', icon: Heading3 },
    { type: 'bullet', label: 'Bullet List', icon: List },
    { type: 'ordered', label: 'Numbered List', icon: ListOrdered },
    { type: 'task', label: 'Task List', icon: List },
    { type: 'quote', label: 'Quote', icon: Quote },
    { type: 'code', label: 'Code Block', icon: Code },
    { type: 'table', label: 'Table', icon: TableIcon },
    { type: 'image', label: 'Image', icon: ImageIcon },
    { type: 'divider', label: 'Divider', icon: X },
    { type: 'ai-improve', label: '✨ AI: Improve Selection', icon: Sparkles, ai: true },
    { type: 'ai-expand', label: '✨ AI: Expand Selection', icon: Sparkles, ai: true },
    { type: 'ai-summarize', label: '✨ AI: Summarize Selection', icon: Sparkles, ai: true },
  ];

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3, 4],
        },
        codeBlock: false, // We'll use CodeBlockLowlight instead
      }),
      Placeholder.configure({
        placeholder: 'Type "/" for commands, or start writing...',
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          class: 'text-purple-400 hover:text-purple-300 underline',
        },
      }),
      Image.configure({
        HTMLAttributes: {
          class: 'max-w-full rounded-lg',
        },
      }),
      CodeBlockLowlight.configure({
        lowlight,
        defaultLanguage: 'typescript',
      }),
      Table.configure({
        resizable: true,
        HTMLAttributes: {
          class: 'border-collapse border border-[#2d2d2d]',
        },
      }),
      TableRow,
      TableHeader,
      TableCell,
      TextAlign.configure({
        types: ['heading', 'paragraph'],
      }),
      Color,
      TextStyle,
      Highlight.configure({
        multicolor: true,
      }),
      Underline,
      Subscript,
      Superscript,
      TaskList,
      TaskItem.configure({
        nested: true,
      }),
      FloatingMenu,
      BubbleMenu,
      DragHandle,
      Dropcursor,
      Gapcursor,
    ],
    content: '',
    editorProps: {
      attributes: {
        class: 'prose prose-invert max-w-none min-h-[500px] focus:outline-none px-4 py-8',
        'data-placeholder': 'Type "/" for commands, or start writing...',
      },
      handleKeyDown: (_view: any, event: KeyboardEvent) => {
        // Handle Escape to close slash menu
        if (event.key === 'Escape' && showSlashMenuRef.current) {
          setShowSlashMenu(false);
          setSelectedSlashIndex(0);
          selectedSlashIndexRef.current = 0;
          return true;
        }
        // Handle Arrow keys for slash menu navigation
        if (showSlashMenuRef.current && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
          event.preventDefault();
          const cmdCount = slashCommands.length;
          const currentIndex = selectedSlashIndexRef.current;
          const newIndex = event.key === 'ArrowDown' 
            ? (currentIndex + 1) % cmdCount
            : (currentIndex - 1 + cmdCount) % cmdCount;
          setSelectedSlashIndex(newIndex);
          selectedSlashIndexRef.current = newIndex;
          return true;
        }
        // Handle Enter to select from slash menu
        if (event.key === 'Enter' && showSlashMenuRef.current) {
          event.preventDefault();
          const selectedCmd = slashCommands[selectedSlashIndexRef.current];
          if (selectedCmd && insertBlockRef.current) {
            insertBlockRef.current(selectedCmd.type);
          }
          return true;
        }
        return false;
      },
    },
    onUpdate: ({ editor }: { editor: any }) => {
      // Handle slash command detection
      const { state } = editor;
      const { selection } = state;
      const { $from } = selection;
      
      // Get text from the current line
      const lineStart = $from.start();
      const lineText = state.doc.textBetween(lineStart, $from.pos, '');
      
      if (lineText.endsWith('/') && lineText.length > 0) {
        // Get cursor position for menu placement
        const coords = editor.view.coordsAtPos($from.pos);
        setSlashMenuPos({ top: coords.top + window.scrollY, left: coords.left + window.scrollX });
        setShowSlashMenu(true);
        setSelectedSlashIndex(0);
        showSlashMenuRef.current = true;
        selectedSlashIndexRef.current = 0;
      } else if (showSlashMenuRef.current && !lineText.endsWith('/')) {
        setShowSlashMenu(false);
        setSelectedSlashIndex(0);
        showSlashMenuRef.current = false;
        selectedSlashIndexRef.current = 0;
      }
    },
    onSelectionUpdate: ({ editor }: { editor: any }) => {
      // Also check on selection changes
      const { state } = editor;
      const { selection } = state;
      const { $from } = selection;
      
      const lineStart = $from.start();
      const lineText = state.doc.textBetween(lineStart, $from.pos, '');
      
      if (lineText.endsWith('/') && lineText.length > 0) {
        const coords = editor.view.coordsAtPos($from.pos);
        setSlashMenuPos({ top: coords.top + window.scrollY, left: coords.left + window.scrollX });
        setShowSlashMenu(true);
        setSelectedSlashIndex(0);
        showSlashMenuRef.current = true;
        selectedSlashIndexRef.current = 0;
      } else if (showSlashMenuRef.current && !lineText.endsWith('/')) {
        setShowSlashMenu(false);
        setSelectedSlashIndex(0);
        showSlashMenuRef.current = false;
        selectedSlashIndexRef.current = 0;
      }
    },
  });

  // AI Generation hook (after editor is created)
  const aiGeneration = useAIGeneration(editor);

  // Markdown converter (for HTML to Markdown export) - available if needed
  // const turndownService = new TurndownService({
  //   headingStyle: 'atx',
  //   codeBlockStyle: 'fenced',
  // });

  useEffect(() => {
    if (selectedNode && editor) {
      setTitle(selectedNode.name || selectedNode.description || '');
      setTags(selectedNode.tags || []);
      
      const initialContent = selectedNode.type === 'category' 
        ? selectedNode.summary 
        : selectedNode.content;
      
      if (initialContent) {
        try {
          // Check if content looks like HTML
          if (initialContent.trim().startsWith('<')) {
            editor.commands.setContent(initialContent);
          } else {
            // Try to parse as markdown and convert to HTML
            try {
              const htmlContent = marked.parse(initialContent, { breaks: true, gfm: true });
              editor.commands.setContent(htmlContent as string);
            } catch {
              // If markdown parsing fails, wrap as plain text
              editor.commands.setContent(`<p>${initialContent}</p>`);
            }
          }
        } catch {
          // Fallback to plain text
          editor.commands.setContent(`<p>${initialContent}</p>`);
        }
      } else {
        editor.commands.clearContent();
      }
    } else if (editor) {
      setTitle('');
      setTags([]);
      editor.commands.clearContent();
    }
  }, [selectedNode, editor]);

  const handleCreateNew = async () => {
    setIsCreating(true);
    const tid = toast.loading('Creating new note...');
    try {
      const result = await createKnowledgeNode({
        description: "Untitled Note",
        content: "<p></p>",
        parent_id: currentFocusId !== 'cat_root' ? currentFocusId : undefined
      });
      toast.success('Empty note created', { id: tid });
      if (onNodeUpdated) onNodeUpdated();
      if (onSelectNode) onSelectNode(result.id);
    } catch (error) {
      toast.error('Failed to create note', { id: tid });
    } finally {
      setIsCreating(false);
    }
  };

  const handleSave = async () => {
    if (!selectedNode || !editor) return;
    setIsSaving(true);
    
    try {
      // Save as HTML (can be converted to markdown on backend if needed)
      const htmlContent = editor.getHTML();
      
      // Optionally convert to markdown for storage
      // const markdownContent = turndownService.turndown(htmlContent);
      
      if (selectedNode.type === 'category') {
        await updateCategoryNode(selectedNode.id, title, htmlContent);
      } else {
        await updateKnowledgeNode(selectedNode.id, htmlContent, title, tags);
      }
      toast.success('Saved to memory');
      if (onNodeUpdated) onNodeUpdated();
    } catch (error) {
      toast.error('Failed to save');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedNode) return;
    
    if (selectedNode.id === 'cat_root') {
      toast.error('Cannot delete the root node');
      return;
    }

    const confirmed = window.confirm(
      `Are you sure you want to delete "${selectedNode.name || selectedNode.description || selectedNode.id}"?\n\nThis will permanently delete the node and all its relationships.`
    );

    if (!confirmed) return;

    setIsDeleting(true);
    const tid = toast.loading('Deleting node...');
    try {
      await deleteNode(selectedNode.id);
      toast.success('Node deleted successfully', { id: tid });
      if (onNodeUpdated) onNodeUpdated();
      if (onNodeDeleted) onNodeDeleted();
      if (onSelectNode) onSelectNode('');
    } catch (error: any) {
      const errorMsg = error.response?.data?.error || error.message || 'Failed to delete node';
      toast.error(errorMsg, { id: tid });
    } finally {
      setIsDeleting(false);
    }
  };

  const addTag = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && tagInput.trim()) {
      e.preventDefault();
      const newTag = tagInput.trim().replace(/^#/, '');
      if (!tags.includes(newTag)) {
        setTags([...tags, newTag]);
      }
      setTagInput('');
    }
  };

  const removeTag = (tagToRemove: string) => {
    setTags(tags.filter(t => t !== tagToRemove));
  };

  // Slash command handlers
  const insertBlock = useCallback((type: string) => {
    if (!editor) return;
    
    setShowSlashMenu(false);
    setSelectedSlashIndex(0);
    showSlashMenuRef.current = false;
    selectedSlashIndexRef.current = 0;
    
    // Remove the "/" character
    editor.commands.deleteRange({
      from: editor.state.selection.$from.pos - 1,
      to: editor.state.selection.$from.pos,
    });

    switch (type) {
      case 'heading1':
        editor.chain().focus().toggleHeading({ level: 1 }).run();
        break;
      case 'heading2':
        editor.chain().focus().toggleHeading({ level: 2 }).run();
        break;
      case 'heading3':
        editor.chain().focus().toggleHeading({ level: 3 }).run();
        break;
      case 'bullet':
        editor.chain().focus().toggleBulletList().run();
        break;
      case 'ordered':
        editor.chain().focus().toggleOrderedList().run();
        break;
      case 'task':
        editor.chain().focus().toggleTaskList().run();
        break;
      case 'quote':
        editor.chain().focus().toggleBlockquote().run();
        break;
      case 'code':
        editor.chain().focus().toggleCodeBlock().run();
        break;
      case 'table':
        editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
        break;
      case 'image':
        const url = window.prompt('Enter image URL:');
        if (url) {
          editor.chain().focus().setImage({ src: url }).run();
        }
        break;
      case 'divider':
        editor.chain().focus().setHorizontalRule().run();
        break;
      case 'ai-improve':
        aiGeneration.improveSelection().catch((err) => {
          toast.error(err.message || 'Failed to improve text');
        });
        break;
      case 'ai-expand':
        aiGeneration.expandSelection().catch((err) => {
          toast.error(err.message || 'Failed to expand text');
        });
        break;
      case 'ai-summarize':
        aiGeneration.summarizeSelection().catch((err) => {
          toast.error(err.message || 'Failed to summarize text');
        });
        break;
      default:
        break;
    }
  }, [editor, aiGeneration]);

  // Store insertBlock in ref for keyboard handler
  const insertBlockRef = useRef(insertBlock);
  useEffect(() => {
    insertBlockRef.current = insertBlock;
  }, [insertBlock]);

  if (!selectedNode) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-[#434343] p-12 text-center space-y-6 bg-[#0d0d0d]">
        <div className="p-6 rounded-3xl bg-[#141414] border border-[#262626] shadow-2xl shadow-black/50">
          <FileText size={48} className="text-[#262626]" />
        </div>
        <div className="space-y-2">
          <h3 className="text-lg font-bold text-[#8c8c8c] uppercase tracking-widest italic">Create New Node</h3>
          <p className="text-sm text-[#595959] max-w-[300px] leading-relaxed">
            Create a new knowledge node or category to expand your graph.
          </p>
        </div>
        <button
          onClick={handleCreateNew}
          disabled={isCreating}
          className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-900/50 text-white rounded-xl text-sm font-semibold transition-all active:scale-95 group shadow-lg shadow-purple-900/20"
        >
          {isCreating ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Plus size={18} className="group-hover:rotate-90 transition-transform duration-300" />
          )}
          <span>{isCreating ? 'Creating...' : 'Create New Note'}</span>
        </button>
      </div>
    );
  }

  if (!editor) {
    return <div>Loading editor...</div>;
  }

  return (
    <div className="h-full flex flex-col bg-[#0d0d0d] overflow-hidden">
      {/* Editor Header */}
      <div className="px-8 py-6 border-b border-[#2d2d2d] bg-[#111111] space-y-4">
        <div className="flex justify-between items-center gap-6">
          <div className="flex-1 flex items-center gap-4 min-w-0">
            <div className={`shrink-0 p-2.5 rounded-xl border ${
              selectedNode.type === 'category' 
                ? 'bg-blue-500/10 border-blue-500/20 text-blue-400' 
                : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
            }`}>
              {selectedNode.type === 'category' ? <Hash size={20} /> : <Sparkles size={20} />}
            </div>
            <div className="flex-1 min-w-0">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Enter title..."
                className="bg-transparent text-2xl font-bold text-[#d4d4d4] outline-none border-none placeholder:text-[#434343] w-full"
              />
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <div className="text-[10px] text-[#595959] uppercase tracking-tighter font-mono mr-2">
                  ID: {selectedNode.id} • {selectedNode.type}
                </div>
                
                {selectedNode.type === 'knowledge' && (
                  <>
                    {tags.map(tag => (
                      <span key={tag} className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 text-[10px] font-medium group">
                        #{tag}
                        <button onClick={() => removeTag(tag)} className="hover:text-purple-200 transition-colors">
                          <X size={10} />
                        </button>
                      </span>
                    ))}
                    <input
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={addTag}
                      placeholder="+ Add tag..."
                      className="bg-transparent text-[10px] text-[#8c8c8c] outline-none border-none placeholder:text-[#434343] min-w-[70px]"
                    />
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDelete}
              disabled={isDeleting || selectedNode.id === 'cat_root'}
              className="flex items-center gap-2 px-4 py-2 bg-red-500/10 hover:bg-red-500/20 disabled:bg-red-900/20 disabled:opacity-50 text-red-400 hover:text-red-300 border border-red-500/20 rounded-xl text-xs font-bold transition-all active:scale-95"
              title={selectedNode.id === 'cat_root' ? 'Cannot delete root node' : 'Delete node'}
            >
              {isDeleting ? (
                <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
              ) : (
                <Trash2 size={14} />
              )}
              <span>Delete</span>
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-900/50 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-purple-900/20 active:scale-95"
            >
              {isSaving ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Save size={14} />}
              <span>Save</span>
            </button>
          </div>
        </div>

        {/* Toolbar */}
        {selectedNode.type === 'knowledge' && (
          <div className="flex items-center gap-1 flex-wrap">
            <button
              onClick={() => editor.chain().focus().toggleBold().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('bold') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <Bold size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleItalic().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('italic') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <Italic size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleUnderline().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('underline') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <UnderlineIcon size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleStrike().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('strike') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <Strikethrough size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleCode().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('code') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <Code size={16} />
            </button>
            <div className="w-px h-6 bg-[#2d2d2d] mx-1" />
            <button
              onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('heading', { level: 1 }) ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <Heading1 size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('heading', { level: 2 }) ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <Heading2 size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleBulletList().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('bulletList') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <List size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleOrderedList().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('orderedList') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <ListOrdered size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().toggleBlockquote().run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive('blockquote') ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <Quote size={16} />
            </button>
            <div className="w-px h-6 bg-[#2d2d2d] mx-1" />
            <button
              onClick={() => editor.chain().focus().setTextAlign('left').run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive({ textAlign: 'left' }) ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <AlignLeft size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().setTextAlign('center').run()}
              className={`p-2 rounded hover:bg-[#262626] ${editor.isActive({ textAlign: 'center' }) ? 'bg-purple-500/20 text-purple-400' : 'text-[#8c8c8c]'}`}
            >
              <AlignCenter size={16} />
            </button>
            <div className="w-px h-6 bg-[#2d2d2d] mx-1" />
            <button
              onClick={() => editor.chain().focus().undo().run()}
              disabled={!editor.can().undo()}
              className="p-2 rounded hover:bg-[#262626] text-[#8c8c8c] disabled:opacity-30"
            >
              <Undo size={16} />
            </button>
            <button
              onClick={() => editor.chain().focus().redo().run()}
              disabled={!editor.can().redo()}
              className="p-2 rounded hover:bg-[#262626] text-[#8c8c8c] disabled:opacity-30"
            >
              <Redo size={16} />
            </button>
          </div>
        )}
      </div>

      {/* Editor Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar relative">
        {selectedNode.type === 'knowledge' ? (
          <>
            <EditorContent editor={editor} />
            
            {/* Slash Command Menu */}
            {showSlashMenu && (
              <div
                ref={slashMenuRef}
                className="fixed z-50 bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg shadow-2xl p-2 min-w-[200px] max-h-[300px] overflow-y-auto"
                style={{
                  top: `${slashMenuPos.top + 20}px`,
                  left: `${slashMenuPos.left}px`,
                }}
              >
                {slashCommands.map((cmd, index) => {
                  const Icon = cmd.icon;
                  const isSelected = index === selectedSlashIndex;
                  return (
                    <button
                      key={cmd.type}
                      onClick={() => insertBlock(cmd.type)}
                      disabled={cmd.ai && aiGeneration.isGenerating}
                      className={`w-full flex items-center gap-3 px-3 py-2 rounded text-left text-sm transition-colors ${
                        isSelected 
                          ? 'bg-purple-500/20 border border-purple-500/30' 
                          : 'hover:bg-[#262626]'
                      } ${
                        cmd.ai 
                          ? 'text-purple-400 hover:text-purple-300' 
                          : 'text-[#d4d4d4] hover:text-white'
                      } ${aiGeneration.isGenerating && cmd.ai ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <Icon size={16} className={cmd.ai ? 'text-purple-400' : 'text-[#8c8c8c]'} />
                      <span>{cmd.label}</span>
                      {aiGeneration.isGenerating && cmd.ai && (
                        <div className="ml-auto w-4 h-4 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          <div className="space-y-6 p-8">
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-[#595959] uppercase tracking-widest">
                Abstract / Summary
              </label>
              <textarea
                value={editor.getText()}
                onChange={(e) => editor.commands.setContent(`<p>${e.target.value}</p>`)}
                placeholder="Describe this category..."
                className="w-full h-[400px] bg-[#0d0d0d] border border-[#2d2d2d] rounded-xl p-6 text-sm text-[#a3a3a3] leading-relaxed focus:outline-none focus:border-purple-500/50 transition-all resize-none"
              />
            </div>
            
            <div className="p-4 rounded-xl bg-blue-500/5 border border-blue-500/10 space-y-3">
              <div className="flex items-center gap-2 text-blue-400">
                <Info size={14} />
                <span className="text-[10px] font-bold uppercase tracking-widest">Category Insight</span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <div className="text-[9px] text-[#595959] uppercase">Hierarchy Level</div>
                  <div className="text-xs text-[#d4d4d4] font-mono">Level {selectedNode.level || 1}</div>
                </div>
                <div className="space-y-1">
                  <div className="text-[9px] text-[#595959] uppercase">Active Concepts</div>
                  <div className="text-xs text-[#d4d4d4] font-mono">{selectedNode.insert_counter || 0} nested</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TiptapEditor;
