import { useState } from 'react';

interface Props {
  label: string;
  value: string;
  placeholder?: string;
  multiline?: boolean;
  options?: string[];  // Preset options for quick selection (multi-select + custom)
  onSave: (value: string) => Promise<any>;
}

export default function EditableField({ label, value, placeholder, multiline, options, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [customInput, setCustomInput] = useState('');

  const startEdit = () => {
    setDraft(value);
    setCustomInput('');
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  // For options mode: parse current value as comma-separated tags
  const selectedTags = draft ? draft.split('、').map(s => s.trim()).filter(Boolean) : [];

  const toggleTag = (tag: string) => {
    if (selectedTags.includes(tag)) {
      const next = selectedTags.filter(t => t !== tag);
      setDraft(next.join('、'));
    } else {
      setDraft([...selectedTags, tag].join('、'));
    }
  };

  const addCustom = () => {
    const v = customInput.trim();
    if (v && !selectedTags.includes(v)) {
      setDraft([...selectedTags, v].join('、'));
    }
    setCustomInput('');
  };

  if (editing) {
    return (
      <div className="field-row editing">
        <label>{label}</label>
        <div className="field-edit-area">
          {options ? (
            <>
              <div className="tag-selector">
                {options.map((opt) => (
                  <button key={opt} type="button"
                    className={`tag-btn ${selectedTags.includes(opt) ? 'selected' : ''}`}
                    onClick={() => toggleTag(opt)}>
                    {opt}
                  </button>
                ))}
              </div>
              {selectedTags.filter(t => !options.includes(t)).length > 0 && (
                <div className="tag-selector" style={{ marginTop: 4 }}>
                  {selectedTags.filter(t => !options.includes(t)).map((tag) => (
                    <button key={tag} type="button" className="tag-btn selected custom"
                      onClick={() => toggleTag(tag)}>
                      {tag} ×
                    </button>
                  ))}
                </div>
              )}
              <div className="tag-custom">
                <input
                  value={customInput}
                  onChange={(e) => setCustomInput(e.target.value)}
                  placeholder="自定义..."
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); addCustom(); }
                    if (e.key === 'Escape') setEditing(false);
                  }}
                />
                {customInput.trim() && (
                  <button className="btn-sm" type="button" onClick={addCustom}>添加</button>
                )}
              </div>
            </>
          ) : multiline ? (
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={placeholder}
              rows={3}
              onKeyDown={(e) => { if (e.key === 'Escape') setEditing(false); }}
            />
          ) : (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={placeholder}
              onKeyDown={(e) => {
                if (e.key === 'Enter') save();
                if (e.key === 'Escape') setEditing(false);
              }}
            />
          )}
          <div className="field-edit-actions">
            <button className="btn-sm" onClick={save} disabled={saving}>{saving ? '...' : '保存'}</button>
            <button className="btn-sm" onClick={() => setEditing(false)}>取消</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="field-row">
      <label>{label}</label>
      <span className="field-value clickable" onClick={startEdit}>
        {value || <span className="field-placeholder">{placeholder || '点击编辑'}</span>}
        <span className="field-edit-icon">✏️</span>
      </span>
    </div>
  );
}
