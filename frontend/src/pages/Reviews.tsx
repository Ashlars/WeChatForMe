import { useEffect, useState } from 'react';
import { api } from '../api/client';
import './Pages.css';

export default function Reviews() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState('pending');

  const load = (status: string) => {
    api.listReviews(1, status || undefined).then((res) => {
      setItems(res.items);
      setTotal(res.total);
    });
  };

  useEffect(() => { load(filter); }, [filter]);

  const handleApprove = async (id: number) => {
    await api.approveReview(id);
    load(filter);
  };

  const handleReject = async (id: number) => {
    await api.rejectReview(id);
    load(filter);
  };

  const TYPE_LABELS: Record<string, string> = {
    rule_change: '规则变更',
    contact_profile_change: '联系人画像',
    group_profile_change: '群画像',
    contact_state_change: '状态变更',
  };

  const STATUS_LABELS: Record<string, string> = {
    pending: '待审核',
    applied: '已应用',
    rejected: '已拒绝',
  };

  return (
    <div>
      <h1 className="page-title">审核建议 <span className="badge">{total}</span></h1>

      <div className="filter-bar">
        {['pending', 'applied', 'rejected', ''].map((s) => (
          <button key={s} className={`filter-btn ${filter === s ? 'active' : ''}`}
            onClick={() => setFilter(s)}>
            {s ? STATUS_LABELS[s] || s : '全部'}
          </button>
        ))}
      </div>

      <div className="review-list">
        {items.map((item) => {
          let payload: any = {};
          try { payload = JSON.parse(item.proposed_payload_json); } catch {}

          return (
            <div key={item.id} className="review-card">
              <div className="review-header">
                <span className={`status-badge ${item.status}`}>{STATUS_LABELS[item.status] || item.status}</span>
                <span className="review-type">{TYPE_LABELS[item.review_type] || item.review_type}</span>
                <span className="review-target">{item.target_type}/{item.target_id}</span>
              </div>
              <pre className="review-payload">{JSON.stringify(payload, null, 2)}</pre>
              {item.status === 'pending' && (
                <div className="review-actions">
                  <button className="btn-primary" onClick={() => handleApprove(item.id)}>通过</button>
                  <button className="btn-danger" onClick={() => handleReject(item.id)}>拒绝</button>
                </div>
              )}
            </div>
          );
        })}
        {items.length === 0 && <div className="empty">暂无数据</div>}
      </div>
    </div>
  );
}
