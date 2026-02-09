import { useState, useCallback } from 'react';
import { Editor } from '@tiptap/react';
import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8001';

interface AIGenerationOptions {
  prompt: string;
  context?: string;
  position?: number; // Position in editor to insert generated content
}

export const useAIGeneration = (editor: Editor | null) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateText = useCallback(async (options: AIGenerationOptions) => {
    if (!editor) {
      setError('Editor not available');
      return;
    }

    setIsGenerating(true);
    setError(null);

    try {
      // Call backend AI endpoint
      const response = await axios.post(`${API_BASE_URL}/ai/generate`, {
        prompt: options.prompt,
        context: options.context || editor.getText(),
        position: options.position || editor.state.selection.$from.pos,
      });

      const generatedText = response.data.text;

      // Insert generated text at cursor position
      if (options.position !== undefined) {
        editor.chain().focus().insertContentAt(options.position, generatedText).run();
      } else {
        editor.chain().focus().insertContent(generatedText).run();
      }

      return generatedText;
    } catch (err: any) {
      const errorMsg = err.response?.data?.error || err.message || 'Failed to generate text';
      setError(errorMsg);
      throw err;
    } finally {
      setIsGenerating(false);
    }
  }, [editor]);

  const improveSelection = useCallback(async () => {
    if (!editor) return;

    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to);

    if (!selectedText.trim()) {
      setError('Please select some text to improve');
      return;
    }

    return generateText({
      prompt: `Improve and enhance the following text while maintaining its meaning: ${selectedText}`,
      context: editor.getText(),
      position: from,
    });
  }, [editor, generateText]);

  const expandSelection = useCallback(async () => {
    if (!editor) return;

    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to);

    if (!selectedText.trim()) {
      setError('Please select some text to expand');
      return;
    }

    return generateText({
      prompt: `Expand and elaborate on the following text: ${selectedText}`,
      context: editor.getText(),
      position: to,
    });
  }, [editor, generateText]);

  const summarizeSelection = useCallback(async () => {
    if (!editor) return;

    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to);

    if (!selectedText.trim()) {
      setError('Please select some text to summarize');
      return;
    }

    return generateText({
      prompt: `Summarize the following text concisely: ${selectedText}`,
      context: editor.getText(),
      position: from,
    });
  }, [editor, generateText]);

  return {
    generateText,
    improveSelection,
    expandSelection,
    summarizeSelection,
    isGenerating,
    error,
  };
};
