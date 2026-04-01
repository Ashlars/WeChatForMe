import { useEffect, useState } from 'react';
import { api } from '../api/client';
import './Pages.css';

type Config = Record<string, string>;

const PROFILE_FIELDS = [
  { key: 'user_nickname', label: '你的昵称', placeholder: '在微信里别人怎么叫你' },
  { key: 'user_aliases', label: '别人对你的称呼', placeholder: '如: 老王, 王哥, 小王（逗号隔开）' },
  { key: 'user_personality', label: '性格特点', placeholder: '如: 幽默、毒舌、随和、爱开玩笑' },
  { key: 'user_speaking_style', label: '说话风格', placeholder: '如: 口语化、喜欢用反问、经常用缩写' },
  { key: 'user_habits', label: '口头禅和习惯', placeholder: '如: 喜欢说"绝了"、爱用😂、经常调侃朋友' },
  { key: 'user_topics', label: '感兴趣的话题', placeholder: '如: 足球、科技、游戏、吃喝' },
  { key: 'user_tone', label: '语气特征', placeholder: '如: 轻松随意、偶尔正经、喜欢抖机灵' },
  { key: 'user_extra', label: '其他补充', placeholder: '任何有助于模仿你说话方式的信息', multiline: true },
];

const API_FIELDS = [
  { key: 'chat_api_key', label: '回复消息 API Key', placeholder: '留空不修改', isSecret: true },
  { key: 'chat_api_base_url', label: '回复消息 Base URL', placeholder: 'https://api.anthropic.com' },
  { key: 'chat_api_model', label: '回复消息模型', placeholder: 'claude-sonnet-4-6' },
  { key: 'analysis_api_key', label: '分析数据 API Key', placeholder: '留空不修改', isSecret: true },
  { key: 'analysis_api_base_url', label: '分析数据 Base URL', placeholder: 'https://api.anthropic.com' },
  { key: 'analysis_api_model', label: '分析数据模型', placeholder: 'claude-sonnet-4-6' },
];

export default function Settings() {
  const [profile, setProfile] = useState<Config | null>(null);
  const [profileForm, setProfileForm] = useState<Config>({});
  const [apiConfig, setApiConfig] = useState<Config | null>(null);
  const [apiForm, setApiForm] = useState<Config>({});
  const [saving, setSaving] = useState('');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    api.getUserProfile().then((d) => { setProfile(d); });
    api.getApiConfig().then((d) => { setApiConfig(d as Config); });
  }, []);

  const saveProfile = async () => {
    setSaving('profile');
    try {
      const updated = await api.updateUserProfile(profileForm);
      setProfile(updated);
      setProfileForm({});
      setMsg('人设已保存');
      setTimeout(() => setMsg(''), 3000);
    } catch (e: any) {
      setMsg(`保存失败: ${e.message}`);
    } finally {
      setSaving('');
    }
  };

  const doSelfAnalyze = async () => {
    setSaving('analyze');
    setMsg('');
    try {
      const res = await api.selfAnalyze();
      if (res.updated && res.analysis) {
        // Reload profile to show updated values
        const updated = await api.getUserProfile();
        setProfile(updated);
        setProfileForm({});
        setMsg(`自我分析完成！分析了 ${res.messages_analyzed} 条消息，更新了 ${res.updated_fields?.length || 0} 个字段`);
      } else {
        setMsg(res.error || '分析失败');
      }
    } catch (e: any) {
      setMsg(`分析失败: ${e.message}`);
    } finally {
      setSaving('');
    }
  };

  const saveApi = async () => {
    setSaving('api');
    try {
      const updated = await api.updateApiConfig(apiForm);
      setApiConfig(updated);
      setApiForm({});
      setMsg('API 配置已保存');
      setTimeout(() => setMsg(''), 3000);
    } catch (e: any) {
      setMsg(`保存失败: ${e.message}`);
    } finally {
      setSaving('');
    }
  };

  if (!profile || !apiConfig) return <div className="loading">加载中...</div>;

  return (
    <div>
      <h1 className="page-title">设置</h1>

      <div className="settings-section highlight">
        <h3>我的人设</h3>
        <p className="settings-hint">定义你的人格特征，AI 会严格模仿你的风格来回复消息。填写越详细，回复越像你。</p>
        {PROFILE_FIELDS.map((f) => (
          <div key={f.key} className="settings-row">
            <label>{f.label}</label>
            <div className="settings-input-group">
              {(f as any).multiline ? (
                <textarea
                  placeholder={f.placeholder}
                  value={profileForm[f.key] ?? profile[f.key] ?? ''}
                  onChange={(e) => setProfileForm({ ...profileForm, [f.key]: e.target.value })}
                  rows={3}
                />
              ) : (
                <input
                  type="text"
                  placeholder={f.placeholder}
                  value={profileForm[f.key] ?? profile[f.key] ?? ''}
                  onChange={(e) => setProfileForm({ ...profileForm, [f.key]: e.target.value })}
                />
              )}
            </div>
          </div>
        ))}
        <div className="settings-actions">
          <button className="btn-primary" onClick={saveProfile} disabled={saving === 'profile'}>
            {saving === 'profile' ? '保存中...' : '保存人设'}
          </button>
          <button className="btn-analyze" onClick={doSelfAnalyze} disabled={saving === 'analyze'}>
            {saving === 'analyze' ? '分析中...' : '自动分析我的风格'}
          </button>
          {(msg.includes('人设') || msg.includes('分析')) && <span className="msg">{msg}</span>}
        </div>
      </div>

      <div className="settings-section">
        <h3>回复消息 API</h3>
        <p className="settings-hint">用于 ChatAgent 自动回复消息时调用的 API</p>
        {API_FIELDS.slice(0, 3).map((f) => (
          <div key={f.key} className="settings-row">
            <label>{f.label}</label>
            <div className="settings-input-group">
              {apiConfig[f.key] && !apiForm[f.key] && (
                <span className="settings-current">当前: {apiConfig[f.key]}</span>
              )}
              <input
                type={f.isSecret ? 'password' : 'text'}
                placeholder={f.placeholder}
                value={apiForm[f.key] || ''}
                onChange={(e) => setApiForm({ ...apiForm, [f.key]: e.target.value })}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="settings-section">
        <h3>分析数据 API</h3>
        <p className="settings-hint">用于画像分析时调用的 API</p>
        {API_FIELDS.slice(3).map((f) => (
          <div key={f.key} className="settings-row">
            <label>{f.label}</label>
            <div className="settings-input-group">
              {apiConfig[f.key] && !apiForm[f.key] && (
                <span className="settings-current">当前: {apiConfig[f.key]}</span>
              )}
              <input
                type={f.isSecret ? 'password' : 'text'}
                placeholder={f.placeholder}
                value={apiForm[f.key] || ''}
                onChange={(e) => setApiForm({ ...apiForm, [f.key]: e.target.value })}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="settings-actions">
        <button className="btn-primary" onClick={saveApi} disabled={saving === 'api' || Object.keys(apiForm).filter(k => apiForm[k]).length === 0}>
          {saving === 'api' ? '保存中...' : '保存 API 配置'}
        </button>
        {msg.includes('API') && <span className="msg">{msg}</span>}
      </div>

      <div className="settings-note">
        <p>API Key 保存后以脱敏形式显示。未配置时使用环境变量作为默认值。</p>
      </div>
    </div>
  );
}
