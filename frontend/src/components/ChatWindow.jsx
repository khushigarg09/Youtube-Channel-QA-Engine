import React, { useState, useRef, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from './ui/Card';
import { Input } from './ui/Input';
import { Button } from './ui/Button';
import { apiService } from '../services/api';
import { Send, Sparkles, ExternalLink, Calendar, ListFilter, MessageSquare, Clock, Trash2 } from 'lucide-react';

export default function ChatWindow({ channelId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sortByDate, setSortByDate] = useState(false);
  const [currentSources, setCurrentSources] = useState([]);
  
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const resetChat = () => {
    setMessages([
      {
        role: 'assistant',
        text: 'Hello! I am your YouTube Knowledge Graph assistant. Ask me anything across the video collection of this channel!',
        sources: []
      }
    ]);
    setCurrentSources([]);
  };

  // Load chat history when channel is switched
  useEffect(() => {
    const saved = localStorage.getItem('yt_knowledge_graph_chat_history_' + channelId);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setMessages(parsed);
        // Load sources from last assistant response
        const lastAssistant = [...parsed].reverse().find(m => m.role === 'assistant');
        if (lastAssistant && lastAssistant.sources) {
          setCurrentSources(lastAssistant.sources);
        } else {
          setCurrentSources([]);
        }
      } catch (e) {
        console.error('Failed to load chat history:', e);
        resetChat();
      }
    } else {
      resetChat();
    }
  }, [channelId]);

  // Save chat history when messages change and loading is completed
  useEffect(() => {
    if (messages.length > 1 && !loading) {
      localStorage.setItem('yt_knowledge_graph_chat_history_' + channelId, JSON.stringify(messages));
    }
  }, [messages, loading, channelId]);

  const handleClearChat = () => {
    localStorage.removeItem('yt_knowledge_graph_chat_history_' + channelId);
    resetChat();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    // Append user message immediately
    setMessages(prev => [...prev, { role: 'user', text: userMessage }]);
    
    // Setup placeholder for assistant streaming response
    setMessages(prev => [...prev, { role: 'assistant', text: '', sources: [] }]);

    let accumulatedText = '';

    await apiService.chatStream(
      userMessage,
      channelId,
      sortByDate,
      {
        onMetadata: (metadata) => {
          setCurrentSources(metadata);
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last) {
              last.sources = metadata;
            }
            return updated;
          });
        },
        onChunk: (chunk) => {
          accumulatedText += chunk;
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last) {
              last.text = accumulatedText;
            }
            return updated;
          });
        },
        onError: (err) => {
          console.error(err);
          setMessages(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last) {
              last.text = 'Error generating response. Please make sure your GROQ_API_KEY is configured and valid.';
            }
            return updated;
          });
          setLoading(false);
        },
        onDone: () => {
          setLoading(false);
        }
      }
    );
  };

  // Helper to securely parse citations and render clickable elements
  const parseResponseText = (text) => {
    if (!text) return '';
    // Matches markdown style: [Video Title](https://youtube.com/watch?v=VIDEO_ID&t=SECONDS)
    const regex = /\[([^\]]+)\]\((https:\/\/youtube\.com\/watch\?v=([a-zA-Z0-9_-]+)&t=(\d+))\)/g;
    
    const elements = [];
    let lastIdx = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIdx) {
        elements.push(<span key={lastIdx}>{text.slice(lastIdx, match.index)}</span>);
      }

      const title = match[1];
      const url = match[2];
      const seconds = parseInt(match[4], 10);
      
      const mm = Math.floor(seconds / 60);
      const ss = seconds % 60;
      const formattedTime = `${mm}:${ss.toString().padStart(2, '0')}`;

      elements.push(
        <a
          key={match.index}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-primary/10 hover:bg-primary/20 border border-primary/20 text-xs font-semibold text-indigo-300 transition-colors mx-0.5"
          title={`Watch: ${title}`}
        >
          <span>🎥 {title}</span>
          <span className="text-[10px] opacity-80 font-mono">({formattedTime})</span>
        </a>
      );

      lastIdx = regex.lastIndex;
    }

    if (lastIdx < text.length) {
      elements.push(<span key={lastIdx}>{text.slice(lastIdx)}</span>);
    }

    return elements.length > 0 ? elements : text;
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 h-[600px]">
      {/* Main Chat Area */}
      <Card className="lg:col-span-3 flex flex-col h-full border border-white/5 overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between border-b border-white/5 py-4 shrink-0">
          <div>
            <CardTitle className="text-md flex items-center gap-2 text-white">
              <MessageSquare className="w-5 h-5 text-primary" />
              <span>Channel Chat Assistant</span>
            </CardTitle>
            <CardDescription>Ask questions and see source video timestamps.</CardDescription>
          </div>
          
          <div className="flex items-center gap-2">
            {/* Sorting / Timeline Filter Toggle */}
            <button
              onClick={() => setSortByDate(!sortByDate)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-all ${
                sortByDate
                  ? 'bg-primary/20 border-primary/50 text-indigo-300 shadow-sm shadow-primary/10'
                  : 'bg-white/5 border-white/10 text-slate-400 hover:text-white hover:bg-white/10'
              }`}
              title="Sort transcript contexts chronologically by video upload date"
            >
              <Clock className="w-3.5 h-3.5" />
              <span>Timeline Order</span>
            </button>

            {/* Clear Chat Button */}
            {messages.length > 1 && (
              <button
                onClick={handleClearChat}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/20 bg-red-950/10 text-red-400 hover:text-white hover:bg-red-500/20 text-xs transition-all"
                title="Clear conversation history for this channel"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Clear Chat</span>
              </button>
            )}
          </div>
        </CardHeader>

        {/* Message Log */}
        <CardContent className="flex-grow overflow-y-auto p-4 space-y-4 custom-scrollbar bg-black/10">
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl p-4 text-sm leading-relaxed shadow-lg ${
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground rounded-tr-none'
                    : 'glass-panel text-slate-150 rounded-tl-none border border-white/5'
                }`}
              >
                <div className="whitespace-pre-wrap">
                  {msg.role === 'user' ? msg.text : parseResponseText(msg.text)}
                </div>
              </div>
            </div>
          ))}
          {loading && messages[messages.length - 1]?.text === '' && (
            <div className="flex justify-start">
              <div className="glass-panel text-slate-300 rounded-2xl rounded-tl-none p-4 text-sm border border-white/5 flex items-center gap-2 shadow-lg">
                <Sparkles className="w-4 h-4 text-primary animate-spin" />
                <span className="animate-pulse">Synthesizing channel transcripts...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </CardContent>

        {/* Input area */}
        <CardFooter className="p-4 shrink-0 bg-black/20 border-t border-white/5">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                channelId
                  ? "e.g., 'What projects has this creator built?' or 'When was Docker first discussed?'"
                  : "Please select an indexed channel to start chat..."
              }
              disabled={loading || !channelId}
            />
            <Button type="submit" disabled={loading || !input.trim() || !channelId} className="shrink-0">
              <Send className="w-4 h-4" />
            </Button>
          </form>
        </CardFooter>
      </Card>

      {/* Citations Sidebar Panel */}
      <Card className="lg:col-span-1 flex flex-col h-full border border-white/5 overflow-hidden">
        <CardHeader className="py-4 border-b border-white/5 shrink-0">
          <CardTitle className="text-sm flex items-center gap-1.5 text-white">
            <ListFilter className="w-4 h-4 text-primary" />
            <span>Retrieved Sources</span>
          </CardTitle>
          <CardDescription>Video contexts with timestamp citations.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-y-auto flex-grow p-4 space-y-3 custom-scrollbar bg-black/5">
          <div className="text-[10px] text-muted-foreground bg-white/5 p-2 rounded border border-white/5 leading-relaxed">
            Note: Generated answers should be verified through the linked video timestamp citations.
          </div>
          {currentSources.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-4">
              <MessageSquare className="w-8 h-8 text-white/10 mb-2" />
              <p className="text-xs text-muted-foreground">
                Ask a question to see mapped context sources with timestamps.
              </p>
            </div>
          ) : (
            currentSources.map((source, index) => {
              const mm = Math.floor(source.start_time / 60);
              const ss = Math.floor(source.start_time % 60);
              const timeFormatted = `${mm}:${ss.toString().padStart(2, '0')}`;
              
              return (
                <div
                  key={index}
                  className="glass-panel p-3 rounded-lg border border-white/5 hover:bg-white/5 transition-all text-xs space-y-2"
                >
                  <div className="font-semibold text-white line-clamp-2" title={source.title}>
                    <span className="text-primary mr-1">Video:</span>{source.title}
                  </div>
                  
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {source.upload_date ? new Date(source.upload_date).toLocaleDateString() : 'N/A'}
                    </span>
                    <span className="font-mono bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded text-indigo-300 font-semibold" title="Timestamp">
                      Start: {timeFormatted} ({Math.floor(source.start_time)}s)
                    </span>
                  </div>

                  <a
                    href={`https://youtube.com/watch?v=${source.video_id}&t=${Math.floor(source.start_time)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-full inline-flex items-center justify-center gap-1 bg-white/5 hover:bg-white/10 py-1.5 rounded border border-white/10 transition-colors text-slate-300 hover:text-white font-medium"
                  >
                    <span>Open Timestamp</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
