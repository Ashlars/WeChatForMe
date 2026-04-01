import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { DashboardSummary, RuntimeStatus } from '../api/client';
import './Pages.css';

export default function Dashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);

  const load = () => {
    api.getDashboard().then(setData);
    api.getRuntimeStatus().then(setRuntime);
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const toggleAutoReply = async () => {
    if (!runtime) return;
    const res = await api.setAutoReply(!runtime.auto_reply_enabled);
    setRuntime({ ...runtime, auto_reply_enabled: res.auto_reply_enabled });
  };

  const toggleAiLabel = async () => {
    if (!runtime) return;
    const res = await api.setAiLabel({ enabled: !runtime.ai_label_enabled });
    setRuntime({ ...runtime, ai_label_enabled: res.ai_label_enabled, ai_label_text: res.ai_label_text });
  };

  const saveLabelText = async (text: string) => {
    if (!runtime) return;
    const res = await api.setAiLabel({ label_text: text });
    setRuntime({ ...runtime, ai_label_text: res.ai_label_text });
  };

  if (!data || !runtime) return <div className="loading">加载中...</div>;

  const runtimeRunning = runtime.runtime_process === 'running';

  const stats = [
    { label: '白名单联系人', value: data.whitelist_count },
    { label: '启用群聊', value: data.active_group_count },
    { label: '待审核建议', value: data.pending_review_count, color: data.pending_review_count > 0 ? '#ff9800' : undefined },
    { label: '24h 分析成功', value: data.analysis_success_24h },
    { label: '24h 分析失败', value: data.analysis_failed_24h, color: data.analysis_failed_24h > 0 ? '#f44336' : undefined },
  ];

  return (
    <div>
      <h1 className="page-title">总览</h1>

      <div className="control-panel">
        <div className="control-card">
          <div className="control-icon" style={{ background: runtimeRunning ? '#e8f5e9' : '#fce4ec' }}>
            {runtimeRunning ? '🟢' : '🔴'}
          </div>
          <div className="control-info">
            <div className="control-label">消息监听</div>
            <div className="control-value" style={{ color: runtimeRunning ? '#4caf50' : '#f44336' }}>
              {runtimeRunning ? '运行中' : '已停止'}
            </div>
          </div>
        </div>

        <div className="control-card">
          <div className="control-icon" style={{ background: runtime.auto_reply_enabled ? '#e8f5e9' : '#f5f5f5' }}>
            💬
          </div>
          <div className="control-info">
            <div className="control-label">自动回复</div>
            <button
              className={`toggle-btn-lg ${runtime.auto_reply_enabled ? 'on' : 'off'}`}
              onClick={toggleAutoReply}
            >
              {runtime.auto_reply_enabled ? '已开启' : '已关闭'}
            </button>
          </div>
        </div>

        <div className="control-card">
          <div className="control-icon" style={{ background: runtime.ai_label_enabled ? '#e8f5e9' : '#f5f5f5' }}>
            🏷️
          </div>
          <div className="control-info">
            <div className="control-label">AI 标识</div>
            <div className="control-row">
              <button
                className={`toggle-btn-lg ${runtime.ai_label_enabled ? 'on' : 'off'}`}
                onClick={toggleAiLabel}
              >
                {runtime.ai_label_enabled ? '已开启' : '已关闭'}
              </button>
              {runtime.ai_label_enabled && (
                <input
                  className="label-text-input"
                  value={runtime.ai_label_text || '[AI]'}
                  onChange={(e) => setRuntime({ ...runtime, ai_label_text: e.target.value })}
                  onBlur={(e) => saveLabelText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                  placeholder="标识内容"
                />
              )}
            </div>
          </div>
        </div>
      </div>

      {!runtimeRunning && (
        <div className="runtime-hint">
          消息监听进程未运行，请启动 <code>uv run python -m src.main</code>
        </div>
      )}

      <div className="card-grid">
        {stats.map((c) => (
          <div key={c.label} className="stat-card">
            <div className="stat-label">{c.label}</div>
            <div className="stat-value" style={c.color ? { color: c.color } : undefined}>{c.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
