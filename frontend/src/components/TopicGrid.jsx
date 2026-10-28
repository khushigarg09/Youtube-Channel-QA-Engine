import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './ui/Card';
import { Button } from './ui/Button';
import { apiService } from '../services/api';
import { Hash, ExternalLink, RefreshCw, AlertCircle } from 'lucide-react';

export default function TopicGrid({ channelId }) {
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [error, setError] = useState('');

  const fetchTopics = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiService.getTopics(channelId);
      setTopics(data);
      // Auto-select first topic if nothing is selected
      setSelectedTopic(prev => {
        if (data.length > 0 && !prev) {
          return data[0];
        } else if (data.length > 0 && prev) {
          const updated = data.find(t => t.topic === prev.topic);
          return updated || prev;
        }
        return null;
      });
    } catch (err) {
      console.error(err);
      setError('Failed to fetch topics. Make sure the backend is running.');
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    fetchTopics();
  }, [fetchTopics]);

  // Helper to convert seconds to MM:SS format
  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Topics List Card */}
      <Card className="md:col-span-1 flex flex-col max-h-[600px]">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-md flex items-center gap-1.5">
              <Hash className="text-primary w-4.5 h-4.5" />
              <span>Discovered Topics</span>
            </CardTitle>
            <CardDescription>Click to explore references.</CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={fetchTopics} className="p-1 hover:bg-white/5">
            <RefreshCw className={`w-4 h-4 text-muted-foreground ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-grow p-0 custom-scrollbar">
          {error && (
            <div className="p-4 text-center text-red-400 text-xs flex flex-col items-center gap-2">
              <AlertCircle className="w-5 h-5" />
              <span>{error}</span>
            </div>
          )}
          {topics.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              {loading ? 'Scanning channel transcripts...' : 'No topics discovered. Index some transcripts first!'}
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {topics.map((item) => {
                const isSelected = selectedTopic?.topic === item.topic;
                return (
                  <div
                    key={item.topic}
                    onClick={() => setSelectedTopic(item)}
                    className={`flex items-center justify-between p-3.5 cursor-pointer transition-all hover:bg-white/5 ${
                      isSelected ? 'bg-primary/10 border-l-2 border-primary text-white' : 'text-slate-300'
                    }`}
                  >
                    <span className="text-sm font-medium">#{item.topic}</span>
                    <span className="text-xs bg-white/5 border border-white/5 text-muted-foreground px-2 py-0.5 rounded-full font-mono">
                      {item.video_count} videos
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Occurrences Detail Card */}
      <Card className="md:col-span-2 flex flex-col max-h-[600px]">
        <CardHeader>
          <CardTitle className="text-md flex items-center gap-2 text-white">
            <span>Topic Mentions: </span>
            {selectedTopic ? (
              <span className="text-primary font-semibold">#{selectedTopic.topic}</span>
            ) : (
              <span className="text-muted-foreground">None selected</span>
            )}
          </CardTitle>
          <CardDescription>
            Chronological timestamps of where this topic was discussed.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-grow custom-scrollbar space-y-3">
          {!selectedTopic ? (
            <div className="p-12 text-center text-sm text-muted-foreground">
              Select a topic on the left to view specific timestamp citations.
            </div>
          ) : selectedTopic.occurrences.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">
              No references found.
            </div>
          ) : (
            <div className="space-y-3">
              {selectedTopic.occurrences.map((occ, idx) => (
                <div
                  key={`${occ.video_id}-${occ.timestamp}-${idx}`}
                  className="glass-panel p-4 rounded-xl flex items-center justify-between hover:bg-white/5 border border-white/5 transition-colors"
                >
                  <div className="space-y-1 pr-4">
                    <h4 className="text-sm font-medium text-white line-clamp-1">{occ.video_title}</h4>
                    <p className="text-xs text-muted-foreground">
                      Upload Date: {occ.upload_date ? new Date(occ.upload_date).toLocaleDateString() : 'N/A'}
                    </p>
                  </div>
                  
                  <div className="shrink-0 flex items-center gap-3">
                    <span className="text-xs font-mono font-bold text-primary bg-primary/10 border border-primary/20 px-2 py-1 rounded">
                      Timestamp: {formatTime(occ.timestamp)}
                    </span>
                    <a
                      href={`https://youtube.com/watch?v=${occ.video_id}&t=${Math.floor(occ.timestamp)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white bg-white/5 hover:bg-white/10 px-2.5 py-1.5 rounded-lg border border-white/10 transition-all shadow-sm"
                    >
                      <span>Jump</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
