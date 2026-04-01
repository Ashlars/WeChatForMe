import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { AnalysisPolicy } from '../api/client';
import './Pages.css';

export default function Scheduler() {
  const [policy, setPolicy] = useState<AnalysisPolicy | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => { api.getPolicy().then(setPolicy); }, []);

  const save = async () => {
    if (!policy) return;
    setSaving(true);
    try {
      const updated = await api.updatePolicy(policy);
      setPolicy(updated);
      setMsg('已保存');
      setTimeout(() => setMsg(''), 2000);
    } catch (e: any) {
      setMsg(`保存失败: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (!policy) return <div className="loading">加载中...</div>;

  return (
    <div>
      <h1 className="page-title">调度策略</h1>

      <div className="detail-card" style={{ maxWidth: 600 }}>
        <label className="form-row">
          <span>启用批量分析</span>
          <input type="checkbox" checked={policy.enabled} onChange={(e) => setPolicy({ ...policy, enabled: e.target.checked })} />
        </label>

        <label className="form-row">
          <span>Cron 表达式</span>
          <input type="text" value={policy.cron_expr} onChange={(e) => setPolicy({ ...policy, cron_expr: e.target.value })} />
        </label>

        <label className="form-row">
          <span>每轮最大目标数</span>
          <input type="number" value={policy.max_targets_per_run} onChange={(e) => setPolicy({ ...policy, max_targets_per_run: parseInt(e.target.value) || 0 })} />
        </label>

        <label className="form-row">
          <span>分析联系人</span>
          <input type="checkbox" checked={policy.contacts_enabled} onChange={(e) => setPolicy({ ...policy, contacts_enabled: e.target.checked })} />
        </label>

        <label className="form-row">
          <span>分析群聊</span>
          <input type="checkbox" checked={policy.groups_enabled} onChange={(e) => setPolicy({ ...policy, groups_enabled: e.target.checked })} />
        </label>

        <label className="form-row">
          <span>最少间隔(小时)</span>
          <input type="number" value={policy.min_hours_since_last_analysis} onChange={(e) => setPolicy({ ...policy, min_hours_since_last_analysis: parseInt(e.target.value) || 0 })} />
        </label>

        <label className="form-row">
          <span>选择策略</span>
          <select value={policy.selection_strategy} onChange={(e) => setPolicy({ ...policy, selection_strategy: e.target.value })}>
            <option value="recently_active_first">最近活跃优先</option>
            <option value="oldest_unanalyzed_first">最久未分析优先</option>
          </select>
        </label>

        <div style={{ marginTop: 16 }}>
          <button className="btn-primary" onClick={save} disabled={saving}>{saving ? '保存中...' : '保存'}</button>
          {msg && <span className="msg" style={{ marginLeft: 12 }}>{msg}</span>}
        </div>
      </div>
    </div>
  );
}
