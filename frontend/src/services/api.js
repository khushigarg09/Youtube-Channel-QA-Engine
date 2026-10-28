import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_URL 
  ? (import.meta.env.VITE_API_URL.endsWith('/api') ? import.meta.env.VITE_API_URL : `${import.meta.env.VITE_API_URL}/api`)
  : 'http://localhost:8000/api';

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const apiService = {
  // Index a channel (supports optional custom_topics and bounded scope)
  indexChannel: async (url, customTopics = null, scope = 'latest_20') => {
    const payload = { url, scope };
    if (customTopics && customTopics.length > 0) {
      payload.custom_topics = customTopics;
    }
    const response = await client.post('/index-channel', payload);
    return response.data;
  },

  // Cancel channel indexing
  cancelIndexing: async (channelId) => {
    const response = await client.post('/cancel-indexing', { channel_id: channelId });
    return response.data;
  },

  // Re-index a single video
  reindexVideo: async (videoId, customTopics = null) => {
    const payload = customTopics ? { custom_topics: customTopics } : {};
    const response = await client.post(`/reindex-video/${videoId}`, payload);
    return response.data;
  },

  // Export channel data (JSON or CSV) and trigger browser download
  exportChannelData: async (channelId, format = 'json') => {
    const response = await client.get(`/export/${channelId}`, {
      params: { format },
      responseType: 'blob',
    });

    const blob = new Blob([response.data], {
      type: format === 'csv' ? 'text/csv' : 'application/json',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `channel_${channelId}_transcripts.${format}`);
    document.body.appendChild(link);
    link.click();
    link.parentNode.removeChild(link);
    window.URL.revokeObjectURL(url);
  },

  // Get all indexed channels
  getChannels: async () => {
    const response = await client.get('/channels');
    return response.data;
  },

  // Get videos (optional channel_id filter)
  getVideos: async (channelId = null) => {
    const params = {};
    if (channelId) params.channel_id = channelId;
    const response = await client.get('/videos', { params });
    return response.data;
  },

  // Get video details and transcripts
  getVideoDetail: async (videoId) => {
    const response = await client.get(`/video/${videoId}`);
    return response.data;
  },

  // Get topics (optional channel_id filter)
  getTopics: async (channelId = null) => {
    const params = {};
    if (channelId) params.channel_id = channelId;
    const response = await client.get('/topics', { params });
    return response.data;
  },

  // Semantic search
  search: async (query, channelId = null) => {
    const params = { query };
    if (channelId) params.channel_id = channelId;
    const response = await client.get('/search', { params });
    return response.data;
  },

  // Chat streaming implementation
  chatStream: async (message, channelId = null, sortByDate = false, { onMetadata, onChunk, onDone, onError }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          channel_id: channelId || null,
          sort_by_date: sortByDate,
        }),
      });

      if (!response.ok) {
        throw new Error(`Chat API error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let parsedMetadata = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        if (!parsedMetadata) {
          let lineEndIdx = buffer.indexOf('\n');
          if (lineEndIdx !== -1) {
            const line = buffer.slice(0, lineEndIdx).trim();
            if (line.startsWith('METADATA:')) {
              try {
                const metaJson = line.replace('METADATA:', '');
                const metadata = JSON.parse(metaJson);
                if (onMetadata) onMetadata(metadata);
              } catch (err) {
                console.error('Error parsing citation metadata:', err);
              }
            }
            buffer = buffer.slice(lineEndIdx + 1);
            parsedMetadata = true;
          }
        }
        
        if (parsedMetadata && buffer.length > 0) {
          if (onChunk) onChunk(buffer);
          buffer = '';
        }
      }
      
      if (buffer && onChunk) {
        onChunk(buffer);
      }

      if (onDone) onDone();
    } catch (error) {
      if (onError) onError(error);
      else console.error('Streaming error:', error);
    }
  },
};
