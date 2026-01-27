import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
});

export interface Node {
  id: string;
  type: 'knowledge' | 'category' | 'fact'; // 'fact' kept for backward compat, but facts are now knowledge nodes
  session_id?: string;
  name?: string; // For categories
  summary?: string; // For categories
  tags?: string[]; // For knowledge (includes fact_type tags for facts: identity/preference/habit)
  description?: string; // For knowledge/facts
  content?: string; // For knowledge/facts (for facts, this is the fact text)
  worth_of_learning?: number;
  level?: number;
  insert_counter?: number;
  cat0?: string;
  created_at: string;
  is_hot?: boolean;
  parent_id?: string;
}

export interface Link {
  source: string;
  target: string;
  type: string; // The relationship_type (e.g., PART_OF, SOLVES)
  edge_label: string; // The Neo4j edge label (e.g., BELONGS_TO, RELATED)
}

export interface GraphData {
  nodes: Node[];
  links: Link[];
}

export interface ChatResponse {
  session_id: string;
  response: string;
  retrieved_node_ids?: string[];
}

export interface SessionMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface Session {
  session_id: string;
  messages: SessionMessage[];
  created_at: string;
  updated_at: string;
}

export interface CreateTopicRequest {
  topic_name: string;
  parent_category_id?: string;
  initial_sub_categories?: string[];
}

export interface CreateTopicResponse {
  session_id: string;
  category_id: string;
}

export const createTopic = async (data: CreateTopicRequest): Promise<CreateTopicResponse> => {
  const response = await api.post('/topics/create', {
    topic_name: data.topic_name,
    parent_category_id: data.parent_category_id || 'cat_root',
    initial_sub_categories: data.initial_sub_categories
  });
  return response.data;
};

export const chat = async (
  message: string, 
  session_id: string, // Required - session must exist
  category_ids?: string[] // Optional category IDs to scope search
): Promise<ChatResponse> => {
  const response = await api.post('/chat', { 
    message, 
    session_id,
    category_ids
  });
  return response.data;
};

export interface StreamChunk {
  type: 'metadata' | 'chunk' | 'done' | 'error';
  content?: string;
  session_id?: string;
  retrieved_node_ids?: string[];
  message?: string;
}

export const chatStream = async (
  message: string,
  session_id: string,
  category_ids: string[] | undefined,
  onChunk: (chunk: string) => void,
  onMetadata?: (metadata: { session_id: string; retrieved_node_ids?: string[] }) => void,
  onError?: (error: string) => void
): Promise<string> => {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      session_id,
      category_ids,
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullResponse = '';

  if (!reader) {
    throw new Error('No response body reader available');
  }

  while (true) {
    const { done, value } = await reader.read();
    
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data: StreamChunk = JSON.parse(line.slice(6));
          
          if (data.type === 'metadata') {
            onMetadata?.({
              session_id: data.session_id || session_id,
              retrieved_node_ids: data.retrieved_node_ids,
            });
          } else if (data.type === 'chunk' && data.content) {
            fullResponse += data.content;
            onChunk(data.content);
          } else if (data.type === 'done') {
            return fullResponse;
          } else if (data.type === 'error') {
            const errorMsg = data.message || 'Unknown error';
            onError?.(errorMsg);
            throw new Error(errorMsg);
          }
        } catch (e) {
          console.error('Error parsing SSE data:', e);
        }
      }
    }
  }

  return fullResponse;
};

export const extractContext = async (session_id: string) => {
  const response = await api.post(`/extract/${session_id}`);
  return response.data;
};

export const refreshMemory = async (session_id: string) => {
  const response = await api.post(`/refresh/${session_id}`);
  return response.data;
};

export const triggerEvolution = async (category_id?: string) => {
  const response = await api.post('/evolve', null, { params: { category_id } });
  return response.data;
};

export const getGraphData = async (session_id?: string): Promise<GraphData> => {
  const response = await api.get('/graph/data', { params: { session_id } });
  return response.data;
};

export const getSessionHistory = async (session_id: string, limit: number = 20) => {
  const response = await api.get(`/sessions/${session_id}`, { params: { limit } });
  return response.data;
};

export const getActiveNodes = async (session_id: string) => {
  const response = await api.get(`/sessions/${session_id}/active-nodes`);
  return response.data;
};

export const getAllSessions = async () => {
  const response = await api.get('/sessions');
  return response.data;
};

export const updateKnowledgeNode = async (node_id: string, content: string, description?: string, tags?: string[]) => {
  const response = await api.patch(`/nodes/knowledge/${node_id}`, { content, description, tags });
  return response.data;
};

export const updateCategoryNode = async (category_id: string, name?: string, summary?: string) => {
  const response = await api.patch(`/nodes/category/${category_id}`, { name, summary });
  return response.data;
};

// Facts are now KnowledgeNodes - use updateKnowledgeNode instead
export const updateFactNode = async (node_id: string, content: string) => {
  // For backward compatibility, map to updateKnowledgeNode
  return updateKnowledgeNode(node_id, content, content);
};

export const createKnowledgeNode = async (data: { description: string; content: string; parent_id?: string; session_id?: string }) => {
  const response = await api.post('/nodes/knowledge', data);
  return response.data;
};

export const createCategoryNode = async (data: { name: string; summary: string; parent_id?: string; level?: number }) => {
  const response = await api.post('/nodes/category', data);
  return response.data;
};

export const deleteNode = async (node_id: string) => {
  const response = await api.delete(`/nodes/${node_id}`);
  return response.data;
};

export const createLink = async (source_id: string, target_id: string, rel_type: string) => {
  const response = await api.post('/links', { source_id, target_id, rel_type });
  return response.data;
};

export const deleteLink = async (source_id: string, target_id: string, rel_type: string) => {
  const response = await api.delete('/links', { params: { source_id, target_id, rel_type } });
  return response.data;
};

export const deleteSession = async (session_id: string) => {
  const response = await api.delete(`/sessions/${session_id}`);
  return response.data;
};

export default api;

