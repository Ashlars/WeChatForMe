import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import './Pages.css';

export default function Contacts() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [cleanupResult, setCleanupResult] = useState<string | null>(null);
  const nav = useNavigate();

  const load = (p: number) => {
    api.listContacts(p).then((res) => {
      setItems(res.items);
      setTotal(res.total);
      setPage(p);
    });
  };

  useEffect(() => { load(1); }, []);

  const toggle = async (wxid: string, field: 'is_whitelist' | 'is_paused', current: boolean) => {
    await api.updateContact(wxid, { [field]: !current });
    load(page);
  };

  const startRename = (wxid: string, currentName: string) => {
    setEditing(wxid);
    setEditName(currentName || '');
  };

  const saveRename = async (wxid: string) => {
    if (editName.trim()) {
      await api.updateContact(wxid, { nickname: editName.trim() });
      load(page);
    }
    setEditing(null);
  };

  const doCleanup = async () => {
    const res = await api.cleanupContacts();
    if (res.removed_count > 0) {
      setCleanupResult(`已清理 ${res.removed_count} 个无效联系人: ${res.removed.map((r: any) => `${r.nickname}(${r.reason})`).join(', ')}`);
      load(page);
    } else {
      setCleanupResult('没有需要清理的联系人');
    }
    setTimeout(() => setCleanupResult(null), 5000);
  };

  const doDelete = async (wxid: string, nickname: string) => {
    if (!confirm(`确定删除联系人「${nickname || wxid}」？`)) return;
    await api.deleteContact(wxid);
    load(page);
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">联系人 <span className="badge">{total}</span></h1>
        <button className="btn-cleanup" onClick={doCleanup}>扫描清理</button>
      </div>
      {cleanupResult && <div className="cleanup-result">{cleanupResult}</div>}
      <table className="data-table">
        <thead>
          <tr>
            <th>昵称</th>
            <th>备注</th>
            <th>白名单</th>
            <th>暂停</th>
            <th>主动聊天</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.wxid} onClick={() => nav(`/contacts/${c.wxid}`)} className="clickable-row">
              <td>
                {editing === c.wxid ? (
                  <span className="inline-edit" onClick={(e) => e.stopPropagation()}>
                    <input
                      autoFocus
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') saveRename(c.wxid); if (e.key === 'Escape') setEditing(null); }}
                    />
                    <button className="btn-sm" onClick={() => saveRename(c.wxid)}>保存</button>
                    <button className="btn-sm" onClick={() => setEditing(null)}>取消</button>
                  </span>
                ) : (
                  <span>
                    {c.nickname || c.wxid}
                    <button className="rename-btn" onClick={(e) => { e.stopPropagation(); startRename(c.wxid, c.nickname); }} title="改名">✏️</button>
                  </span>
                )}
              </td>
              <td>{c.remark || '-'}</td>
              <td>
                <button className={`toggle-btn ${c.is_whitelist ? 'on' : ''}`}
                  onClick={(e) => { e.stopPropagation(); toggle(c.wxid, 'is_whitelist', c.is_whitelist); }}>
                  {c.is_whitelist ? '是' : '否'}
                </button>
              </td>
              <td>
                <button className={`toggle-btn ${c.is_paused ? 'on warn' : ''}`}
                  onClick={(e) => { e.stopPropagation(); toggle(c.wxid, 'is_paused', c.is_paused); }}>
                  {c.is_paused ? '已暂停' : '正常'}
                </button>
              </td>
              <td>
                {c.proactive_enabled ? (
                  <span className="proactive-badge on">{c.proactive_topic || '已开启'}</span>
                ) : (
                  <span className="proactive-badge off">-</span>
                )}
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                <button className="btn-sm" onClick={() => nav(`/contacts/${c.wxid}`)}>详情</button>
                <button className="btn-sm btn-del" onClick={() => doDelete(c.wxid, c.nickname)} title="删除">删除</button>
              </td>
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
