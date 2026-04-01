import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Group, Rule, ProactiveChat, GroupMember } from '../api/client';
import EditableField from '../components/EditableField';
import './Pages.css';

export default function GroupDetail() {
  const { groupId } = useParams<{ groupId: string }>();
  const [group, setGroup] = useState<Group | null>(null);
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
  const [members, setMembers] = useState<GroupMember[]>([]);

  const loadMembers = (gid: string) => api.listGroupMembers(gid).then(setMembers);

  useEffect(() => {
    if (!groupId) return;
    api.getGroup(groupId).then(setGroup);
    api.getGroupRule(groupId).then(setRule);
    loadMembers(groupId);
    api.getProactiveChat(groupId).then((p) => {
      setProactive(p);
      if (p) {
        setProTopic(p.topic);
        setProInterval(p.interval_minutes);
      }
    });
  }, [groupId]);

  const doAnalyze = async () => {
    if (!groupId) return;
    setAnalyzing(true);
    setMsg('');
    try {
      const res = await api.analyzeGroup(groupId);
      setMsg(`分析任务已创建 (ID: ${res.analysis_run_id}, 状态: ${res.status})`);
      api.getGroup(groupId).then(setGroup);
    } catch (e: any) {
      setMsg(`分析失败: ${e.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const toggleProactive = async (enabled: boolean) => {
    if (!groupId || !group) return;
    setProSaving(true);
    try {
      const updated = await api.upsertProactiveChat(groupId, {
        chat_type: 'group',
        chat_name: group.group_name || groupId,
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
    if (!groupId || !group) return;
    setProSaving(true);
    try {
      const updated = await api.upsertProactiveChat(groupId, {
        chat_type: 'group',
        chat_name: group.group_name || groupId,
        enabled: proactive?.enabled ?? false,
        interval_minutes: proInterval,
        topic: proTopic,
      });
      setProactive(updated);
    } finally {
      setProSaving(false);
    }
  };

  if (!group) return <div className="loading">加载中...</div>;

  const proEnabled = proactive?.enabled ?? false;

  return (
    <div>
      <h1 className="page-title">
        {editingName ? (
          <span className="inline-edit">
            <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newName.trim()) {
                  api.updateGroup(groupId!, { group_name: newName.trim() }).then(() => {
                    api.getGroup(groupId!).then(setGroup);
                    setEditingName(false);
                  });
                }
                if (e.key === 'Escape') setEditingName(false);
              }} />
            <button className="btn-sm" onClick={() => {
              if (newName.trim()) api.updateGroup(groupId!, { group_name: newName.trim() }).then(() => {
                api.getGroup(groupId!).then(setGroup);
                setEditingName(false);
              });
            }}>保存</button>
            <button className="btn-sm" onClick={() => setEditingName(false)}>取消</button>
          </span>
        ) : (
          <span>{group.group_name || group.group_id}
            <button className="rename-btn" onClick={() => { setNewName(group.group_name || ''); setEditingName(true); }}>✏️</button>
          </span>
        )}
      </h1>

      <div className="detail-grid">
        <div className="detail-card">
          <h3>基本信息</h3>
          <dl>
            <dt>group_id</dt><dd>{group.group_id}</dd>
            <dt>群名</dt><dd>{group.group_name || '-'}</dd>
            <dt>启用自动回复</dt>
            <dd>
              <button className={`toggle-btn ${group.is_active ? 'on' : ''}`}
                onClick={() => api.updateGroup(groupId!, { is_active: !group.is_active }).then(() => api.getGroup(groupId!).then(setGroup))}>
                {group.is_active ? '已启用' : '未启用'}
              </button>
            </dd>
            <dt>触发模式</dt>
            <dd>
              <select value={group.trigger_mode} onChange={(e) =>
                api.updateGroup(groupId!, { trigger_mode: e.target.value as any }).then(() => api.getGroup(groupId!).then(setGroup))
              } style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #ddd' }}>
                <option value="all">全部消息</option>
                <option value="at_me">@我</option>
                <option value="keyword">关键词</option>
                <option value="both">@我 或 关键词</option>
              </select>
            </dd>
            <dt>关键词</dt><dd>{group.keywords?.join(', ') || '无'}</dd>
          </dl>
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
          <h3>群画像 & 策略</h3>
          <div className="editable-fields">
            <EditableField label="群氛围" value={group.group_profile || ''} multiline placeholder="群聊的氛围和特点"
              onSave={(v) => api.updateGroup(groupId!, { group_profile: v }).then(() => api.getGroup(groupId!).then(setGroup))} />
            <EditableField label="回复策略" value={group.reply_strategy || ''} multiline placeholder="在这个群里的回复策略"
              onSave={(v) => api.updateGroup(groupId!, { reply_strategy: v }).then(() => api.getGroup(groupId!).then(setGroup))} />
            <div className="field-row">
              <label>最近分析</label>
              <span className="field-value">{group.last_analysis_at?.slice(0, 19) || '从未'}</span>
            </div>
            <button className="btn-primary" onClick={doAnalyze} disabled={analyzing} style={{ marginTop: 8 }}>
              {analyzing ? '分析中...' : '立即分析'}
            </button>
            {msg && <div className="msg">{msg}</div>}
          </div>
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

      <div className="members-section">
        <h2 className="section-title">群成员画像 <span className="badge">{members.length}</span></h2>
        <p className="section-hint">编辑成员的角色、性格、说话风格等信息，回复时会参考这些画像来调整回应方式</p>
        {members.length === 0 ? (
          <div className="empty">暂无成员记录（有人发消息后会自动出现）</div>
        ) : (
          <div className="members-grid">
            {members.map((m) => (
              <MemberCard key={m.wxid} member={m} groupId={groupId!} onUpdated={() => loadMembers(groupId!)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MemberCard({ member, groupId, onUpdated }: { member: any; groupId: string; onUpdated: () => void }) {
  const hasContactData = member.contact_relationship || member.contact_persona || member.contact_style;

  return (
    <div className="member-card">
      <div className="member-header">
        <div>
          <span className="member-name">{member.nickname || member.wxid}</span>
          {member.contact_remark && <span className="member-remark">({member.contact_remark})</span>}
        </div>
        <div className="member-meta">
          <span className="member-stats">{member.msg_count} 条消息</span>
          {member.contact_is_whitelist ? <span className="member-tag">白名单</span> : null}
        </div>
      </div>

      <div className="member-section-label">群内信息</div>
      <div className="editable-fields">
        <EditableField label="我叫TA" value={member.group_my_alias || ''} placeholder="如: 老张、饼子、大佬"
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { my_alias_for: v }).then(onUpdated)} />
        <EditableField label="群内角色" value={member.role || ''} placeholder="选择或自定义"
          options={['群主', '管理员', '活跃分子', '偶尔冒泡', '潜水员', '话题发起者', '捧场王']}
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { role: v }).then(onUpdated)} />
        <EditableField label="性格" value={member.personality || ''} placeholder="选择或自定义"
          options={['幽默', '认真', '随和', '毒舌', '热心', '安静', '活泼', '耿直', '细腻', '豪爽']}
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { personality: v }).then(onUpdated)} />
        <EditableField label="说话风格" value={member.style_notes || ''} placeholder="选择或自定义"
          options={['喜欢发表情包', '经常用缩写', '口语化', '长篇大论', '简短直接', '喜欢开玩笑', '经常反问', '爱用感叹号']}
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { style_notes: v }).then(onUpdated)} />
        <EditableField label="备注" value={member.notes || ''} placeholder="其他信息"
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { notes: v }).then(onUpdated)} />
      </div>

      <div className="member-section-label">联系人信息{!hasContactData && ' (未填写)'}</div>
      <div className="editable-fields">
        <EditableField label="我平时叫TA" value={member.contact_my_alias || ''} placeholder="如: 老张、饼子（全局称呼）"
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { contact_my_alias_for: v }).then(onUpdated)} />
        <EditableField label="与我关系" value={member.contact_relationship || ''} placeholder="选择或自定义"
          options={['好朋友', '同事', '同学', '家人', '网友', '前同事', '老师', '客户', '邻居']}
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { relationship: v }).then(onUpdated)} />
        <EditableField label="人物画像" value={member.contact_persona || ''} placeholder="对方的人物画像" multiline
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { persona_summary: v }).then(onUpdated)} />
        <EditableField label="聊天风格" value={member.contact_style || ''} placeholder="选择或自定义"
          options={['口语化', '正式', '简短', '啰嗦', '爱用表情', '语音多', '喜欢分享链接', '经常发图']}
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { contact_style_summary: v }).then(onUpdated)} />
        <EditableField label="互动偏好" value={member.contact_interaction || ''} placeholder="选择或自定义"
          options={['喜欢被夸', '喜欢互怼', '喜欢深度聊', '喜欢轻松闲聊', '不喜欢废话', '喜欢被关心', '喜欢讨论专业话题']}
          onSave={(v) => api.updateGroupMember(groupId, member.wxid, { interaction_style_summary: v }).then(onUpdated)} />
      </div>
    </div>
  );
}
