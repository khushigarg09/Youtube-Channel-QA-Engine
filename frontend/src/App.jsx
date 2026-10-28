import React, { useState, useEffect, useCallback } from 'react';
import ChannelIndexer from './components/ChannelIndexer';
import ChatWindow from './components/ChatWindow';
import VideoCard from './components/VideoCard';
import TopicGrid from './components/TopicGrid';
import { Input } from './components/ui/Input';
import { Button } from './components/ui/Button';
import { apiService, API_BASE_URL } from './services/api';
import { Layout, MessageSquare, Video, Hash, Youtube, ExternalLink, RefreshCw, Compass, ChevronsUpDown, Download } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedChannelId, setSelectedChannelId] = useState(null);
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [channels, setChannels] = useState([]);
  const [isChannelDropdownOpen, setIsChannelDropdownOpen] = useState(false);
  const [isExportDropdownOpen, setIsExportDropdownOpen] = useState(false);
  
  // Videos tab state
  const [videos, setVideos] = useState([]);
  const [videosLoading, setVideosLoading] = useState(false);
  const [videoSearchText, setVideoSearchText] = useState('');
  const [selectedVideoDetail, setSelectedVideoDetail] = useState(null);

  const fetchChannels = useCallback(async () => {
    try {
      const data = await apiService.getChannels();
      setChannels(data);
      // Auto-select first channel if nothing is selected yet
      setSelectedChannelId(prev => (data.length > 0 && !prev ? data[0].channel_id : prev));
    } catch (err) {
      console.error(err);
    }
  }, []);

  const fetchVideos = useCallback(async () => {
    if (!selectedChannelId) return;
    setVideosLoading(true);
    try {
      const data = await apiService.getVideos(selectedChannelId);
      setVideos(data);
    } catch (err) {
      console.error(err);
    } finally {
      setVideosLoading(false);
    }
  }, [selectedChannelId]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  // Listen to indexing progress via Server-Sent Events (SSE) in real-time
  useEffect(() => {
    const indexingChannel = channels.find(c => c.is_indexing);
    if (!indexingChannel) return;

    const channelId = indexingChannel.channel_id;
    console.log("Opening indexing progress SSE for channel:", channelId);
    
    const eventSource = new EventSource(`${API_BASE_URL}/index-progress/${channelId}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.error) {
          console.error("Index progress SSE error:", data.error);
          eventSource.close();
          fetchChannels();
          return;
        }

        setChannels(prev => prev.map(c => {
          if (c.channel_id === channelId) {
            const newStatus = data.indexing_status || (data.total_videos > 0 && data.indexed_videos === data.total_videos ? 'idle' : c.indexing_status);
            return {
              ...c,
              indexed_videos: data.indexed_videos,
              total_videos: data.total_videos,
              indexing_status: newStatus,
              is_indexing: newStatus === 'indexing'
            };
          }
          return c;
        }));

        if ((data.total_videos > 0 && data.indexed_videos === data.total_videos) || (data.indexing_status && data.indexing_status !== 'indexing')) {
          console.log("Indexing finished or stopped. Closing SSE stream.");
          eventSource.close();
          fetchChannels();
          if (selectedChannelId === channelId) {
            fetchVideos();
          }
        }
      } catch (err) {
        console.error("Failed to parse progress event:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE connection error:", err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [channels, selectedChannelId, fetchChannels, fetchVideos]);

  useEffect(() => {
    if (selectedChannelId) {
      const found = channels.find(c => c.channel_id === selectedChannelId);
      setSelectedChannel(found || null);
      fetchVideos();
    }
  }, [selectedChannelId, channels, fetchVideos]);

  const handleViewVideoDetail = async (videoId) => {
    try {
      const detail = await apiService.getVideoDetail(videoId);
      setSelectedVideoDetail(detail);
    } catch (err) {
      console.error("Failed to load video details:", err);
    }
  };

  const handleExport = async (format) => {
    if (!selectedChannelId) return;
    try {
      await apiService.exportChannelData(selectedChannelId, format);
      setIsExportDropdownOpen(false);
    } catch (err) {
      console.error(`Failed to export channel data as ${format}:`, err);
    }
  };

  const filteredVideos = videos.filter(v => 
    v.title.toLowerCase().includes(videoSearchText.toLowerCase()) ||
    (v.description && v.description.toLowerCase().includes(videoSearchText.toLowerCase()))
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground font-sans">
      {/* Left Sidebar Navigation */}
      <aside className="w-64 border-r border-white/5 bg-[#090d19]/80 backdrop-blur-xl flex flex-col justify-between shrink-0 z-20">
        <div className="space-y-6">
          {/* Logo Brand Header */}
          <div className="p-6 pb-2 flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-primary to-indigo-500 flex items-center justify-center text-white shadow-lg shadow-primary/20">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-1.5">
                Channel<span className="text-primary">RAG</span>
              </h1>
              <p className="text-[10px] text-muted-foreground font-mono">QA Engine v2.0</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="px-3 space-y-1">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'dashboard'
                  ? 'bg-primary/10 text-primary border border-primary/20 shadow-sm'
                  : 'text-muted-foreground hover:bg-white/5 hover:text-white'
              }`}
            >
              <Layout className="w-4 h-4" />
              <span>Channels & Index</span>
            </button>

            <button
              onClick={() => setActiveTab('chat')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'chat'
                  ? 'bg-primary/10 text-primary border border-primary/20 shadow-sm'
                  : 'text-muted-foreground hover:bg-white/5 hover:text-white'
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              <span>Semantic Chat</span>
            </button>

            <button
              onClick={() => setActiveTab('videos')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'videos'
                  ? 'bg-primary/10 text-primary border border-primary/20 shadow-sm'
                  : 'text-muted-foreground hover:bg-white/5 hover:text-white'
              }`}
            >
              <Video className="w-4 h-4" />
              <span>Videos Explorer</span>
            </button>

            <button
              onClick={() => setActiveTab('topics')}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'topics'
                  ? 'bg-primary/10 text-primary border border-primary/20 shadow-sm'
                  : 'text-muted-foreground hover:bg-white/5 hover:text-white'
              }`}
            >
              <Hash className="w-4 h-4" />
              <span>Topic Discovery</span>
            </button>
          </nav>
        </div>

        {/* Channel Switcher Dropdown */}
        {selectedChannel && (
          <div className="border-t border-white/5 bg-black/20 relative">
            {isChannelDropdownOpen && (
              <>
                <div 
                  className="fixed inset-0 z-30" 
                  onClick={() => setIsChannelDropdownOpen(false)} 
                />
                <div className="absolute bottom-full left-3 right-3 mb-2 bg-[#0d1326] border border-white/10 rounded-xl shadow-2xl p-1.5 z-40 max-h-60 overflow-y-auto custom-scrollbar backdrop-blur-xl">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground px-2.5 py-1.5">
                    Switch Workspace Channel
                  </div>
                  {channels.map((chan) => {
                    const isChanSelected = chan.channel_id === selectedChannelId;
                    return (
                      <button
                        key={chan.channel_id}
                        onClick={() => {
                          setSelectedChannelId(chan.channel_id);
                          setIsChannelDropdownOpen(false);
                        }}
                        className={`w-full flex items-center gap-2.5 p-2 rounded-lg text-left transition-all text-sm ${
                          isChanSelected 
                            ? 'bg-primary/20 text-white font-medium border border-primary/20' 
                            : 'text-slate-300 hover:bg-white/5 hover:text-white border border-transparent'
                        }`}
                      >
                        {chan.thumbnail_url ? (
                          <img
                            src={chan.thumbnail_url}
                            alt={chan.channel_name}
                            className="w-6 h-6 rounded-full border border-white/10 shrink-0"
                          />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-secondary flex items-center justify-center font-bold text-white shrink-0 text-xs">
                            {chan.channel_name[0]}
                          </div>
                        )}
                        <div className="truncate flex-grow">
                          <span className="block truncate">{chan.channel_name}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </>
            )}

            {/* Selector trigger */}
            <div 
              onClick={() => setIsChannelDropdownOpen(!isChannelDropdownOpen)}
              className="p-4 flex items-center justify-between gap-3 hover:bg-white/5 hover:text-white cursor-pointer transition-all"
              title="Click to switch active channel workspace"
            >
              <div className="flex items-center gap-3 overflow-hidden">
                {selectedChannel.thumbnail_url ? (
                  <img
                    src={selectedChannel.thumbnail_url}
                    alt={selectedChannel.channel_name}
                    className="w-10 h-10 rounded-full border border-white/10 shrink-0"
                  />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center font-bold text-white shrink-0 text-sm">
                    {selectedChannel.channel_name[0]}
                  </div>
                )}
                <div className="overflow-hidden">
                  <div className="text-xs font-semibold text-white truncate">{selectedChannel.channel_name}</div>
                  <div className="text-[10px] text-indigo-300 font-mono mt-0.5 flex items-center gap-1">
                    <span>Active Workspace</span>
                  </div>
                </div>
              </div>
              <ChevronsUpDown className="w-4 h-4 text-slate-400 shrink-0" />
            </div>
          </div>
        )}
      </aside>

      {/* Main Workspace Panel */}
      <main className="flex-grow flex flex-col h-full overflow-hidden relative">
        {/* Top Header bar */}
        <header className="h-16 border-b border-white/5 bg-[#090d19]/40 flex items-center justify-between px-8 z-10 shrink-0">
          <div className="text-sm font-semibold text-slate-300 flex items-center gap-2">
            <span>Workspace</span>
            <span className="text-white/20">/</span>
            <span className="text-white font-medium capitalize">{activeTab}</span>
          </div>

          <div className="flex items-center gap-3 relative">
            {/* Export Dropdown */}
            {selectedChannelId && (
              <div className="relative">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsExportDropdownOpen(!isExportDropdownOpen)}
                  className="gap-1.5 text-xs border-white/5 hover:bg-white/5"
                >
                  <Download className="w-3.5 h-3.5 text-primary" />
                  <span>Export</span>
                </Button>

                {isExportDropdownOpen && (
                  <>
                    <div 
                      className="fixed inset-0 z-30" 
                      onClick={() => setIsExportDropdownOpen(false)} 
                    />
                    <div className="absolute right-0 mt-2 w-44 bg-[#0d1326] border border-white/10 rounded-xl shadow-2xl p-1.5 z-40 backdrop-blur-xl">
                      <button
                        onClick={() => handleExport('json')}
                        className="w-full text-left px-3 py-2 text-xs text-slate-200 hover:bg-white/10 rounded-lg transition-colors flex items-center justify-between"
                      >
                        <span>Export as JSON</span>
                        <span className="text-[10px] text-muted-foreground font-mono">.json</span>
                      </button>
                      <button
                        onClick={() => handleExport('csv')}
                        className="w-full text-left px-3 py-2 text-xs text-slate-200 hover:bg-white/10 rounded-lg transition-colors flex items-center justify-between"
                      >
                        <span>Export as CSV</span>
                        <span className="text-[10px] text-muted-foreground font-mono">.csv</span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={fetchChannels}
              className="gap-1.5 text-xs border-white/5 hover:bg-white/5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Sync</span>
            </Button>
          </div>
        </header>

        {/* Main Content Area */}
        <div className="flex-grow overflow-y-auto p-8 custom-scrollbar relative">
          
          {/* Dashboard Tab */}
          {activeTab === 'dashboard' && (
            <div className="max-w-4xl mx-auto space-y-8">
              <div className="space-y-2">
                <h2 className="text-3xl font-extrabold tracking-tight text-white">
                  Welcome to <span className="gradient-text">YouTube Knowledge Graph</span>
                </h2>
                <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">
                  Start by indexing a creator's YouTube channel. Once transcript segments are parsed and vectors are generated, you can semantically chat, timeline search, and explore topics.
                </p>
              </div>
              <ChannelIndexer
                channels={channels}
                fetchChannels={fetchChannels}
                selectedChannelId={selectedChannelId}
                onSelectChannel={(id) => {
                  setSelectedChannelId(id);
                }}
              />
            </div>
          )}

          {/* Chat Tab */}
          {activeTab === 'chat' && (
            <div className="max-w-6xl mx-auto h-full">
              {selectedChannelId ? (
                <ChatWindow channelId={selectedChannelId} />
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center p-8">
                  <Youtube className="w-12 h-12 text-slate-500 mb-3" />
                  <h3 className="text-lg font-semibold text-white">No Channel Selected</h3>
                  <p className="text-muted-foreground text-sm max-w-sm mt-1 mb-4">
                    To start a semantic chat, select or index a YouTube channel in the Channels tab.
                  </p>
                  <Button onClick={() => setActiveTab('dashboard')}>
                    Go to Channels & Indexing
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* Videos Tab */}
          {activeTab === 'videos' && (
            <div className="max-w-6xl mx-auto space-y-6">
              {selectedChannelId ? (
                <>
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-bold text-white">Videos for {selectedChannel?.channel_name}</h2>
                      <p className="text-xs text-muted-foreground">List of all parsed and queued videos.</p>
                    </div>

                    <div className="flex gap-2 w-full md:w-80 shrink-0">
                      <Input
                        placeholder="Search video titles..."
                        value={videoSearchText}
                        onChange={(e) => setVideoSearchText(e.target.value)}
                      />
                    </div>
                  </div>

                  {videosLoading ? (
                    <div className="py-24 text-center text-sm text-muted-foreground flex flex-col items-center justify-center gap-2">
                      <RefreshCw className="w-6 h-6 animate-spin text-primary" />
                      <span>Loading channel videos...</span>
                    </div>
                  ) : filteredVideos.length === 0 ? (
                    <div className="py-24 text-center text-sm text-muted-foreground border border-dashed border-white/5 rounded-2xl bg-black/10">
                      No videos found. Check if the channel is still indexing.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
                      {filteredVideos.map((video) => (
                        <VideoCard
                          key={video.video_id}
                          video={video}
                          onClick={() => handleViewVideoDetail(video.video_id)}
                          onReindexed={fetchVideos}
                        />
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="py-24 text-center text-sm text-muted-foreground">
                  Please select or index a channel on the dashboard tab to view videos.
                </div>
              )}
            </div>
          )}

          {/* Topics Tab */}
          {activeTab === 'topics' && (
            <div className="max-w-6xl mx-auto space-y-6">
              {selectedChannelId ? (
                <TopicGrid channelId={selectedChannelId} />
              ) : (
                <div className="py-24 text-center text-sm text-muted-foreground">
                  Please select or index a channel on the dashboard tab to browse topics.
                </div>
              )}
            </div>
          )}

        </div>
      </main>

      {/* Video Details Transcript Modal */}
      {selectedVideoDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6 animate-fade-in">
          <div className="glass-panel w-full max-w-3xl max-h-[85vh] rounded-2xl flex flex-col border border-white/10 shadow-2xl overflow-hidden">
            <header className="p-5 border-b border-white/5 flex items-start justify-between bg-black/20 shrink-0">
              <div className="space-y-1 pr-6">
                <h3 className="text-md font-semibold text-white leading-snug">
                  {selectedVideoDetail.video.title}
                </h3>
                <p className="text-xs text-muted-foreground flex items-center gap-3">
                  <span>Upload: {selectedVideoDetail.video.upload_date ? new Date(selectedVideoDetail.video.upload_date).toLocaleDateString() : 'N/A'}</span>
                  <span>•</span>
                  <span>Duration: {Math.floor(selectedVideoDetail.video.duration_seconds / 60)} mins</span>
                </p>
              </div>
              <button 
                onClick={() => setSelectedVideoDetail(null)}
                className="text-slate-400 hover:text-white bg-white/5 hover:bg-white/10 px-3 py-1.5 rounded-lg border border-white/10 transition-all text-xs font-semibold"
              >
                Close
              </button>
            </header>

            <div className="flex-grow overflow-y-auto p-5 space-y-4 custom-scrollbar bg-black/5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-300">Transcript Chunks</h4>
              
              {selectedVideoDetail.chunks.length === 0 ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  {selectedVideoDetail.video.status === 'failed' || selectedVideoDetail.video.status === 'no_transcript'
                    ? 'No transcript was generated for this video (disabled or automatic transcripts not available).' 
                    : 'Transcript is indexing. Please wait...'}
                </div>
              ) : (
                <div className="space-y-3">
                  {selectedVideoDetail.chunks.map((chunk) => {
                    const mm = Math.floor(chunk.start_time / 60);
                    const ss = Math.floor(chunk.start_time % 60);
                    const timeFormatted = `${mm}:${ss.toString().padStart(2, '0')}`;
                    
                    return (
                      <div 
                        key={chunk.chunk_id}
                        className="glass-panel p-3.5 rounded-xl border border-white/5 hover:border-white/10 transition-all flex items-start gap-4"
                      >
                        <span className="text-[11px] font-mono font-bold text-primary bg-primary/10 border border-primary/20 px-2 py-1 rounded shrink-0">
                          {timeFormatted}
                        </span>
                        
                        <div className="flex-grow space-y-1">
                          <p className="text-xs text-slate-200 leading-relaxed font-light">
                            {chunk.text}
                          </p>
                          <div className="flex justify-end pt-1">
                            <a
                              href={`https://youtube.com/watch?v=${selectedVideoDetail.video.video_id}&t=${Math.floor(chunk.start_time)}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-white hover:underline transition-all"
                            >
                              <span>Open YouTube at {timeFormatted}</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
