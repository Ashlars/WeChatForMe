import { useEffect, useState } from 'react';
import { api } from '../api/client';
import './Pages.css';

export default function Analyses() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const load = (p: number) => {
    api.listAnalyses(p).then((res) => {
      setItems(res.items);
      setTotal(res.total);
      setPage(p);
    });
  };

  useEffect(() => { load(1); }, []);

  const STATUS_COLORS: Record<string, string> = {
    queued: '#2196f3',
    running: '#ff9800',
    succeeded: '#4caf50',
    failed: '#f44336',
  };

  return (
    <div>
      <h1 className="page-title">分析记录 <span className="badge">{total}</span></h1>
      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>目标</th>
            <th>触发</th>
            <th>状态</th>
            <th>摘要</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{r.target_type}/{r.target_id}</td>
              <td>{r.trigger_type}</td>
              <td><span style={{ color: STATUS_COLORS[r.status] || '#666' }}>{r.status}</span></td>
              <td>{r.summary || r.error_message || '-'}</td>
              <td>{r.created_at?.slice(0, 19)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {total > 20 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => load(page - 1)}>上一页</button>
          <span>第 {page} 页</span>
          <button disabled={page * 20 >= total} onClick={() => load(page + 1)}>下一页</button>
        </div>
      )}
    </div>
  );
}
