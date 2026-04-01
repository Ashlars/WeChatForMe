import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ConversationItem } from '../api/client';
import './Pages.css';

export default function Messages() {
  const [conversations, setConversations] = useState<{ private: ConversationItem[]; groups: ConversationItem[] } | null>(null);
  const [selected, setSelected] = useState<{ type: string; id: string; name: string } | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.listConversations().then(setConversations);
  }, []);

  const selectConversation = (type: string, id: string, name: string) => {
    setSelected({ type, id, name });
    loadMessages(type, id, 1);
  };

  const loadMessages = (type: string, id: string, p: number) => {
    const opts = type === 'group' ? { group_id: id } : { contact_id: id };
    api.listMessages(p, opts).then((res) => {
      setMessages(res.items.reverse()); // oldest first for chat view
      setTotal(res.total);
      setPage(p);
    });
  };

  return (
    <div>
      <h1 className="page-title">聊天记录</h1>
      <div className="chat-layout">
        <div className="chat-sidebar">
          {conversations && (
            <>
              {conversations.groups.length > 0 && (
                <div className="conv-section">
                  <div className="conv-section-title">群聊</div>
                  {conversations.groups.map((c) => (
                    <div key={c.id}
                      className={`conv-item ${selected?.id === c.id ? 'active' : ''}`}
                      onClick={() => selectConversation('group', c.id, c.name)}>
                      <div className="conv-name">{c.name}</div>
                      <div className="conv-preview">{c.last_content?.slice(0, 30) || ''}</div>
                      <div className="conv-meta">{c.msg_count} 条消息</div>
                    </div>
                  ))}
                </div>
              )}
              {conversations.private.length > 0 && (
                <div className="conv-section">
                  <div className="conv-section-title">私聊</div>
                  {conversations.private.map((c) => (
                    <div key={c.id}
                      className={`conv-item ${selected?.id === c.id ? 'active' : ''}`}
                      onClick={() => selectConversation('private', c.id, c.name)}>
                      <div className="conv-name">{c.name}</div>
                      <div className="conv-preview">{c.last_content?.slice(0, 30) || ''}</div>
                      <div className="conv-meta">{c.msg_count} 条消息</div>
                    </div>
                  ))}
                </div>
              )}
              {conversations.private.length === 0 && conversations.groups.length === 0 && (
                <div className="empty" style={{ padding: 20 }}>暂无聊天记录</div>
              )}
            </>
          )}
        </div>

        <div className="chat-main">
          {selected ? (
            <>
              <div className="chat-header">{selected.name} <span className="badge">{total} 条</span></div>
              {total > 50 && (
                <div className="pagination" style={{ padding: '8px 16px', justifyContent: 'flex-start' }}>
                  <button disabled={page * 50 >= total} onClick={() => loadMessages(selected.type, selected.id, page + 1)}>更早的消息</button>
                  <span>第 {page} 页</span>
                  <button disabled={page <= 1} onClick={() => loadMessages(selected.type, selected.id, page - 1)}>更新的消息</button>
                </div>
              )}
              <div className="chat-messages">
                {messages.map((m, i) => (
                  <div key={m.id || i} className={`chat-bubble ${m.direction === 'outgoing' ? 'sent' : 'received'}`}>
                    {m.direction === 'incoming' && <div className="bubble-sender">{m.contact_id}</div>}
                    <div className="bubble-content">{m.content}</div>
                    <div className="bubble-time">{m.created_at?.slice(5, 19)}</div>
                  </div>
                ))}
                {messages.length === 0 && <div className="empty">选择对话查看消息</div>}
              </div>
            </>
          ) : (
            <div className="empty" style={{ paddingTop: 100 }}>选择左侧对话查看聊天记录</div>
          )}
        </div>
      </div>
    </div>
  );
}
