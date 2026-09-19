import React, { useState } from 'react';
import { Card } from './ui/Card';
import { Play, Calendar, Clock, Database, AlertCircle, RotateCcw } from 'lucide-react';
import { apiService } from '../services/api';

export default function VideoCard({ video, onClick, onReindexed }) {
  const [reindexing, setReindexing] = useState(false);

  // Helper to format duration in seconds to MM:SS or HH:MM:SS
  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hrs > 0) {
      return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Helper to format ISO date to readable text
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  };

  const handleReindex = async (e) => {
    e.stopPropagation();
    try {
      setReindexing(true);
      await apiService.reindexVideo(video.video_id);
      if (onReindexed) onReindexed(video.video_id);
    } catch (err) {
      console.error('Failed to re-index video:', err);
    } finally {
      setReindexing(false);
    }
  };

  const getStatusBadge = (status, errorMsg) => {
    switch (status) {
      case 'indexed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-green-500/10 text-green-400 border border-green-500/20">
            <Database className="w-3 h-3" /> Indexed
          </span>
        );
      case 'indexing':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 animate-pulse">
            <Clock className="w-3 h-3" /> Indexing
          </span>
        );
      case 'failed':
        return (
          <span 
            title={errorMsg || 'Failed to retrieve transcript'}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-red-500/10 text-red-400 border border-red-500/20 cursor-help"
          >
            <AlertCircle className="w-3 h-3" /> Failed
          </span>
        );
      case 'no_transcript':
        return (
          <span 
            title={errorMsg || 'No transcript was generated for this video.'}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 cursor-help"
          >
            <Clock className="w-3 h-3" /> No Transcript
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-white/10 text-muted-foreground border border-white/5">
            Pending
          </span>
        );
    }
  };

  return (
    <Card 
      onClick={onClick}
      className="glass-card-hover flex flex-col h-full cursor-pointer border border-white/5 rounded-xl hover:border-primary/20 overflow-hidden group"
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-black/40 overflow-hidden">
        {video.thumbnail_url ? (
          <img 
            src={video.thumbnail_url} 
            alt={video.title} 
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground">
            No Thumbnail
          </div>
        )}
        
        {/* Play Icon hover overlay */}
        <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
          <div className="p-3 bg-primary/80 rounded-full text-white shadow-lg">
            <Play className="w-5 h-5 fill-current" />
          </div>
        </div>
        
        {/* Duration badge */}
        {video.duration_seconds > 0 && (
          <span className="absolute bottom-2 right-2 bg-black/80 px-1.5 py-0.5 text-[10px] font-mono text-white rounded">
            {formatDuration(video.duration_seconds)}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-4 flex-grow flex flex-col justify-between space-y-3">
        <div className="space-y-1.5">
          <h4 className="text-sm font-medium text-white line-clamp-2 leading-snug group-hover:text-primary transition-colors">
            {video.title}
          </h4>
          {video.description && (
            <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
              {video.description}
            </p>
          )}
        </div>

        <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-2 border-t border-white/5">
          <span className="flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            {formatDate(video.upload_date)}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReindex}
              disabled={reindexing || video.status === 'indexing'}
              title="Re-index this video"
              className="p-1 rounded hover:bg-white/10 text-muted-foreground hover:text-white transition-colors disabled:opacity-40"
            >
              <RotateCcw className={`w-3 h-3 ${reindexing ? 'animate-spin' : ''}`} />
            </button>
            {getStatusBadge(video.status, video.error_message)}
          </div>
        </div>
      </div>
    </Card>
  );
}
