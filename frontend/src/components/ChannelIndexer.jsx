import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './ui/Card';
import { Input } from './ui/Input';
import { Button } from './ui/Button';
import { apiService } from '../services/api';
import { Plus, Youtube, RefreshCw, Layers } from 'lucide-react';

export default function ChannelIndexer({ onSelectChannel, selectedChannelId, channels = [], fetchChannels }) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleIndex = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await apiService.indexChannel(url);
      setSuccess(`Successfully resolved! ${response.message}`);
      setUrl('');
      if (fetchChannels) fetchChannels();
      if (onSelectChannel && response.channel) {
        onSelectChannel(response.channel.channel_id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to trigger indexing. Please check the URL.');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async (channelId) => {
    try {
      setLoading(true);
      setError('');
      setSuccess('');
      const response = await apiService.cancelIndexing(channelId);
      setSuccess(response.message || 'Indexing cancellation request submitted.');
      if (fetchChannels) fetchChannels();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to cancel indexing.');
    } finally {
      setLoading(false);
    }
  };


  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Youtube className="text-red-500 w-5 h-5 animate-pulse" />
            <span>Index YouTube Channel</span>
          </CardTitle>
          <CardDescription>
            Enter any YouTube Channel URL (e.g., handles like <code className="text-primary font-mono bg-white/5 px-1.5 py-0.5 rounded">https://youtube.com/@LangChain</code> or IDs) to resolve, download transcripts, and build a vector database.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleIndex} className="space-y-4">
            <div className="flex gap-2">
              <Input
                type="text"
                placeholder="https://youtube.com/@creator"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={loading}
              />
              <Button type="submit" loading={loading} className="shrink-0 gap-1.5">
                <Plus className="w-4 h-4" />
                <span>Index</span>
              </Button>
            </div>
            {error && (
              <p className="text-xs text-red-400 bg-red-950/20 border border-red-500/20 p-2.5 rounded-lg">
                {error}
              </p>
            )}
            {success && (
              <p className="text-xs text-green-400 bg-green-950/20 border border-green-500/20 p-2.5 rounded-lg">
                {success}
              </p>
            )}
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-md flex items-center gap-2">
              <Layers className="text-primary w-4.5 h-4.5" />
              <span>Indexed Channels</span>
            </CardTitle>
            <CardDescription>Select a channel to query or browse.</CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={fetchChannels} className="p-1 hover:bg-white/5">
            <RefreshCw className="w-4 h-4 text-muted-foreground" />
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {channels.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No channels indexed yet. Enter a URL above to start.
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {channels.map((channel) => {
                const isSelected = selectedChannelId === channel.channel_id;
                const isIndexing = channel.is_indexing;
                
                return (
                  <div
                    key={channel.channel_id}
                    onClick={() => onSelectChannel(channel.channel_id)}
                    className={`flex items-center justify-between p-4 cursor-pointer transition-all duration-200 hover:bg-white/5 ${
                      isSelected ? 'bg-primary/10 border-l-2 border-primary' : ''
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {channel.thumbnail_url ? (
                        <img
                          src={channel.thumbnail_url}
                          alt={channel.channel_name}
                          className="w-10 h-10 rounded-full border border-white/10"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-white font-bold">
                          {channel.channel_name[0]}
                        </div>
                      )}
                      <div>
                        <h4 className="text-sm font-medium text-white flex items-center gap-1.5">
                          {channel.channel_name}
                          {isIndexing && (
                            <span className="inline-flex h-2 w-2 rounded-full bg-yellow-400 animate-ping" />
                          )}
                        </h4>
                        <p className="text-xs text-muted-foreground">
                          {channel.custom_url || `@${channel.channel_id}`}
                        </p>
                      </div>
                    </div>
                    
                    <div className="text-right shrink-0">
                      <div className="text-xs font-mono font-medium text-white">
                        {channel.indexed_videos} / {channel.total_videos} videos
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center justify-end gap-1.5">
                        <span>
                          {channel.is_indexing 
                            ? 'Indexing...' 
                            : channel.indexed_videos < channel.total_videos 
                              ? 'Stopped' 
                              : 'Ready'}
                        </span>
                        {isIndexing && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCancel(channel.channel_id);
                            }}
                            className="text-[10px] text-red-400 hover:text-red-300 bg-red-950/20 border border-red-500/20 px-1.5 py-0.5 rounded cursor-pointer transition-all"
                            title="Stop Indexing"
                          >
                            Stop
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
