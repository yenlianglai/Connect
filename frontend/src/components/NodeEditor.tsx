import React, { useEffect, useState, useRef } from 'react';
import { 
  MDXEditor, 
  headingsPlugin, 
  listsPlugin, 
  quotePlugin, 
  thematicBreakPlugin, 
  markdownShortcutPlugin,
  toolbarPlugin,
  UndoRedo,
  BoldItalicUnderlineToggles,
  BlockTypeSelect,
  ListsToggle,
  Separator,
  linkPlugin,
  linkDialogPlugin,
  CreateLink,
  tablePlugin,
  InsertTable,
  codeBlockPlugin,
  InsertCodeBlock,
  codeMirrorPlugin,
  type MDXEditorMethods
} from '@mdxeditor/editor';
import '@mdxeditor/editor/style.css';
import { type Node as MnemoNode, updateKnowledgeNode, updateCategoryNode, createKnowledgeNode, deleteNode } from '../api';
import { toast } from 'react-hot-toast';
import { Save, FileText, Sparkles, Hash, Plus, X, Info, Trash2 } from 'lucide-react';

interface NodeEditorProps {
  selectedNode: MnemoNode | null;
  onNodeUpdated?: () => void;
  currentFocusId?: string;
  onSelectNode?: (nodeId: string) => void;
  onNodeDeleted?: () => void;
}

const NodeEditor: React.FC<NodeEditorProps> = ({ selectedNode, onNodeUpdated, currentFocusId, onSelectNode, onNodeDeleted }) => {
  const editorRef = useRef<MDXEditorMethods>(null);
  const [markdown, setMarkdown] = useState('');
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (selectedNode) {
      setTitle(selectedNode.name || selectedNode.description || '');
      setTags(selectedNode.tags || []);
      
      const initialMarkdown = selectedNode.type === 'category' 
        ? selectedNode.summary 
        : selectedNode.content; // Facts now use content field
          
      const md = initialMarkdown || '';
      setMarkdown(md);
      
      // Use ref to ensure the editor content is updated correctly
      if (editorRef.current) {
        editorRef.current.setMarkdown(md);
      }
    } else {
      setTitle('');
      setMarkdown('');
      if (editorRef.current) {
        editorRef.current.setMarkdown('');
      }
    }
  }, [selectedNode]);

  const handleCreateNew = async () => {
    setIsCreating(true);
    const tid = toast.loading('Creating new note...');
    try {
      const result = await createKnowledgeNode({
        description: "Untitled Note",
        content: "# Content\n\n",
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
    if (!selectedNode) return;
    setIsSaving(true);
    const currentMarkdown = editorRef.current?.getMarkdown() || markdown;
    try {
      if (selectedNode.type === 'category') {
        await updateCategoryNode(selectedNode.id, title, currentMarkdown);
      } else {
        // Both knowledge and facts use updateKnowledgeNode now
        await updateKnowledgeNode(selectedNode.id, currentMarkdown, title, tags);
      }
      toast.success('Saved to memory');
      if (onNodeUpdated) onNodeUpdated();
    } catch (error) {
      toast.error('Failed to save');
    } finally {
      setIsSaving(false);
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

  const handleDelete = async () => {
    if (!selectedNode) return;
    
    // Prevent deleting root node
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
      // Clear selection after deletion
      if (onSelectNode) onSelectNode('');
    } catch (error: any) {
      const errorMsg = error.response?.data?.error || error.message || 'Failed to delete node';
      toast.error(errorMsg, { id: tid });
    } finally {
      setIsDeleting(false);
    }
  };

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
      </div>

      {/* Editor Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-8 notion-editor-container">
        {selectedNode.type === 'knowledge' ? (
          <MDXEditor
            ref={editorRef}
            key={selectedNode.id} 
            markdown={markdown}
            onChange={setMarkdown}
            className="dark-theme dark-editor"
            contentEditableClassName="prose prose-invert max-w-none min-h-[500px]"
            plugins={[
              headingsPlugin({ allowedHeadingLevels: [1, 2, 3, 4] }),
              listsPlugin(),
              quotePlugin(),
              thematicBreakPlugin(),
              markdownShortcutPlugin(),
              linkPlugin(),
              linkDialogPlugin(),
              tablePlugin(),
              codeBlockPlugin({ defaultCodeBlockLanguage: 'typescript' }),
              codeMirrorPlugin({ codeBlockLanguages: { js: 'JavaScript', ts: 'TypeScript', py: 'Python', rust: 'Rust' } }),
              toolbarPlugin({
                toolbarContents: () => (
                  <div className="flex items-center gap-1 bg-[#1a1a1a] p-1 rounded-lg border border-[#2d2d2d] mb-4 sticky top-0 z-10 shadow-xl mdxeditor-toolbar overflow-x-auto max-w-full">
                    <BlockTypeSelect />
                    <Separator />
                    <BoldItalicUnderlineToggles />
                    <Separator />
                    <ListsToggle />
                    <Separator />
                    <CreateLink />
                    <InsertTable />
                    <InsertCodeBlock />
                    <Separator />
                    <UndoRedo />
                  </div>
                )
              })
            ]}
          />
        ) : (
          <div className="space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-[#595959] uppercase tracking-widest">
                {selectedNode.type === 'category' ? 'Abstract / Summary' : 'Content'}
              </label>
              <textarea
                value={markdown}
                onChange={(e) => setMarkdown(e.target.value)}
                placeholder={selectedNode.type === 'category' ? "Describe this category..." : "Enter content..."}
                className="w-full h-[400px] bg-[#0d0d0d] border border-[#2d2d2d] rounded-xl p-6 text-sm text-[#a3a3a3] leading-relaxed focus:outline-none focus:border-purple-500/50 transition-all resize-none"
              />
            </div>
            
            {selectedNode.type === 'category' && (
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
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default NodeEditor;
