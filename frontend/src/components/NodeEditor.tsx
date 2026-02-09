import React from 'react';
import TiptapEditor from './TiptapEditor';
import { type Node } from '../api';

interface NodeEditorProps {
  selectedNode: Node | null;
  onNodeUpdated?: () => void;
  currentFocusId?: string;
  onSelectNode?: (nodeId: string) => void;
  onNodeDeleted?: () => void;
}

const NodeEditor: React.FC<NodeEditorProps> = (props) => {
  return <TiptapEditor {...props} />;
};

export default NodeEditor;
