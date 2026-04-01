import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Contact, Rule, ProactiveChat } from '../api/client';
import EditableField from '../components/EditableField';
import './Pages.css';

export default function ContactDetail() {
  const { wxid } = useParams<{ wxid: string }>();
  const [contact, setContact] = useState<Contact | null>(null);
  const [rule, setRule] = useState<Rule | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [msg, setMsg] = useState('');

  // Proactive chat state
  const [proactive, setProactive] = useState<ProactiveChat | null>(null);
  const [proTopic, setProTopic] = useState('');
  const [proInterval, setProInterval] = useState(5);
  const [proSaving, setProSaving] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [newName, setNewName] = useState('');

  useEffect(() => {
    if (!wxid) return;
    api.getContact(wxid).then(setContact);
    api.getPrivateRule(wxid).then(setRule);
    api.getProactiveChat(wxid).then((p) => {
      setProactive(p);
      if (p) {
        setProTopic(p.topic);
        setProInterval(p.interval_minutes);
      }
    });
  }, [wxid]);

  const doAnalyze = async () => {
    if (!wxid) return;
    setAnalyzing(true);
    setMsg('');
    try {
      const res = await api.analyzeContact(wxid);
      setMsg(`分析任务已创建 (ID: ${res.analysis_run_id}, 状态: ${res.status})`);
      api.getContact(wxid).then(setContact);
    } catch (e: any) {
      setMsg(`分析失败: ${e.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const toggleProactive = async (enabled: boolean) => {
    if (!wxid || !contact) return;
    setProSaving(true);
    try {
      const updated = await api.upsertProactiveChat(wxid, {
        chat_type: 'private',
        chat_name: contact.remark || contact.nickname || wxid,
        enabled,
        interval_minutes: proInterval,
        topic: proTopic,
      });
      setProactive(updated);
    } finally {
      setProSaving(false);
    }
  };

  const saveProConfig = async () => {
    if (!wxid || !contact) return;
    setProSaving(true);
    try {
      const updated = await api.upsertProactiveChat(wxid, {
        chat_type: 'private',
        chat_name: contact.remark || contact.nickname || wxid,
        enabled: proactive?.enabled ?? false,
        interval_minutes: proInterval,
        topic: proTopic,
      });
      setProactive(updated);
    } finally {
      setProSaving(false);
    }
  };

  if (!contact) return <div className="loading">加载中...</div>;

  const proEnabled = proactive?.enabled ?? false;

  return (
    <div>
      <h1 className="page-title">
        {editingName ? (
          <span className="inline-edit">
            <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newName.trim()) {
                  api.updateContact(wxid!, { nickname: newName.trim() }).then(() => {
                    api.getContact(wxid!).then(setContact);
                    setEditingName(false);
                  });
                }
                if (e.key === 'Escape') setEditingName(false);
              }} />
            <button className="btn-sm" onClick={() => {
              if (newName.trim()) api.updateContact(wxid!, { nickname: newName.trim() }).then(() => {
                api.getContact(wxid!).then(setContact);
                setEditingName(false);
              });
            }}>保存</button>
            <button className="btn-sm" onClick={() => setEditingName(false)}>取消</button>
          </span>
        ) : (
          <span>{contact.nickname || contact.wxid}
            <button className="rename-btn" onClick={() => { setNewName(contact.nickname || ''); setEditingName(true); }}>✏️</button>
          </span>
        )}
      </h1>

      <div className="detail-grid">
        <div className="detail-card">
          <h3>基本信息</h3>
          <div className="editable-fields">
            <div className="field-row">
              <label>wxid</label>
              <span className="field-value">{contact.wxid}</span>
            </div>
            <EditableField label="备注" value={contact.remark || ''} placeholder="备注名" onSave={(v) => api.updateContact(wxid!, { remark: v }).then(() => api.getContact(wxid!).then(setContact))} />
            <EditableField label="我对TA的称呼" value={(contact as any).my_alias_for || ''} placeholder="如: 老张、饼子、大佬"
              onSave={(v) => api.updateContact(wxid!, { my_alias_for: v }).then(() => api.getContact(wxid!).then(setContact))} />
            <EditableField label="关系" value={contact.relationship || ''} placeholder="选择或自定义"
              options={['好朋友', '同事', '同学', '家人', '网友', '前同事', '老师', '客户', '邻居']}
              onSave={(v) => api.updateContact(wxid!, { relationship: v }).then(() => api.getContact(wxid!).then(setContact))} />
            <div className="field-row">
              <label>白名单</label>
              <button className={`toggle-btn ${contact.is_whitelist ? 'on' : ''}`}
                onClick={() => api.updateContact(wxid!, { is_whitelist: !contact.is_whitelist }).then(() => api.getContact(wxid!).then(setContact))}>
                {contact.is_whitelist ? '是' : '否'}
              </button>
            </div>
            <div className="field-row">
              <label>暂停回复</label>
              <button className={`toggle-btn ${contact.is_paused ? 'on warn' : ''}`}
                onClick={() => api.updateContact(wxid!, { is_paused: !contact.is_paused }).then(() => api.getContact(wxid!).then(setContact))}>
                {contact.is_paused ? '已暂停' : '正常'}
              </button>
            </div>
          </div>
        </div>

        <div className="detail-card">
          <h3>画像 & 个性</h3>
          <div className="editable-fields">
            <EditableField label="人物画像" value={contact.persona_summary || ''} multiline placeholder="对方的人物画像描述" onSave={(v) => api.updateContact(wxid!, { persona_summary: v }).then(() => api.getContact(wxid!).then(setContact))} />
            <EditableField label="聊天风格" value={contact.style_summary || ''} placeholder="选择或自定义"
              options={['口语化', '正式', '简短直接', '啰嗦', '爱用表情', '语音多', '喜欢分享链接', '长篇大论']}
              onSave={(v) => api.updateContact(wxid!, { style_summary: v }).then(() => api.getContact(wxid!).then(setContact))} />
            <EditableField label="互动偏好" value={contact.interaction_style_summary || ''} placeholder="选择或自定义"
              options={['喜欢被夸', '喜欢互怼', '喜欢深度聊', '喜欢轻松闲聊', '不喜欢废话', '喜欢被关心', '喜欢讨论专业话题']}
              onSave={(v) => api.updateContact(wxid!, { interaction_style_summary: v }).then(() => api.getContact(wxid!).then(setContact))} />
            <div className="field-row">
              <label>最近分析</label>
              <span className="field-value">{contact.last_analysis_at?.slice(0, 19) || '从未'}</span>
            </div>
            <button className="btn-primary" onClick={doAnalyze} disabled={analyzing} style={{ marginTop: 8 }}>
              {analyzing ? '分析中...' : '立即分析'}
            </button>
            {msg && <div className="msg">{msg}</div>}
          </div>
        </div>

        <div className="detail-card">
          <h3>主动聊天</h3>
          <div className="proactive-toggle">
            <span>开启主动聊天</span>
            <button
              className={`toggle-btn-lg ${proEnabled ? 'on' : 'off'}`}
              onClick={() => toggleProactive(!proEnabled)}
              disabled={proSaving}
            >
              {proEnabled ? '已开启' : '已关闭'}
            </button>
          </div>

          <div className="settings-row" style={{ marginTop: 12 }}>
            <label>话题主题</label>
            <input
              type="text"
              placeholder="如: 足球、科技、日常"
              value={proTopic}
              onChange={(e) => setProTopic(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14 }}
            />
          </div>

          <div className="settings-row" style={{ marginTop: 8 }}>
            <label>发送间隔（分钟）</label>
            <input
              type="number"
              min={1}
              value={proInterval}
              onChange={(e) => setProInterval(parseInt(e.target.value) || 5)}
              style={{ width: 100, padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14 }}
            />
          </div>

          <button className="btn-primary" onClick={saveProConfig} disabled={proSaving} style={{ marginTop: 12 }}>
            {proSaving ? '保存中...' : '保存配置'}
          </button>

          {proactive?.last_sent_at && (
            <div className="msg" style={{ marginTop: 8 }}>上次发送: {proactive.last_sent_at.slice(0, 19)}</div>
          )}
        </div>

        <div className="detail-card">
          <h3>聊天规则</h3>
          {rule ? (
            <pre className="rule-json">{JSON.stringify(rule.document, null, 2)}</pre>
          ) : (
            <p>暂无专属规则，使用全局默认</p>
          )}
        </div>
      </div>
    </div>
  );
}
