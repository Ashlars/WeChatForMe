import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import './Pages.css';

export default function Groups() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const nav = useNavigate();

  const load = (p: number) => {
    api.listGroups(p).then((res) => {
      setItems(res.items);
      setTotal(res.total);
      setPage(p);
    });
  };

  useEffect(() => { load(1); }, []);

  const toggleActive = async (id: string, current: boolean) => {
    await api.updateGroup(id, { is_active: !current });
    load(page);
  };

  const startRename = (id: string, currentName: string) => {
    setEditing(id);
    setEditName(currentName || '');
  };

  const saveRename = async (id: string) => {
    if (editName.trim()) {
      await api.updateGroup(id, { group_name: editName.trim() });
      load(page);
    }
    setEditing(null);
  };

  return (
    <div>
      <h1 className="page-title">群聊 <span className="badge">{total}</span></h1>
      <table className="data-table">
        <thead>
          <tr>
            <th>群名</th>
            <th>触发模式</th>
            <th>自动回复</th>
            <th>主动聊天</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((g) => (
            <tr key={g.group_id} onClick={() => nav(`/groups/${g.group_id}`)} className="clickable-row">
              <td>
                {editing === g.group_id ? (
                  <span className="inline-edit" onClick={(e) => e.stopPropagation()}>
                    <input
                      autoFocus
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') saveRename(g.group_id); if (e.key === 'Escape') setEditing(null); }}
                    />
                    <button className="btn-sm" onClick={() => saveRename(g.group_id)}>保存</button>
                    <button className="btn-sm" onClick={() => setEditing(null)}>取消</button>
                  </span>
                ) : (
                  <span>
                    {g.group_name || g.group_id}
                    <button className="rename-btn" onClick={(e) => { e.stopPropagation(); startRename(g.group_id, g.group_name); }} title="改名">✏️</button>
                  </span>
                )}
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                <select value={g.trigger_mode} onChange={async (e) => {
                  await api.updateGroup(g.group_id, { trigger_mode: e.target.value as any });
                  load(page);
                }} style={{ padding: '3px 6px', borderRadius: 4, border: '1px solid #ddd', fontSize: 12 }}>
                  <option value="all">全部</option>
                  <option value="at_me">@我</option>
                  <option value="keyword">关键词</option>
                  <option value="both">两者</option>
                </select>
              </td>
              <td>
                <button className={`toggle-btn ${g.is_active ? 'on' : ''}`}
                  onClick={(e) => { e.stopPropagation(); toggleActive(g.group_id, g.is_active); }}>
                  {g.is_active ? '已启用' : '未启用'}
                </button>
              </td>
              <td>
                {g.proactive_enabled ? (
                  <span className="proactive-badge on">{g.proactive_topic || '已开启'}</span>
                ) : (
                  <span className="proactive-badge off">未开启</span>
                )}
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                <button className="btn-sm" onClick={() => nav(`/groups/${g.group_id}`)}>详情</button>
                <button className="btn-sm btn-del" onClick={async () => {
                  if (!confirm(`确定删除群聊「${g.group_name || g.group_id}」？`)) return;
                  await api.deleteGroup(g.group_id);
                  load(page);
                }}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {total > 20 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => load(page - 1)}>上一页</button>
          <span>第 {page} 页 / 共 {Math.ceil(total / 20)} 页</span>
          <button disabled={page * 20 >= total} onClick={() => load(page + 1)}>下一页</button>
        </div>
      )}
    </div>
  );
}
