import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './ui/Card';
import { Input } from './ui/Input';
import { Button } from './ui/Button';
import { apiService } from '../services/api';
import { Plus, Youtube, RefreshCw, Layers, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function ChannelIndexer({ onSelectChannel, selectedChannelId, channels = [], fetchChannels }) {
  const [url, setUrl] = useState('');
  const [scope, setScope] = useState('latest_20');
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
      const response = await apiService.indexChannel(url, null, scope);
      setSuccess(`Success: ${response.message}`);
      setUrl('');
      if (fetchChannels) fetchChannels();
      if (onSelectChannel && response.channel) {
        onSelectChannel(response.channel.channel_id);
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Failed to start indexing. Please check the URL or channel handle.';
      setError(errorMsg);
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

  const formatScopeLabel = (scopeVal) => {
    switch (scopeVal) {
      case 'latest_20': return 'Latest 20 videos';
      case 'latest_50': return 'Latest 50 videos';
      case 'entire_channel': return 'Entire channel';
      default: return 'Latest 20 videos';
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
            Enter a YouTube Channel URL or handle (e.g., <code className="text-primary font-mono bg-white/5 px-1.5 py-0.5 rounded">https://youtube.com/@hnasr</code> or <code className="text-primary font-mono bg-white/5 px-1.5 py-0.5 rounded">@LangChain</code>) and select a bounded indexing scope.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleIndex} className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-2">
              <Input
                type="text"
                placeholder="https://youtube.com/@creator"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={loading}
                className="flex-grow"
              />
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                disabled={loading}
                className="bg-[#0f172a] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-primary shrink-0"
                aria-label="Indexing Scope"
              >
                <option value="latest_20">Latest 20 videos</option>
                <option value="latest_50">Latest 50 videos</option>
                <option value="entire_channel">Entire channel</option>
              </select>
              <Button type="submit" loading={loading} className="shrink-0 gap-1.5">
                <Plus className="w-4 h-4" />
                <span>Index ({formatScopeLabel(scope)})</span>
              </Button>
            </div>
            {error && (
              <div className="flex items-center gap-2 text-xs text-red-400 bg-red-950/20 border border-red-500/20 p-2.5 rounded-lg">
                <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className="flex items-center gap-2 text-xs text-green-400 bg-green-950/20 border border-green-500/20 p-2.5 rounded-lg">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-green-400" />
                <span>{success}</span>
              </div>
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
                const status = channel.indexing_status || (channel.is_indexing ? 'indexing' : 'idle');
                const isIndexing = status === 'indexing';
                const isCancelling = status === 'cancel_requested';
                
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
                          {channel.channel_name ? channel.channel_name[0] : 'C'}
                        </div>
                      )}
                      <div>
                        <h4 className="text-sm font-medium text-white flex items-center gap-1.5">
                          {channel.channel_name}
                          {isIndexing && (
                            <span className="inline-flex h-2 w-2 rounded-full bg-yellow-400 animate-ping" title="Indexing in progress" />
                          )}
                          {isCancelling && (
                            <span className="inline-flex h-2 w-2 rounded-full bg-orange-400 animate-pulse" title="Cancellation requested" />
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
                      {channel.failed_videos > 0 && (
                        <div className="text-[10px] text-red-400 font-mono">
                          {channel.failed_videos} failed / no transcript
                        </div>
                      )}
                      <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center justify-end gap-1.5">
                        <span className="capitalize font-mono">
                          Status: {status === 'cancel_requested' ? 'Cancelling...' : status === 'indexing' ? 'Indexing...' : channel.indexed_videos < channel.total_videos && channel.total_videos > 0 ? 'Partial' : 'Ready'}
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
